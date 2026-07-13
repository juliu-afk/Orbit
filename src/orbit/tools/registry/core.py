"""ToolRegistry——工具注册中心核心类。

从 registry.py 拆分——models/exceptions 见 models.py。
"""

from __future__ import annotations

import asyncio
import ast
import importlib
import json as _json
import threading
import time
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

# ChatMode 门禁信号——需前端确认
_CONFIRM_SIGNAL = "__CONFIRM_NEEDED__"

import structlog

from orbit.tools.models import ToolInvocation, ToolSchema
from orbit.tools.registry.models import (
    DoomLoopError,
    PermissionError,
    RateLimitError,
    ToolCall,
    ToolDeprecatedError,
    ToolEntry,
    ToolHandler,
    ToolNotFoundError,
    WorkspaceViolationError,
)

logger = structlog.get_logger("orbit.tools")

# ── 全局单例 ────────────────────────────────────────────
_registry_instance: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    """获取全局 ToolRegistry 单例——供工具文件底部自注册使用."""
    return ToolRegistry.get_instance()


def _path_to_module(file_path: str) -> str:
    r"""文件路径 → Python 模块路径.

    e.g. "src/orbit/tools/filesystem.py" → "orbit.tools.filesystem"
    """
    p = Path(file_path)
    parts = list(p.parts)
    try:
        idx = parts.index("orbit")
        parts = parts[idx:]
    except ValueError:
        try:
            idx = parts.index("src")
            parts = parts[idx + 1:]
        except ValueError:
            stem = p.stem
            return f"orbit.tools.{stem}"
    parts[-1] = parts[-1].replace(".py", "")
    return ".".join(parts)


def _version_key(version: str) -> tuple[int, ...]:
    """semver 字符串 → 可排序元组."""
    try:
        return tuple(int(x) for x in version.split("."))
    except (ValueError, AttributeError):
        return (0,)


