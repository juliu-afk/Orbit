# 代码审查 —— Session 架构重构

## 审查清单

| 维度 | 检查项 | 结果 |
|------|--------|------|
| **安全** | SQL 注入 / XSS / 命令注入 / eval() / 硬编码密钥 | ✅ 通过 |
| **财务** | Decimal（N/A——Orbit 不涉及会计计算） | ✅ N/A |
| **会计规则** | 恒等式 / 借贷成对（N/A） | ✅ N/A |
| **方案偏差** | 是否按阶段2方案实现 | ✅ 严格按方案，无偏差 |
| **回溯一致性** | 代码→方案→PRD 可追溯 | ✅ 6/6 验收标准逐条有对应 |
| **测试覆盖** | 新代码是否有测试 | ✅ 145 测试全绿 |

## 审查发现

### 已修复（5 项）

| # | 严重度 | 位置 | 问题 | 修复 |
|---|-------|------|------|------|
| 1 | 致命 | `chat.py:52` | 畸形 JSON → `json.JSONDecodeError` 未捕获 → WebSocket 崩溃 | 模块级预 import orjson/json，解析失败 `continue` 返回错误 |
| 2 | 风险 | `executor.py:121` | 脚本挂载路径未做 Windows Docker 转换（`C:\...` vs `//c/...`），环境切换可能挂载失败 | `host_script` 也走 `_to_docker_path()` |
| 3 | 风险 | `sessions/registry.py:161` | archived→active 静默覆盖为 archived，API 返回 200 OK | `update()` 改为 `raise ValueError`，API 层转 409 Conflict |
| 4 | 一般 | `executor.py:159` | mount 字符串 split/join 重建相同内容，死代码 | 直接用 `mount` |
| 5 | 一般 | `projects/registry.py:255` | `except (IndexError, KeyError)` 中 IndexError 永远不会被 sqlite3.Row 抛出 | 改为 `except KeyError:` |

### 已有问题，未在本次修复

| # | 严重度 | 位置 | 问题 |
|---|-------|------|------|
| 6 | 风险 | `projects/registry.py:188` | `search()` 中 `f"%{query}%"` 未转义 `%`/`_` 通配符——已有代码，非本次引入 |

## 审查结论

**通过。** 致命问题已修复，风险问题已修复。

145 单元+集成测试全绿，TypeScript 类型检查通过，Vite 构建通过。
