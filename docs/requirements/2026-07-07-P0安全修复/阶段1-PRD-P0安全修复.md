# 阶段 1 PRD — P0 安全漏洞修复（WS 认证 + Shell Exec 模式）

> 基线来源：[Orbit 安全与UX评估报告](../../research/Orbit-安全与UX评估报告-2026-07-07.html)
> 评估日期：2026-07-07 | 代码基线：1676dce
> 本轮范围：仅 P0-1 + P0-3（P0-2 用户选择跳过）

---

## 1. 背景

Orbit 安全评估报告发现 3 个 P0 致命漏洞。本轮修复其中 2 个：
- **P0-1**：WebSocket 聊天端点无认证——攻击者可无限制调用 LLM Agent
- **P0-3**：Shell 工具使用 `create_subprocess_shell`——尽管有白名单，`shell=True` 仍存在 shell 注入风险

## 2. 用户故事

| 优先级 | 用户故事 |
|--------|---------|
| P0 | 作为 Orbit 运维者，我希望 WebSocket 端点验证 token，防止未授权用户通过 WS 无限制调用 LLM |
| P0 | 作为 Orbit 安全审计者，我希望 Shell 工具直接 exec 而非经过 shell 解释器，消除命令注入攻击面 |

## 3. 验收标准

### P0-1：WebSocket 聊天端点认证

- **AC-1**：未携带有效 `X-Orbit-Token` 的 WebSocket 连接请求被拒绝（返回 401/403），不进入 `ws.accept()`
- **AC-2**：携带有效 token 的 WebSocket 连接正常建立，聊天功能不受影响
- **AC-3**：现有 HTTP 端点认证行为不变（回归约束）

### P0-3：Shell Exec 模式切换

- **AC-4**：`exec_command()` 使用 `create_subprocess_exec(*parts, ...)` 替代 `create_subprocess_shell(cmd, ...)`，不经过 shell 解释器
- **AC-5**：白名单验证、危险模式检测逻辑保持不变且正常工作
- **AC-6**：所有现有 shell 工具的测试用例保持通过

## 4. 边缘情况

| 场景 | 预期行为 |
|------|---------|
| WS 连接请求无 token header | 拒绝连接，返回 401 |
| WS 连接请求携带错误 token | 拒绝连接，返回 401 |
| WS 连接请求携带有效 token | 正常建立，后续收发消息不受影响 |
| `exec_command()` 收到含管道符的命令 | 白名单拒绝（管道经 shell 解释，exec 模式下不可用） |
| `exec_command()` 收到含重定向的命令 | 白名单拒绝（`>` 经 shell 解释，exec 模式下不可用） |
| `exec_command()` 收到简单命令如 `pytest tests/ -q` | 正常执行，行为和 shell 模式一致 |

## 5. 待确认问题

1. **WS 认证方案**：在 `ws.accept()` 前通过查询参数或子协议验证 token。查询参数方案简单但与 P1-1（SSE Token 经 URL 泄露）有同样缺陷。是否接受查询参数方案作为 P0 短期修复，后续统一迁移到 Header/子协议？→ **建议：查询参数，快速止血**
2. **exec 模式对管道/重定向的影响**：切换 `create_subprocess_exec` 后，`cmd1 | cmd2` 和 `cmd > file` 将不可用。白名单中 `ls | head` 等组合是否需要保留？→ **建议：白名单已有管道到 shell 的检测，切换 exec 后自然禁用管道/重定向，安全收益大于功能损失**

## 6. Non-Goals

- P0-2 (.env 密钥泄露) — 用户跳过
- P1 级别问题 — 后续迭代
- UX 改进 — 后续迭代
- JWT/Token 轮换机制 — P1-3，不在本轮