class ToolRegistry:
    """工具注册中心——注册/查询/调用 + AST自发现 + 并发安全.

    用法 (旧 API——向后兼容):
        reg = ToolRegistry()
        reg.register(
            ToolSchema(name="query_knowledge", version="1.0.0",
                       allowed_agents=["QAAgent"], rate_limit=10),
            handler=lambda params: knowledge_store.query(**params),
        )
        result = reg.invoke("query_knowledge", {"concept": "CurrentRatio"},
                            agent_name="QAAgent")

    用法 (新 API——AST 自注册):
        # 在 tools/filesystem.py 底部:
        registry = get_registry()
        registry.register(
            name="read_file", toolset="filesystem",
            schema={...}, handler=read_file, concurrency="safe",
        )
    """

    # 并发分类常量——对标 Hermes tool_dispatch_helpers.py 三类判定
    NEVER_PARALLEL = {"exec_command"}  # 交互式，必须串行
    PATH_SCOPED = {"write_file", "edit_file"}  # 同路径串行，不同路径可并行
    # 其余默认 "safe"——可并发

    _instance: ToolRegistry | None = None
    _lock = threading.RLock()

    def __init__(self) -> None:
        # 旧存储: name -> list[(version, ToolSchema, handler)]
        self._tools: dict[str, list[tuple[str, ToolSchema, ToolHandler]]] = {}
        # 新存储: name -> ToolEntry (AST 自注册的工具)
        self._entries: dict[str, ToolEntry] = {}
        # 限流状态: "name:version:agent" -> deque[timestamp]
        self._rate_limiters: dict[str, deque[float]] = {}
        # 调用审计
        self._invocations: list[ToolInvocation] = []
        # Doom Loop 追踪: agent_name -> tool_name -> list[ToolCall]
        self._tool_history: dict[str, dict[str, list[ToolCall]]] = {}
        # MCP 客户端连接: server_name -> MCPClientConnection
        self._mcp_connections: dict[str, Any] = {}
        # 确认回路: confirm_id → (asyncio.Event, result dict)
        self._pending_confirms: dict[str, tuple[object, dict]] = {}
        self._confirm_counter: int = 0

    # ── 单例 ─────────────────────────────────────────

    @classmethod
    def get_instance(cls) -> ToolRegistry:
        """获取全局单例——供 AST 自注册文件使用。"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ── 新 API: 简化注册 (AST 自注册入口) ────────────────

    def register_tool(
        self,
        name: str,
        toolset: str,
        schema: dict,
        handler: Callable,
        check_fn: Callable[[], bool] | None = None,
        concurrency: str = "safe",
    ) -> None:
        """新 API——工具自注册入口.

        WHY 分离新旧 API: 旧 API 接受 ToolSchema 对象，新 API 接受扁平参数，
        两边签名不兼容，分开避免类型混淆。
        """
        entry = ToolEntry(
            name=name,
            toolset=toolset,
            schema=schema,
            handler=handler,
            check_fn=check_fn,
            concurrency=concurrency,
        )
        self._entries[name] = entry
        logger.info(
            "tool_registered_v2",
            name=name,
            toolset=toolset,
            concurrency=concurrency,
        )

    # ── 旧 API: ToolSchema 注册 (向后兼容) ───────────────

    def register(self, schema: ToolSchema, handler: ToolHandler) -> None:
        """旧 API——注册工具 (ToolSchema + handler).

        同一 name 可注册多版本。
        """
        self._tools.setdefault(schema.name, []).append((schema.version, schema, handler))
        logger.info("tool_registered", name=schema.name, version=schema.version)

    # ── AST 自发现 ────────────────────────────────────

    @classmethod
    def discover(cls, paths: list[str]) -> None:
        """AST 扫描 + 自动导入——对标 Hermes discover_builtin_tools().

        扫描给定路径下所有 .py 文件，查找 registry.register() 或
        registry.register_tool() 调用，自动 import 触发注册。

        WHY AST 而非 import 全部: 只导入含注册调用的模块，避免副作用。
        """
        _ = cls.get_instance()  # 确保单例已初始化
        for path in paths:
            p = Path(path)
            if not p.exists():
                logger.warning("discover_path_not_found", path=str(p))
                continue
            for f in p.rglob("*.py"):
                if f.name.startswith("_"):
                    continue
                try:
                    tree = ast.parse(f.read_text(encoding="utf-8"))
                except (SyntaxError, UnicodeDecodeError):
                    logger.warning("discover_parse_failed", file=str(f))
                    continue
                for node in ast.walk(tree):
                    if (
                        isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr in ("register", "register_tool")
                    ):
                        # 动态导入触发 @registry.register 装饰器或底部 register() 调用
                        module_path = _path_to_module(str(f))
                        try:
                            importlib.import_module(module_path)
                        except Exception as e:
                            logger.warning(
                                "discover_import_failed",
                                module=module_path,
                                error=str(e),
                            )
                        break  # 一个文件只需导入一次

    # ── 角色→工具映射 ───────────────────────────────

    # 每个角色可调用的工具——缩小攻击面，减少 prompt 噪音
    # WHY: Clarifier 不需要 shell，Reviewer 不需要 write_file
    # WHY 多媒体工具按角色分配:
    # - chatter: read_file(代码)+file_parser(文档)+ocr_document(图片)，
    #   watch_video 太重不走自动检测，用 /watch 命令
    # - architect/reviewer/dream: +file_parser 看设计文档
    # - developer/qa: 全套多媒体
    ROLE_TOOLS: dict[str, set[str]] = {
        "architect": {"read_file", "grep", "glob", "file_parser"},
        "developer": {"read_file", "write_file", "edit_file", "exec_command", "grep", "glob", "file_parser", "ocr_document", "watch_video", "gui_agent", "spawn_subagent"},
        "reviewer": {"read_file", "grep", "glob", "file_parser", "spawn_subagent"},
        "qa": {"read_file", "exec_command", "grep", "glob", "file_parser", "ocr_document", "gui_agent", "spawn_subagent"},
        "config_manager": {"read_file", "write_file", "grep", "glob", "file_parser"},
        "clarifier": set(),  # 纯文本交互，无需工具
        "dream": {"read_file", "grep", "glob", "file_parser"},
        "chatter": {"read_file", "file_parser", "ocr_document"},
    }

    # MCP 工具自动授予的角色——这些角色需要代码导航/编辑能力
    # WHY: MCP 工具名是动态的，无法在 ROLE_TOOLS 中硬编码
    # 静态枚举。改为按 toolset 前缀 `mcp:` 自动匹配。
    MCP_ROLES: set[str] = {"architect", "developer", "reviewer", "qa"}

    def list_for_role(self, role_value: str) -> list[dict]:
        """返回指定角色可用的工具 JSON Schema.

        WHY: 按角色裁剪工具列表——关闭不该有的门。
        MCP 工具（toolset 以 `mcp:` 开头）自动授予代码相关角色。
        """
        # 未知角色回退空集——最小权限原则：新角色默认无工具
        allowed = self.ROLE_TOOLS.get(role_value, set())
        schemas: list[dict] = []
        seen: set[str] = set()

        for name, entry in self._entries.items():
            # 本地工具：走白名单
            if name in allowed:
                schemas.append(entry.schema)
                seen.add(name)
            # MCP 工具：自动授予有代码能力的角色
            elif entry.toolset.startswith("mcp:") and role_value in self.MCP_ROLES:
                schemas.append(entry.schema)
                seen.add(name)

        # 旧 API 工具（向后兼容）——也按角色过滤
        for name in self._tools:
            if name in seen:
                continue
            if name in allowed:
                entries = self._tools[name]
                entries.sort(key=lambda e: _version_key(e[0]), reverse=True)
                schema = entries[0][1]
                if schema.parameters:
                    schemas.append(schema.parameters)
                seen.add(name)

        return schemas

    # ── LLM 工具 Schema 导出 ─────────────────────────────

    def get_schemas(self) -> list[dict]:
        """返回所有工具 JSON Schema——供 LLM function calling 使用.

        对标 OpenAI tools 参数格式: [{"type":"function","function":{...}}, ...]
        """
        schemas: list[dict] = []
        seen: set[str] = set()

        # 新 ToolEntry (优先——可能覆盖同名旧工具)
        for name, entry in self._entries.items():
            schemas.append(entry.schema)
            seen.add(name)

        # 旧 ToolSchema (向后兼容——跳过已被新 API 覆盖的)
        for name, entries in self._tools.items():
            if name in seen:
                continue
            entries.sort(key=lambda e: _version_key(e[0]), reverse=True)
            schema = entries[0][1]
            if schema.parameters:
                schemas.append(schema.parameters)
            seen.add(name)

        return schemas

    # ── 工具分发 (ReAct 循环核心) ──────────────────────────

    def set_permission(self, engine: Any) -> None:
        """Phase 4: 注入 PermissionEngine 实例。"""
        self._permission = engine

    async def dispatch(
        self, name: str, args: dict[str, Any], agent_name: str = "react_agent"
    ) -> str:
        """执行工具并返回字符串结果——ReAct 循环调用入口.

        Args:
            name: 工具名
            args: 工具参数
            agent_name: 调用方 Agent 名——用于审计 + 权限检查
        """
        # Phase 4 AC-A4: PermissionEngine 前置检查
        perm = getattr(self, "_permission", None)
        if perm is not None:
            path = str(args.get("path", args.get("file_path", "")))
            command = str(args.get("command", ""))
            if not perm.check(agent_name, name, path=path, command=command):
                return f"权限拒绝——{agent_name} 无权执行 {name}"

        # ChatMode 四级门禁——在 PermissionEngine 之后，工具执行之前
        chat_mode_gate = self._check_mode_gate(name, agent_name)
        if chat_mode_gate is not None:
            if chat_mode_gate == "__CONFIRM_NEEDED__":
                # 异步确认回路——等 WebSocket confirm_response
                session_id = ""
                try:
                    from orbit.core.context import get_context
                    session_id = get_context().session_id
                except Exception:
                    pass
                allow_remember = True  # Edit Automatically 才显示，Manual 不显示
                try:
                    from orbit.core.context import get_context
                    from orbit.skills.models import ChatMode
                    allow_remember = get_context().chat_mode == ChatMode.EDIT_AUTO
                except Exception:
                    pass
                approved, remember = await self._request_confirm(
                    name, args, session_id, allow_remember)
                if not approved:
                    return f"用户拒绝了工具执行: {name}"
                if remember:
                    try:
                        from orbit.core.context import get_context
                        get_context().confirmed_tools.add(name)
                    except Exception:
                        pass
            else:
                return chat_mode_gate

        # 新 API 优先
        entry = self._entries.get(name)
        if entry is not None:
            # P1-7: 新 API 路径也要检查 per-agent 白名单
            if entry.allowed_agents and agent_name not in entry.allowed_agents:
                return f"权限拒绝——Agent {agent_name} 不在 {name} 白名单中"
            return await self._dispatch_entry(entry, args)

        # 旧 API 回退——走完整权限+限流管线
        if name in self._tools:
            return str(self.invoke(name, args, agent_name=agent_name))

        return f"error: 工具不存在: {name}"

    async def _dispatch_entry(self, entry: ToolEntry, args: dict[str, Any]) -> str:
        """执行 ToolEntry——截断 + 错误处理."""
        import inspect

        try:
            if inspect.iscoroutinefunction(entry.handler):
                result = await entry.handler(**args)
            else:
                result = entry.handler(**args)
        except Exception as e:
            logger.error("tool_dispatch_error", tool=entry.name, error=str(e))
            return f"工具执行错误: {str(e)}"

        # AC6b: 截断超长输出 (>10K chars → 头尾+摘要)
        result_str = str(result) if not isinstance(result, str) else result
        if len(result_str) > entry.max_result_chars:
            half = entry.max_result_chars // 2
            result_str = (
                result_str[:half]
                + f"\n\n... [截断 {len(result_str) - entry.max_result_chars} 字符] ...\n\n"
                + result_str[-half:]
            )
        return result_str

    # ── 并发安全判定 ─────────────────────────────────────

    def _should_parallelize(self, calls: list[ToolCall]) -> tuple[list[ToolCall], list[ToolCall]]:
        """将工具调用分为 safe(可并发) 和 serial(必须串行) 两组.

        对标 Hermes _should_parallelize_tool_batch():
        - NEVER_PARALLEL (exec_command) → serial
        - PATH_SCOPED (write_file, edit_file) 同路径的 → serial
        - 其余 → safe (可并发)
        """
        safe: list[ToolCall] = []
        serial: list[ToolCall] = []
        # 追踪 PATH_SCOPED 工具已见的路径
        path_seen: dict[str, int] = {}

        for call in calls:
            entry = self._entries.get(call.name)

            # 检查 NEVER_PARALLEL（即使工具未注册也生效）
            if call.name in self.NEVER_PARALLEL:
                serial.append(call)
                continue
            if entry is not None and entry.concurrency == "never_parallel":
                serial.append(call)
                continue

            if entry is None:
                # 旧 API 工具——检查类级别并发标记
                if call.name in self.NEVER_PARALLEL:
                    serial.append(call)
                elif call.name in self.PATH_SCOPED:
                    path = call.args.get("path", "")
                    if path and path in path_seen:
                        serial.append(call)
                    else:
                        if path:
                            path_seen[path] = 0
                        safe.append(call)
                else:
                    safe.append(call)
                continue
            elif entry.concurrency == "serial" or call.name in self.PATH_SCOPED:
                path = call.args.get("path", "")
                if path and path in path_seen:
                    serial.append(call)  # 同路径冲突
                else:
                    if path:
                        path_seen[path] = 0
                    safe.append(call)
            else:
                safe.append(call)

        return safe, serial

    # ── ChatMode 门禁 ────────────────────────────────────

    def _is_write_tool(self, name: str) -> bool:
        """判断工具是否为写操作——基于 ToolEntry.is_write 标记。

        默认 True（安全默认）——未注册的工具一律视为写操作。
        """
        entry = self._entries.get(name)
        if entry is not None:
            return entry.is_write
        write_patterns = ("write", "edit", "delete", "create", "run", "exec",
                          "bash", "shell", "move", "copy", "mkdir", "rm")
        return any(p in name.lower() for p in write_patterns)

    async def _request_confirm(self, name: str, args: dict, session_id: str,
                                allow_remember: bool) -> tuple[bool, bool]:
        """发送 confirm_request 并等待用户响应。

        Returns: (approved, remember)
        """
        self._confirm_counter += 1
        cid = f"confirm_{self._confirm_counter}_{time.time()}"

        # 通过 ws_sender 推送确认请求到客户端
        try:
            from orbit.core.context import get_context
            ctx = get_context()
            sender = ctx.ws_sender
            if sender and callable(sender):
                import json as _json
                await sender(_json.dumps({
                    "code": 0,
                    "data": {
                        "type": "confirm_request",
                        "confirm_id": cid,
                        "tool_name": name,
                        "tool_args": args,
                        "message": f"即将执行 {name}",
                        "allow_remember": allow_remember,
                    },
                }))
        except Exception:
            pass

        # 创建 Event 等待用户响应
        event = asyncio.Event()
        result: dict = {"approved": False, "remember": False}
        self._pending_confirms[cid] = (event, result)

        try:
            await asyncio.wait_for(event.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            pass  # 超时 → 默认拒绝（result 已是 False）
        finally:
            self._pending_confirms.pop(cid, None)

        return result["approved"], result["remember"]

    def resolve_confirm(self, confirm_id: str, approved: bool, remember: bool) -> None:
        """WebSocket confirm_response 到达时调用——唤醒等待的 _request_confirm。"""
        entry = self._pending_confirms.get(confirm_id)
        if entry is None:
            return
        event, result = entry
        result["approved"] = approved
        result["remember"] = remember
        event.set()

    def _check_mode_gate(self, name: str, agent_name: str) -> str | None:
        """ChatMode 四级门禁——同步检查（不含 WebSocket 确认）。

        确认回路由 dispatch() 中的异步 _request_confirm 处理。
        此方法仅返回 None（放行）或 str（Plan 模式拒绝原因）。
        Manual/Edit 需要确认时返回确认标记字符串，由调用方处理。
        """
        try:
            from orbit.core.context import get_context
            from orbit.skills.models import ChatMode
            ctx = get_context()
        except ImportError:
            return None

        mode = ctx.chat_mode
        is_write = self._is_write_tool(name)

        if mode == ChatMode.AUTO:
            return None

        if mode == ChatMode.PLAN:
            if is_write:
                return (
                    f"Plan 模式不允许写操作。当前工具 {name} 为写入操作。"
                    "切换到 Manual / Edit Automatically / Auto Mode 后可执行。"
                )
            return None

        if mode == ChatMode.MANUAL:
            # 标记需要确认——dispatch 层处理异步回路
            return "__CONFIRM_NEEDED__"

        if mode == ChatMode.EDIT_AUTO:
            if not is_write:
                return None
            confirmed = ctx.confirmed_tools
            if name in confirmed:
                return None
            return "__CONFIRM_NEEDED__"

        return None

    # ── Doom Loop 检测 ────────────────────────────────────

    def would_form_loop(self, agent_name: str, tool_name: str, args: dict[str, Any]) -> bool:
        """检查即将执行的调用是否会形成死循环.

        对标 OpenCode processor.ts:350——连续 3 次同工具同参数 → True.
        WHY 前置检查而非后置: 避免第 3 次调用白白执行后再拦截。
        WHY per-tool 隔离: 不同工具独立追踪，避免 A 工具的历史误伤 B 工具。
        """
        agent_history = self._tool_history.get(agent_name, {})
        tool_history = agent_history.get(tool_name, [])
        if len(tool_history) < 2:
            return False
        # 最近 2 次 + 当前调用 = 3 次连续相同
        last2 = tool_history[-2:]
        return all(c.args == args for c in last2)

    def record_tool_call(self, agent_name: str, name: str, args: dict[str, Any]) -> None:
        """记录工具调用到历史——per-agent + per-tool 嵌套.

        WHY 嵌套结构: agent → tool → history，防止跨工具污染。
        """
        agent_history = self._tool_history.setdefault(agent_name, {})
        agent_history.setdefault(name, []).append(ToolCall(name=name, args=args))

    def clear_tool_history(self, agent_name: str) -> None:
        """清除指定 Agent 的所有工具调用历史."""
        self._tool_history.pop(agent_name, None)

    # ── 旧 API 保持 ─────────────────────────────────────

    def get_schema(self, name: str, version: str | None = None) -> ToolSchema:
        """获取工具 Schema——version 为空时返回最新版本."""
        # 新 API 优先
        entry = self._entries.get(name)
        if entry is not None:
            # 从 ToolEntry 构造 ToolSchema (向后兼容)
            return ToolSchema(
                name=entry.name,
                version="2.0.0",  # Phase 1 标记
                description=entry.schema.get("function", {}).get("description", ""),
                parameters=entry.schema,
            )

        # 旧 API 回退
        entries = self._tools.get(name)
        if not entries:
            raise ToolNotFoundError(f"工具不存在: {name}")
        if version:
            for v, schema, _ in entries:
                if v == version:
                    return schema
            raise ToolNotFoundError(f"工具 {name} 版本 {version} 不存在")
        entries.sort(key=lambda e: _version_key(e[0]), reverse=True)
        return entries[0][1]

    def get_latest_version(self, name: str) -> str:
        return self.get_schema(name).version

    def invoke(
        self,
        name: str,
        params: dict[str, Any],
        agent_name: str,
        version: str | None = None,
    ) -> Any:
        """调用工具——权限检查 + 限流检查 + 执行 + 审计."""
        start = time.time()

        # 新 API 路径
        entry = self._entries.get(name)
        if entry is not None:
            import asyncio

            try:
                # 安全执行 async handler——兼容同步和异步调用上下文
                try:
                    asyncio.get_running_loop()
                except RuntimeError:
                    # 无运行中事件循环——直接用 asyncio.run()
                    result = asyncio.run(self._dispatch_entry(entry, params))
                else:
                    # 在已有事件循环中——用线程池避免冲突
                    import concurrent.futures

                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        future = pool.submit(asyncio.run, self._dispatch_entry(entry, params))
                        result = future.result(timeout=30)
                inv = ToolInvocation(
                    tool_name=name,
                    tool_version="2.0.0",
                    agent_name=agent_name,
                    parameters=params,
                    result=result,
                    status="success",
                    duration_ms=(time.time() - start) * 1000,
                    timestamp=start,
                )
                self._invocations.append(inv)
                return result
            except Exception as e:
                inv = ToolInvocation(
                    tool_name=name,
                    tool_version="2.0.0",
                    agent_name=agent_name,
                    parameters=params,
                    status="error",
                    error=str(e),
                    duration_ms=(time.time() - start) * 1000,
                    timestamp=start,
                )
                self._invocations.append(inv)
                raise

        # 旧 API 路径 (保持不变)
        schema = self.get_schema(name, version)
        if schema.deprecated:
            raise ToolDeprecatedError(f"工具 {name} 已废弃: {schema.deprecated_message}")
        if schema.allowed_agents and agent_name not in schema.allowed_agents:
            inv = ToolInvocation(
                tool_name=name,
                tool_version=schema.version,
                agent_name=agent_name,
                parameters=params,
                status="permission_denied",
                error=f"Agent {agent_name} 不在 {name} 白名单中",
                timestamp=start,
            )
            self._invocations.append(inv)
            raise PermissionError(inv.error)

        if schema.rate_limit > 0:
            key = f"{name}:{schema.version}:{agent_name}"
            if not self._check_rate_limit(key, schema.rate_limit):
                inv = ToolInvocation(
                    tool_name=name,
                    tool_version=schema.version,
                    agent_name=agent_name,
                    parameters=params,
                    status="rate_limited",
                    error=f"工具 {name} 已达限流 ({schema.rate_limit}/min)",
                    timestamp=start,
                )
                self._invocations.append(inv)
                raise RateLimitError(inv.error)

        handler = self._get_handler(name, schema.version)
        try:
            result = handler(params)
            status = "success"
            error = ""
        except Exception as e:
            result = None
            status = "error"
            error = str(e)

        inv = ToolInvocation(
            tool_name=name,
            tool_version=schema.version,
            agent_name=agent_name,
            parameters=params,
            result=result,
            error=error,
            status=status,
            duration_ms=(time.time() - start) * 1000,
            timestamp=start,
        )
        self._invocations.append(inv)
        return result

    def get_invocations(self, limit: int = 50) -> list[dict[str, Any]]:
        return [i.to_dict() for i in self._invocations[-limit:]]

    def list_tools(self) -> list[dict[str, Any]]:
        """列出所有工具（每个 name 返回最新版本）."""
        result: list[dict[str, Any]] = []

        # 新 API 工具
        for name, entry in self._entries.items():
            result.append(
                {
                    "name": name,
                    "latest_version": "2.0.0",
                    "description": entry.schema.get("function", {}).get("description", ""),
                    "deprecated": False,
                    "rate_limit": 0,
                    "concurrency": entry.concurrency,
                    "toolset": entry.toolset,
                }
            )

        # 旧 API 工具
        for name in self._tools:
            if name in self._entries:
                continue  # 已被新 API 覆盖
            schema = self.get_schema(name)
            result.append(
                {
                    "name": schema.name,
                    "latest_version": schema.version,
                    "description": schema.description,
                    "deprecated": schema.deprecated,
                    "rate_limit": schema.rate_limit,
                }
            )

        return result

    # ── 内部 ─────────────────────────────────────────────

    def _get_handler(self, name: str, version: str) -> ToolHandler:
        entries = self._tools.get(name, [])
        for v, _, handler in entries:
            if v == version:
                return handler
        raise ToolNotFoundError(f"工具 {name} v{version} handler 缺失")

    def _check_rate_limit(self, key: str, limit: int) -> bool:
        """滑动窗口限流检查——窗口 60 秒, 清洗过期后判断."""
        now = time.time()
        dq = self._rate_limiters.get(key)
        if dq is None:
            dq = deque()
            self._rate_limiters[key] = dq
        cutoff = now - 60
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= limit:
            return False
        dq.append(now)
        return True

    # ── MCP 客户端集成 ─────────────────────────────────────

    def connect_mcp_server(
        self,
        name: str,
        command: str,
        args: list[str],
        env: dict[str, str] | None = None,
        timeout: int = 30,
    ) -> int:
        """连接外部 MCP 服务器，发现并注册其工具。

        WHY: 让 Orbit Agent 透明调用外部 MCP 工具，通过 MCPClientConnection 桥接。
        通过 MCP 协议桥接——Agent 不感知工具是本地还是远程。

        Returns:
            成功注册的工具数量（0 = 无工具或连接失败）
        """
        # WHY: 防止重复连接——先断开旧连接再建新连接
        if name in self._mcp_connections:
            old = self._mcp_connections.pop(name)
            try:
                old.disconnect()
            except Exception:
                pass

        from orbit.tools.mcp_client import MCPClientConnection, MCPClientError

        conn = MCPClientConnection(name=name, command=command, args=args, env=env)
        conn.CALL_TIMEOUT = timeout

        try:
            conn.connect()
        except MCPClientError as e:
            logger.warning("mcp_connect_failed", server=name, error=str(e))
            return 0

        try:
            tools = conn.list_tools()
        except MCPClientError as e:
            logger.warning("mcp_list_tools_failed", server=name, error=str(e))
            conn.disconnect()
            return 0

        count = 0
        for tool in tools:
            tool_name = tool.get("name", "")
            if not tool_name:
                continue
            # 加服务器前缀避免与本地工具名冲突
            prefixed_name = f"{name}/{tool_name}"
            schema = self._convert_mcp_schema(prefixed_name, tool)
            handler = self._create_mcp_handler(name, conn, tool_name)

            self.register_tool(
                name=prefixed_name,
                toolset=f"mcp:{name}",
                schema=schema,
                handler=handler,
                concurrency="safe",
            )
            count += 1

        self._mcp_connections[name] = conn
        logger.info("mcp_server_registered", server=name, tools=count)
        return count

    def disconnect_mcp_servers(self) -> None:
        """断开所有 MCP 服务器连接——应用关闭时调用。"""
        for name, conn in list(self._mcp_connections.items()):
            try:
                conn.disconnect()
            except Exception:
                pass
        self._mcp_connections.clear()

    def mcp_server_status(self) -> dict[str, dict[str, Any]]:
        """返回已连接 MCP 服务器的运行状态——供 /api/v1/mcp/servers 展示。

        WHY: 路由层不应直接触碰私有 _mcp_connections，这里封装为只读快照。
        """
        out: dict[str, dict[str, Any]] = {}
        for name, conn in self._mcp_connections.items():
            try:
                connected = bool(getattr(conn, "connected", False))
                tools = conn.list_tools() if connected else []
            except Exception:
                connected, tools = False, []
            out[name] = {"connected": connected, "tools_count": len(tools)}
        return out

    @staticmethod
    def _convert_mcp_schema(prefixed_name: str, tool: dict[str, Any]) -> dict[str, Any]:
        """MCP inputSchema → OpenAI function calling 格式。

        WHY 转换: Orbit 的 ToolEntry.schema 使用 OpenAI function calling 格式，
        与 LLM 的 tool_calls 参数一致，无需额外适配层。
        """
        input_schema = tool.get("inputSchema", {})
        return {
            "type": "function",
            "function": {
                "name": prefixed_name,
                "description": tool.get("description", ""),
                "parameters": {
                    "type": input_schema.get("type", "object"),
                    "properties": input_schema.get("properties", {}),
                    "required": input_schema.get("required", []),
                },
            },
        }

    def _create_mcp_handler(
        self,
        server_name: str,
        conn: Any,
        tool_name: str,
    ) -> ToolHandler:
        """创建 MCP 工具调用闭包——将 ToolRegistry 调用转发到 MCP 服务器。

        WHY 闭包而非类方法: 每个远程工具绑定不同的 tool_name，
        闭包捕获 server_name + conn + tool_name，无需为每个工具创建类。
        """
        from orbit.tools.mcp_client import MCPClientError

        def handler(**kwargs: Any) -> str:
            try:
                return conn.call_tool(tool_name, kwargs)
            except MCPClientError as e:
                return f"MCP 工具调用失败 [{server_name}/{tool_name}]: {e}"
            except Exception as e:
                logger.error(
                    "mcp_handler_error",
                    server=server_name,
                    tool=tool_name,
                    error=str(e),
                )
                return f"MCP 工具异常 [{server_name}/{tool_name}]: {e}"

        return handler

