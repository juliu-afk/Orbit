# PR #2 Type Safety — 阶段3 实现记录

> 基线: 阶段2-技术方案-PR2-TypeSafety.md | 日期: 2026-06-28

## 改动清单

| File | Change | Detail |
|------|--------|--------|
| `react_agent.py` | +10/-2 | TYPE_CHECKING 扩展 + role 参数 + 6 Any→具体类型 |
| `factory.py` | +13/-4 | TYPE_CHECKING 扩展 + create/get_agent 参数 Any→具体类型 + role=role 传递 |
| `spawn.py` | +17/-10 | TYPE_CHECKING 扩展 + spawn/_create_agent 参数 Any→具体 + 移除 type: ignore |
| `compose/orchestrator.py` | +2/-1 | actor_spawn Any→ActorSpawn\|None |
| `scheduler/orchestrator.py` | +9/-3 | TYPE_CHECKING 扩展 + 5 参数 Any→具体类型 |

## 偏差

- `message_bus` 和 `router` 保留 `Any`——对应模块无公开类型定义，预留后续 PR
- `spawn.py` 保留 `# noqa: F821` 在 `type[AgentFactory]` 行——shell 检查器误报

## 关键修复

### Issue #3: type: ignore 消除
- 旧：`class SpawnedAgent(ReActAgent): pass; SpawnedAgent.role = role  # type: ignore`
- 新：`ReActAgent(llm=llm, tools=tools, event_bus=event_bus, role=role)`
- ReActAgent.__init__ 新增 `role: AgentRole | None = None` → `self.role = role or type(self).role`

### Issue #5: Any 收敛
- 6 参数 `llm/graph/sandbox/event_bus/_compressor/_budget_tracker` → 具体类型
- 全部 `| None` 保持向后兼容

## 测试

- Unit: 全绿（排除预存 test_dream 失败）
- py_compile: 5/5 OK
- ReActAgent 子类兼容：零子类覆盖 __init__，无破坏
