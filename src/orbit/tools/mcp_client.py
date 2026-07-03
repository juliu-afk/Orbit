"""MCP 客户端——通过 stdio 子进程连接外部 MCP 服务器。

WHY 手写 JSON-RPC 2.0 而非引入 MCP SDK：MVP 零额外依赖，
与现有 mcp_server.py 策略一致。协议足够简单——5 个方法。

协议规范：https://spec.modelcontextprotocol.io/
对标：Claude Code `claude mcp add` 机制
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
from typing import Any

import structlog

logger = structlog.get_logger("orbit.tools.mcp_client")

# MCP 协议版本——统一常量，避免硬编码散落各处
_MCP_PROTOCOL_VERSION = "0.1.0"


class MCPClientError(Exception):
    """MCP 客户端错误——连接失败/超时/协议错误。"""


class MCPClientConnection:
    """MCP JSON-RPC 2.0 客户端——管理一个外部 MCP 服务器的生命周期。

    用法::

        conn = MCPClientConnection("serena", "serena", ["start-mcp-server"])
        conn.connect()
        tools = conn.list_tools()
        result = conn.call_tool("find_symbol", {"name_path": "MyClass"})
        conn.disconnect()
    """

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
            command: 可执行文件路径（如 "serena"）
            args: 命令行参数
            env: 额外环境变量（合并到父进程环境，而非替换）
        """
        self.name = name
        self.command = command
        self.args = args
        # WHY merge: 替换父进程环境会丢失 PATH/SYSTEMROOT/COMSPEC
        self.env = os.environ.copy()
        if env:
            self.env.update(env)
        self._process: subprocess.Popen | None = None
        self._id_counter = 0
        self._lock = threading.Lock()
        self._connected = False
        # 后台 stdout 读取——避免 readline() 阻塞导致超时无效
        self._stdout_queue: queue.Queue[tuple[bool, str | None]] = queue.Queue()
        self._stdout_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None

    @property
    def connected(self) -> bool:
        return self._connected

    # ── 生命周期 ──────────────────────────────────────────

    def connect(self) -> None:
        """启动子进程并发送 initialize 握手。

        Raises:
            MCPClientError: 启动失败或握手超时/被拒。
        """
        # WHY lock: 防双线程同时 connect() 导致第一个 Popen 泄漏为孤儿进程
        with self._lock:
            if self._connected:
                return

            try:
                creationflags = 0
                startupinfo = None
                if hasattr(subprocess, "CREATE_NO_WINDOW"):
                    creationflags = subprocess.CREATE_NO_WINDOW
                # WHY STARTUPINFO: 配合 CREATE_NO_WINDOW 彻底隐藏控制台窗口，
                # 某些 Windows 配置下仅靠 creationflags 仍会短暂闪窗
                if hasattr(subprocess, "STARTUPINFO"):
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = subprocess.SW_HIDE

                self._process = subprocess.Popen(
                    [self.command, *self.args],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    creationflags=creationflags,
                    startupinfo=startupinfo,
                    env=self.env,
                )
            except FileNotFoundError as e:
                raise MCPClientError(
                    f"MCP 服务器 '{self.name}' 启动失败——命令不存在: {self.command}。"
                    f"请确认已安装: {self.command}"
                ) from e
            except Exception as e:
                raise MCPClientError(
                    f"MCP 服务器 '{self.name}' 启动异常: {e}"
                ) from e

            # WHY 后台读 stdout: Windows 上 select() 对管道无效，
            # readline() 永久阻塞→超时机制失效。后台线程读→入队→queue.get(timeout)
            self._start_stdout_reader()
            # WHY 排空 stderr: 管道缓冲 ~64KB，写满后子进程阻塞→死锁
            self._start_stderr_drainer()

        # 握手不持锁——_send_request 内部获取锁
        try:
            init_result = self._send_request("initialize", {
                "protocolVersion": _MCP_PROTOCOL_VERSION,
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
        """关闭连接——通知服务器后终止子进程。

        WHY lock: stdin/stdout/stderr 操作必须串行化，避开 _send_request 进行中的 I/O。
        """
        with self._lock:
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
            self._process = None
        logger.info("mcp_disconnected", server=self.name)

    # ── MCP 方法 ──────────────────────────────────────────

    def list_tools(self) -> list[dict[str, Any]]:
        """获取服务器提供的工具列表。"""
        result = self._send_request("tools/list", {})
        return result.get("tools", [])

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """调用远程 MCP 工具并返回文本结果。"""
        result = self._send_request(
            "tools/call",
            {"name": tool_name, "arguments": arguments},
            timeout=self.CALL_TIMEOUT,
        )
        content = result.get("content", [])
        if not content:
            return ""
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

        WHY 锁: subprocess stdin/stdout 非线程安全，并发调用必须串行化。
        WHY 队列: 后台线程 readline→入队，主线程 queue.get(timeout) 实现真正超时。
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
            try:
                self._process.stdin.write(request_line)
                self._process.stdin.flush()
            except (BrokenPipeError, OSError) as e:
                self._connected = False
                raise MCPClientError(
                    f"MCP 服务器 '{self.name}' 进程已退出——无法写入请求"
                ) from e

            # 从后台线程队列读——真正可超时
            try:
                finished, line = self._stdout_queue.get(timeout=timeout)
            except queue.Empty:
                raise MCPClientError(
                    f"MCP 服务器 '{self.name}' 响应超时 ({timeout}s)——方法: {method}"
                )

            if not finished:
                poll_result = self._process.poll()
                self._connected = False
                raise MCPClientError(
                    f"MCP 服务器 '{self.name}' 意外退出 (exit_code={poll_result})"
                )

            if line is None:
                raise MCPClientError(
                    f"MCP 服务器 '{self.name}' 返回空响应"
                )

        # 解析（锁外——不涉及 I/O）
        try:
            response = json.loads(line)
        except json.JSONDecodeError as e:
            raise MCPClientError(
                f"MCP 服务器 '{self.name}' 返回非法 JSON: {line[:200]}"
            ) from e

        # WHY 校验 id: 防服务端乱序响应→请求-响应错配
        response_id = response.get("id")
        if response_id != req_id:
            raise MCPClientError(
                f"MCP 服务器 '{self.name}' 响应 id 不匹配——"
                f"期望 {req_id}，实际 {response_id}"
            )

        if "error" in response:
            error = response["error"]
            raise MCPClientError(
                f"MCP 调用失败: {error.get('message', str(error))} "
                f"(code={error.get('code', 'unknown')})"
            )

        return response.get("result", {})

    # ── 后台 I/O 线程 ─────────────────────────────────────

    def _start_stdout_reader(self) -> None:
        """后台线程——持续读 stdout→入队，解决 readline() 阻塞问题。"""
        def _reader() -> None:
            try:
                while self._process and self._process.stdout:
                    line = self._process.stdout.readline()
                    if line:
                        self._stdout_queue.put((True, line))
                    elif self._process.poll() is not None:
                        # EOF——子进程已退出
                        self._stdout_queue.put((False, None))
                        break
                    else:
                        # readline() 返回空但进程未退出——极罕见边缘情况
                        # 短暂 sleep 防止 busy-loop
                        import time as _time
                        _time.sleep(0.01)
            except Exception as e:
                logger.debug("mcp_stdout_reader_error", server=self.name, error=str(e))
                self._stdout_queue.put((False, None))

        self._stdout_thread = threading.Thread(target=_reader, daemon=True)
        self._stdout_thread.start()

    def _start_stderr_drainer(self) -> None:
        """后台线程——持续排空 stderr，防缓冲区满→子进程阻塞→死锁。"""
        def _drainer() -> None:
            try:
                while self._process and self._process.stderr:
                    chunk = self._process.stderr.read(4096)
                    if not chunk:
                        break
            except Exception as e:
                logger.debug("mcp_stderr_drain_error", server=self.name, error=str(e))

        self._stderr_thread = threading.Thread(target=_drainer, daemon=True)
        self._stderr_thread.start()

    # ── 内部辅助 ──────────────────────────────────────────

    def _next_id(self) -> int:
        self._id_counter += 1
        return self._id_counter

    def _kill_process(self) -> None:
        if self._process is None:
            return
        try:
            self._process.kill()
            self._process.wait(timeout=2)
        except Exception:
            pass
        self._process = None
        self._connected = False
