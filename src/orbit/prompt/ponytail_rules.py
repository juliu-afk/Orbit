"""Ponytail 决策阶梯——约束 Agent 代码生成行为。

对标开源项目 Ponytail (DietrichGebert, 68k+ stars)。
核心哲学: "最好的代码是你没写的代码。"

6 级决策阶梯——写任何代码前，从第 1 级开始爬，命中最先满足的那一级:
  1. 这东西需要存在吗？ → 不需要就跳过 (YAGNI)
  2. 标准库能干吗？ → 用 stdlib，不引入外部依赖
  3. 平台原生功能？ → 用原生 (如 <input type="date"> 而非 date-picker 库)
  4. 已安装的依赖里有？ → 用现有依赖，不新增
  5. 一行代码能搞定？ → 写一行，不抽象
  6. (兜底) → 写最少可工作的代码

WHY 独立模块: 决策阶梯是纯文本规则，不应散落在 agent prompt 拼接逻辑中。
集中管理方便版本迭代和强度调节。
"""

from __future__ import annotations

# ── 决策阶梯（完整版）──────────────────────────────────────

PONYTAIL_LADDER_FULL = """
## 代码生成规则——Ponytail 决策阶梯

**写任何代码前，从第 1 级开始爬。命中最先满足的那一级，在该级停下。**

### 第 1 级：这东西需要存在吗？
- 如果需求可以用"不写代码"的方式满足 → 不写（YAGNI）。
- 如果已有代码能实现同样功能 → 不写新代码。
- 如果是"将来可能用到"的抽象 → 不写。等真的需要时再写。

### 第 2 级：标准库能干吗？
- 优先用语言标准库。不要为一个小功能引入外部包。
- Python: pathlib, dataclasses, itertools, functools, collections
- TypeScript: URL, fetch, Array methods, Intl, crypto
- 检查: `python -c "import <module>"` 确认是 stdlib

### 第 3 级：平台原生功能？
- 浏览器原生: `<input type="date">`、`<dialog>`、`<details>`、CSS Grid/Flexbox
- 操作系统: 环境变量、文件系统 API、系统调度器
- 数据库: 内置函数（COALESCE、窗口函数、CTE）而非应用层处理
- 不要引入 UI 库替代原生 HTML/CSS 功能

### 第 4 级：已安装的依赖里有？
- 检查 pyproject.toml / package.json / Cargo.toml
- 如果已有依赖能实现 → 用它，不新增依赖
- 新增依赖必须确认: 包大小、维护状态、许可证兼容性

### 第 5 级：一行代码？
- 能一行写完就不写函数。能一个函数搞定就不写类。
- 写完后反问: 有能删的行吗？有能合并的变量吗？
- 文件超过 200 行 → 重新审视是否做了太多事

### 第 6 级（兜底）：写最少可工作的代码
- 不要过早抽象。三个相似行好过一个过早的基类。
- 不添加未要求的功能、错误处理、兼容层。
- 写完后问: 如果明天有人要删掉这段代码，会删几行？

## 安全底线（以下规则永远不跳过）
- 输入验证——信任边界处必须校验
- 错误处理——防止数据丢失的异常必须捕获
- 安全措施——认证、加密、SQL 注入防护
- 无障碍——ARIA 标签、键盘导航
- 硬件校准——嵌入式/IoT 场景

## 补充规则
- **删除优先于新增**: 写新代码前先删死代码。
- **无聊胜过聪明**: 优先简单、明显的方案。
- **最少文件数**: 不要做猜测性抽象，不要写模板代码。
- **治根不治标**: 修改共享函数，不要在调用处打补丁。
- **标记捷径**: 故意的快捷方式加 `# ponytail: <天花板> — 升级触发: <条件>` 注释。
"""

# ── 各强度级别变体 ───────────────────────────────────────

PONYTAIL_LADDER_LITE = """
## 代码质量建议——Ponytail（建议模式）

以下建议不强制执行，但请在写代码前过一遍:
- 能用标准库就别用外部包。能用已有依赖就别新增。
- 能一行写完就别抽象成函数。写完后检查是否有可删除的行。
- 优先简单方案，不要过早优化和过早抽象。
"""

PONYTAIL_LADDER_ULTRA = """
## 代码生成规则——Ponytail 极简模式

你是极简主义代码写手。你的目标是**用最少的代码完成需求**。

规则:
1. **挑战需求本身**——这个需求能用更简单的方式满足吗？能删掉一部分范围吗？
2. **一行原则**——每个功能必须能用一行代码解释。如果不能，你在过度工程。
3. **0 依赖原则**——除非绝对必要（如数据库驱动），不引入任何新依赖。
4. **删删删**——写完立即检查: 哪些行可以删掉？哪个变量可以合并？哪个函数可以内联？
5. **标记所有捷径**——`# ponytail: <天花板> — 升级: <条件>`
"""

# ── 模式常量 ─────────────────────────────────────────────

VALID_MODES = ("off", "lite", "full", "ultra")
DEFAULT_MODE = "full"

LADDER_BY_MODE: dict[str, str] = {
    "off": "",
    "lite": PONYTAIL_LADDER_LITE,
    "full": PONYTAIL_LADDER_FULL,
    "ultra": PONYTAIL_LADDER_ULTRA,
}


def get_ladder(mode: str) -> str:
    """按模式获取决策阶梯文本。

    Args:
        mode: "off" | "lite" | "full" | "ultra"

    Returns:
        对应模式的规则文本，off 返回空字符串
    """
    return LADDER_BY_MODE.get(mode, LADDER_BY_MODE[DEFAULT_MODE])


def determine_mode(
    task_type: str = "unknown",
    project_files: int = 0,
    user_override: str | None = None,
) -> str:
    """自适应判断 Ponytail 强度。

    决策矩阵:
        新项目/空目录 → ultra（极简起步）
        成熟项目 + feature → full（尊重已有模式）
        成熟项目 + bugfix → lite（专注修复，建议不强制）
        成熟项目 + refactor → ultra（鼓励删冗余）
        用户显式设置 → 以用户为准

    Args:
        task_type: "feature" | "bugfix" | "refactor" | "unknown"
        project_files: 已有文件数
        user_override: 环境变量/API 设置的覆盖值

    Returns:
        模式名: "off" | "lite" | "full" | "ultra"
    """
    # 用户显式设置始终优先
    if user_override is not None and user_override in VALID_MODES:
        return user_override

    # 新项目 → ultra
    if project_files < 5:
        return "ultra"

    # 按任务类型
    if task_type == "bugfix":
        return "lite"
    if task_type == "refactor":
        return "ultra"

    # feature / unknown + 成熟项目 → full
    return "full"
