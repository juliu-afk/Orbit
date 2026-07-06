# 阶段 1 PRD — P1 安全漏洞修复（8 项）

> 基线：[Orbit 安全与UX评估报告](../../research/Orbit-安全与UX评估报告-2026-07-07.html)
> 本轮范围：全部 8 项 P1 严重安全问题

---

## 1. 背景

P0 修复完成后，安全评分从 2.5 → ~3.0。8 项 P1 修复后目标：安全评分 3.5+。

## 2. P1 清单与用户故事

| ID | 问题 | 文件 | 严重度 | 工作量 |
|----|------|------|--------|--------|
| P1-1 | SSE Token 经 URL 查询参数泄露 | `dependencies.py:21` | 严重 | 低 |
| P1-2 | Windows 沙箱无 AppContainer | `process_sandbox.py:69` | 严重 | 高 |
| P1-3 | 单一静态 Token 无轮换 | `dependencies.py:65` | 严重 | 高 |
| P1-4 | PermissionEngine Layer4 仅咨询 | `permission.py:93` | 严重 | 低 |
| P1-5 | TokenBucket 无锁竞态 | `token_bucket.py:35` | 严重 | 低 |
| P1-6 | 敏感文件列表三处不同步 | `guard.py + permission.py + validators.py` | 严重 | 中 |
| P1-7 | 新 API 白名单未执行 | `registry/core.py:319` | 严重 | 中 |
| P1-8 | CI bandit 仅扫 HIGH | `security.yml:61` | 一般 | 低 |

### P1-1：SSE Token URL 泄露

**用户故事**：作为运维者，我希望 SSE 流式 token 不通过 URL 查询参数传递，防止泄露到 Nginx 日志/浏览器历史/Referer。

### P1-2：Windows 沙箱加固

**用户故事**：作为运维者，我希望 Windows 上的进程沙箱有 AppContainer 级别的隔离，而非仅 subprocess 的弱隔离。

### P1-3：Token 轮换

**用户故事**：作为运维者，我希望认证 token 支持 JWT 轮换和撤销，而非单一静态 token 一旦泄露永久有效。

### P1-4：Layer4 强制执行

**用户故事**：作为安全审计者，我希望 PermissionEngine Layer4 对 shell 类工具的执行前检查沙箱可用性并拒绝，而非仅日志记录。

### P1-5：TokenBucket 竞态

**用户故事**：作为运维者，我希望 TokenBucket 在高并发多协程场景下令牌计数准确，不受竞态条件影响。

### P1-6：敏感文件列表统一

**用户故事**：作为安全维护者，我希望敏感文件拒绝列表只在一处定义，三处使用同一来源，避免新增敏感模式时遗漏。

### P1-7：新 API 白名单

**用户故事**：作为安全审计者，我希望 dispatch() 新 API 路径也执行 per-agent allowed_agents 白名单检查，而非裸绕过。

### P1-8：CI bandit 全级别

**用户故事**：作为 CI 维护者，我希望 bandit 扫描全部安全级别而非仅 HIGH，捕获中低风险问题提前预防。

## 3. 验收标准

| AC | 描述 |
|----|------|
| AC-1 | SSE token 从 HTTP Header (`X-Orbit-Token`) 读取，不再经 URL 查询参数 |
| AC-2 | `process_sandbox.py` 增加 `_run_windows_appcontainer()` 方法或明确标注需 pywin32 依赖的 TODO |
| AC-3 | `dependencies.py` 支持 JWT Token 生成/验证/过期，保留静态 token 作为降级回退 |
| AC-4 | `permission.py` Layer4 在 `tool_name == "exec_command"` 且沙箱不可用时返回 False |
| AC-5 | `token_bucket.py` `allow()` 加 `asyncio.Lock` 保护 `_tokens` 读写 |
| AC-6 | 创建 `security/constants.py`，`guard.py`/`permission.py`/`validators.py` 统一引用 |
| AC-7 | `dispatch()` 新 API 路径在 `_dispatch_entry` 前检查 `entry.allowed_agents` |
| AC-8 | `security.yml` bandit 改为 `-lll` 扫描全级别 |
| AC-9 | 所有现有测试保持通过 |

## 4. 边缘情况

| 场景 | 预期行为 |
|------|---------|
| SSE 客户端不带 X-Orbit-Token header | 返回 403 |
| PyJWT 库不可用 | 降级到静态 token 模式 |
| TokenBucket 100 协程同时 allow() | asyncio.Lock 串行化，令牌计数精确 |
| AppContainer 不可用（无 pywin32） | 降级到当前 subprocess 模式 + structlog warning |
| ToolEntry.allowed_agents 为空列表 | 允许所有 agent（向后兼容） |
| bandit -lll 发现中低风险 | 仅报告不阻塞 CI（continue-on-error: true） |

## 5. 待确认问题

1. **P1-2 (AppContainer)**：需 pywin32 新依赖。是否接受？→ **建议：加 TODO + 条件导入，有 pywin32 时启用，无则降级**
2. **P1-3 (JWT)**：需 PyJWT 新依赖 + 密钥管理方案。JWT secret 从哪里来？→ **建议：`JWT_SECRET` 环境变量，随机生成默认值**
3. **P1-8 (bandit -lll)**：可能产生大量中低风险噪音。是否阻塞 CI？→ **建议：continue-on-error: true，不阻塞**

## 6. Non-Goals

- JWT 刷新令牌 / 黑名单 —— P1-3 只做到期验证，不做完整轮换体系（属中期）
- Firecracker / gVisor —— 不在本轮
- OAuth2 / PKCE —— 不在本轮
