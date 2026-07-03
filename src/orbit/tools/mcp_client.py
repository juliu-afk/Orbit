"""MCP 客户端——通过 stdio 子进程连接外部 MCP 服务器。

WHY 手写 JSON-RPC 2.0 而非引入 MCP SDK：MVP 零额外依赖，
与现有 mcp_server.py 策略一致。协议足够简单——5 个方法、~150 行。

协议规范：https://spec.modelcontextprotocol.io/
对标：Claude Code `claude mcp add` 机制
"""

from __future__ import annotations

import json
import subprocess
import threading
import time
from typing import Any

import structlog

logger = structlog.get_logger("orbit.tools.mcp_client")


class MCPClientError(Exception):
    """MCP 客户端错误——连接失败/超时/协议错误。"""


class MCPClientConnection:
    """MCP JSON-RPC 2.0 客户端——管理一个外部 MCP 服务器的生命周期。

    用法::

        conn = MCPClientConnection("serena", "uvx", ["--from", "...", "serena", "start-mcp-server"])
        conn.connect()
        tools = conn.list_tools()
        result = conn.call_tool("find_symbol", {"name_path": "MyClass"})
        conn.disconnect()
    """

    # 超时（秒）
    CONNECT_TIMEOUT = 10
    CALL_TIMEOUT = 30

    def __init__(
        self,
        name: str,
        command: str,
        args: list[str],
        env: dict[str, str] | None = None,
    ) -> None:
        """存储连接参数，不立即启动进程（lazy connect）。

        Args:
            name: 服务器标识名（用于日志和工具前缀）
            command: 可执行文件路径（如 "uvx"）
            args: 命令行参数
            env: 环境变量覆盖
        """
        self.name = name
        self.command = command
        self.args = args
        self.env = env
        self._process: subprocess.Popen | None = None
        self._id_counter = 0
        self._lock = threading.Lock()  # 写锁——stdin/stdout 必须串行
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    # ── 生命周期 ──────────────────────────────────────────

    def connect(self) -> None:
        """启动子进程并发送 initialize 握手。

        Raises:
            MCPClientError: 启动失败或握手超时/被拒。
        """
        if self._connected:
            return

        try:
            # WHY CREATE_NO_WINDOW: Windows 上避免弹出控制台窗口
            creationflags = 0
            if hasattr(subprocess, "CREATE_NO_WINDOW"):
                creationflags = subprocess.CREATE_NO_WINDOW

            self._process = subprocess.Popen(
                [self.command, *self.args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                creationflags=creationflags,
                env=self.env,
            )
        except FileNotFoundError as e:
            raise MCPClientError(
                f"MCP 服务器 '{self.name}' 启动失败——命令不存在: {self.command}。"
                f"请确认已安装: {self.command} {' '.join(self.args[:3])}..."
            ) from e
        except Exception as e:
            raise MCPClientError(
                f"MCP 服务器 '{self.name}' 启动异常: {e}"
            ) from e

        # 发送 initialize 请求
        try:
            init_result = self._send_request("initialize", {
                "protocolVersion": "0.1.0",
                "clientInfo": {"name": "orbit", "version": "0.11.0"},
                "capabilities": {},
            }, timeout=self.CONNECT_TIMEOUT)
        except MCPClientError:
            self._kill_process()
            raise

        server_info = init_result.get("serverInfo", {})
        logger.info(
            "mcp_connected",
            server=self.name,
            server_name=server_info.get("name", "unknown"),
            server_version=server_info.get("version", "unknown"),
        )
        self._connected = True

    def disconnect(self) -> None:
        """关闭连接——通知服务器后终止子进程。"""
        self._connected = False
        if self._process is None:
            return
        try:
            self._process.stdin.close()
        except Exception:
            pass
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=2)
        logger.info("mcp_disconnected", server=self.name)

    # ── MCP 方法 ──────────────────────────────────────────

    def list_tools(self) -> list[dict[str, Any]]:
        """获取服务器提供的工具列表。

        Returns:
            MCP 工具列表: [{name, description, inputSchema}, ...]
        """
        result = self._send_request("tools/list", {})
        return result.get("tools", [])

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """调用远程 MCP 工具并返回文本结果。

        Args:
            tool_name: 远程工具名（不含服务器前缀）
            arguments: 工具参数

        Returns:
            工具返回的文本内容（从 content[0].text 提取）
        """
        result = self._send_request(
            "tools/call",
            {"name": tool_name, "arguments": arguments},
            timeout=self.CALL_TIMEOUT,
        )
        # MCP 返回格式: {content: [{type: "text", text: "..."}]}
        content = result.get("content", [])
        if not content:
            return ""
        # 合并所有 text 块
        texts = []
        for item in content:
            if item.get("type") == "text":
                texts.append(item.get("text", ""))
        return "\n".join(texts)

    # ── 内部：JSON-RPC 2.0 通信 ──────────────────────────

    def _send_request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        timeout: int = 30,
    ) -> dict[str, Any]:
        """发送 JSON-RPC 2.0 请求并返回 result。

        WHY 锁: subprocess stdin/stdout 不是线程安全的，
        多个 Agent 并发调用同一 MCP 服务器时必须串行化。

        Args:
            method: JSON-RPC 方法名
            params: 参数字典
            timeout: 超时秒数

        Returns:
            响应的 result 字段

        Raises:
            MCPClientError: 通信失败/超时/服务器返回错误
        """
        if self._process is None:
            raise MCPClientError(f"MCP 服务器 '{self.name}' 未连接——请先调用 connect()")

        req_id = self._next_id()
        request = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params or {},
        }
        request_line = json.dumps(request, ensure_ascii=False) + "\n"

        with self._lock:
            # 写请求到子进程 stdin
            try:
                self._process.stdin.write(request_line)
                self._process.stdin.flush()
            except (BrokenPipeError, OSError) as e:
                self._connected = False
                raise MCPClientError(
                    f"MCP 服务器 '{self.name}' 进程已退出——无法写入请求"
                ) from e

            # 读响应——带超时的阻塞读
            start = time.time()
            while time.time() - start < timeout:
                # 检查子进程是否存活
                poll_result = self._process.poll()
                if poll_result is not None:
                    stderr_output = ""
                    try:
                        stderr_output = self._process.stderr.read() or ""
                    except Exception:
                        pass
                    self._connected = False
                    raise MCPClientError(
                        f"MCP 服务器 '{self.name}' 意外退出 (exit_code={poll_result})。"
                        f"stderr: {stderr_output[:500]}"
                    )

                try:
                    line = self._process.stdout.readline()
                except Exception as e:
                    raise MCPClientError(
                        f"MCP 服务器 '{self.name}' 读取响应失败: {e}"
                    ) from e

                if line:
                    break
                # 空行——子进程还没输出，继续等待
                time.sleep(0.01)
            else:
                raise MCPClientError(
                    f"MCP 服务器 '{self.name}' 响应超时 ({timeout}s)——方法: {method}"
                )

            # 解析响应
            try:
                response = json.loads(line)
            except json.JSONDecodeError as e:
                raise MCPClientError(
                    f"MCP 服务器 '{self.name}' 返回非法 JSON: {line[:200]}"
                ) from e

        # 检查 JSON-RPC 错误
        if "error" in response:
            error = response["error"]
            raise MCPClientError(
                f"MCP 调用失败: {error.get('message', str(error))} "
                f"(code={error.get('code', 'unknown')})"
            )

        return response.get("result", {})

    # ── 内部辅助 ──────────────────────────────────────────

    def _next_id(self) -> int:
        """自增请求 ID——JSON-RPC 2.0 要求唯一 id。"""
        self._id_counter += 1
        return self._id_counter

    def _kill_process(self) -> None:
        """强制终止子进程。"""
        if self._process is None:
            return
        try:
            self._process.kill()
            self._process.wait(timeout=2)
        except Exception:
            pass
        self._process = None
        self._connected = False
