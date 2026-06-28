---
name: test-gate
version: "1.0"
description: |
  Orbit 仓库测试门禁与最佳实践。覆盖单元测试、集成测试、E2E 测试三层，
  以及覆盖率、mock 隔离、fixture 规范。
trigger_keywords:
  - "测试"
  - "coverage"
  - "pytest"
  - "e2e"
  - "mock"
---

# 测试门禁 Skill —— Orbit 仓库专用

## 一、测试分层

| 层级 | 目录 | 职责 | 运行命令 |
|------|------|------|----------|
| Unit | `tests/unit/` | 单模块逻辑，AsyncMock 隔离外部依赖 | `pytest tests/unit/ -q --cov=src/orbit --cov-fail-under=80` |
| Integration | `tests/integration/` | 多模块编排，覆盖 SSE/Compose/权限/Shell 白名单 | `pytest tests/integration/ -q` |
| E2E | `tests/e2e/` | 端到端，Playwright 三层（L1 UI / L2 API 断言 / L3 文档驱动） | `pytest tests/e2e/ --headed` |

## 二、覆盖率门禁

- **硬性阈值**：`--cov-fail-under=80`
- **检查命令**：`python -m pytest tests/unit/ -q --cov=src/orbit --cov-fail-under=80 --cov-report=term-missing:skip-covered`
- **踩线处理**：如某模块覆盖率过低（如 `worktree/manager.py` 仅 18%），补充该模块的单元测试，而非全局降低阈值

## 三、Mock 隔离规范

### 3.1 外部 API / git 调用
```python
from unittest.mock import AsyncMock

# 正确：mock 底层方法
mock_git = AsyncMock()
manager._git = mock_git

# 错误：重构后 mock 失效
# 如 generate_stream() 重构为委托 generate_stream_with_tools()
# 旧 mock _stream_completion 会失效，导致调用真实 API
```

### 3.2 检查 mock 是否失效
- 本地测试耗时异常（>5s 说明可能调用了真实 API）
- CI 出现 `litellm.AuthenticationError` / 超时取消

### 3.3 litellm 相关测试
- 必须 mock `generate_stream_with_tools` 而非 `_stream_completion`
- 熔断器测试使用 `AsyncMock` 模拟 `cb.record_failure`

## 四、Fixture 规范

### 4.1 路径处理
```python
# ❌ 错误：硬编码路径导致 Linux CI PermissionError
@pytest.fixture
def manager():
    return WorktreeManager("/fake/repo")

# ✅ 正确：使用 tmp_path
@pytest.fixture
def manager(tmp_path):
    return WorktreeManager(str(tmp_path))
```

### 4.2 数据库隔离
- 每个测试使用独立 SQLite `:memory:` 或 `tmp_path` 文件
- 避免并发测试共享同一文件导致 `database locked`

## 五、已知 flaky 测试

| 测试 | 症状 | 处理 |
|------|------|------|
| `unit-test (3.11)` | SQLite `database locked` | 与 PR 无关，重试即可 |
| `test_tools.py` | 相对路径误判 | master 既有问题，与当前 PR 无关 |
| `test_dream.py` | 状态变更断言失败 | master 既有问题，与当前 PR 无关 |

## 六、测试新增流程

1. 读 PRD / 技术方案，提取 Acceptance Criteria（AC）
2. 根据 AC 确定测试范围，**禁止全量回归**
3. 优先补充覆盖率不足的模块
4. 本地跑 `pytest --cov` 确认 ≥80%
5. 提交测试代码到 PR

## 七、CI 测试检查清单

```bash
# 1. 全量测试
pytest tests/unit/ tests/integration/ -q

# 2. 覆盖率
pytest tests/unit/ -q --cov=src/orbit --cov-fail-under=80

# 3. 指定模块快速验证
pytest tests/unit/test_worktree.py -v --tb=short

# 4. 检查失败是否与本 PR 相关
# - 失败测试是否触及 PR 修改的文件？
# - 失败是否是 master 既有的？（对比 master 分支测试结果）
```
