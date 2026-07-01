"""Mock 工具注册表——替代 tools/registry.py:ToolRegistry。

可配置工具返回结果、限流触发、Doom Loop 检测。
用于测试中替代真实工具执行（read_file/write_file/exec_command等）。

使用示例:
    # 正常分发
    reg = MockToolRegistry(tool_results={"read_file": "file content"})
    # 限流触发
    reg = MockToolRegistry(rate_limited=True)
    # Doom Loop 检测
    reg = MockToolRegistry(doom_loop_detect=True)
"""

from __future__ import annotations

from typing import Any


class RateLimitError(Exception):
    """工具调用限流——兼容生产 RateLimitError。"""


class ToolNotFoundError(Exception):
    """工具不存在——兼容生产 ToolNotFoundError。"""


class DoomLoopError(Exception):
    """Doom Loop 检测——兼容生产 DoomLoopError。"""


class MockToolRegistry:
    """Mock 工具注册表——替代 tools/registry.py:ToolRegistry。

    100% 兼容 dispatch()/invoke() 接口签名。不执行真实文件系统/Shell 操作。
    """

    def __init__(
        self,
        tool_results: dict[str, Any] | None = None,
        rate_limited: bool = False,
        doom_loop_detect: bool = False,
    ) -> None:
        """初始化 Mock 工具注册表。

        Args:
            tool_results: tool_name → 返回值（dispatch 时返回）
            rate_limited: True→所有调用抛 RateLimitError
            doom_loop_detect: True→连续3次相同调用抛 DoomLoopError
        """
        self._tool_results = tool_results or {}
        self.rate_limited = rate_limited
        self.doom_loop_detect = doom_loop_detect

        # Doom Loop 追踪
        self._call_history: list[tuple[str, str]] = []  # (tool_name, args_key)

        # 调用追踪
        self.dispatch_count: int = 0
        self.dispatches: list[dict[str, Any]] = []  # {name, args, agent_name}

    # ── 链式配置方法 ──────────────────────────────────────

    def with_result(self, tool_name: str, result: Any) -> "MockToolRegistry":
        """设置特定工具的返回值。"""
        self._tool_results[tool_name] = result
        return self

    def with_rate_limited(self) -> "MockToolRegistry":
        """启用限流模拟。"""
        self.rate_limited = True
        return self

    def with_doom_loop(self) -> "MockToolRegistry":
        """启用 Doom Loop 检测。"""
        self.doom_loop_detect = True
        return self

    # ── 生产接口兼容方法 ──────────────────────────────────

    async def dispatch(
        self,
        name: str,
        args: dict[str, Any],
        agent_name: str = "react_agent",
    ) -> str:
        """执行工具——兼容 ToolRegistry.dispatch()。

        Returns:
            工具执行结果字符串

        Raises:
            RateLimitError: rate_limited=True 时
            DoomLoopError: doom_loop_detect=True 且连续3次相同调用时
        """
        self.dispatch_count += 1
        self.dispatches.append({"name": name, "args": args, "agent_name": agent_name})

        # 限流检查
        if self.rate_limited:
            raise RateLimitError(f"Tool '{name}' rate limit exceeded")

        # Doom Loop 检测（连续3次相同 tool+args）
        if self.doom_loop_detect:
            args_key = str(sorted(args.items()))
            self._call_history.append((name, args_key))
            # 检查最近3次是否相同
            if len(self._call_history) >= 3:
                last3 = self._call_history[-3:]
                if last3[0] == last3[1] == last3[2]:
                    raise DoomLoopError(f"Doom loop detected for tool '{name}'")

        # 返回预设结果或默认值
        if name in self._tool_results:
            return str(self._tool_results[name])

        return f"[mock] Tool '{name}' executed successfully"

    def invoke(
        self,
        name: str,
        params: dict[str, Any],
        agent_name: str,
        version: str | None = None,
    ) -> Any:
        """调用工具（旧 API）——兼容 ToolRegistry.invoke()。"""
        # 委托给 dispatch，返回字符串（invoke 返回任意类型）
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 在已有 event loop 中用 create_task 不够优雅，简化为同步返回
                if name in self._tool_results:
                    return self._tool_results[name]
                # 检查限流
                if self.rate_limited:
                    raise RateLimitError(f"Tool '{name}' rate limit exceeded")
                return f"[mock] Tool '{name}' executed (sync)"
        except RuntimeError:
            pass

        # 无 event loop → 同步返回
        if name in self._tool_results:
            return self._tool_results[name]
        if self.rate_limited:
            raise RateLimitError(f"Tool '{name}' rate limit exceeded")
        return f"[mock] Tool '{name}' executed (sync)"

    # ── 辅助方法 ──────────────────────────────────────────

    def reset(self) -> None:
        """重置调用追踪状态。"""
        self.dispatch_count = 0
        self.dispatches.clear()
        self._call_history.clear()
