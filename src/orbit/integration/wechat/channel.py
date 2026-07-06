"""微信通道——cc-weixin 子进程管理 + iLink 协议适配。

WHY 用 cc-weixin 桥接而非直接调 iLink API：
iLink Bot API 仍处于实验性阶段，API 可能随时变更。
cc-weixin 作为成熟桥接层，隔离了底层协议变化。

子进程模式：
- Orbit 启动时 spawn cc-weixin（npx 方式）
- 从 stdout 解析 cc-weixin 本地 HTTP API 地址
- QR 码和消息发送通过 HTTP API 调用（不再用占位符）
- 崩溃自动重启（最多 3 次）
- 登录态由 cc-weixin 持久化，重启后无需重新扫码
"""

from __future__ import annotations

import asyncio
import io
import re
from base64 import b64encode
from urllib.parse import urljoin

import httpx
import qrcode
import structlog

logger = structlog.get_logger("orbit.wechat.channel")

MAX_RESTART_ATTEMPTS = 3
CC_WEIXIN_STARTUP_TIMEOUT = 30.0  # 等待 cc-weixin 就绪的超时（秒）
CC_WEIXIN_API_TIMEOUT = 10.0  # HTTP API 调用超时（秒）

# 匹配 cc-weixin stdout 中的监听地址行
# cc-weixin 典型输出: "listening on http://127.0.0.1:45678"
_LISTEN_PATTERN = re.compile(r"listening on (https?://[\d.]+:\d+)", re.I)


class WechatChannelError(Exception):
    """微信通道错误基类。"""


class WechatChannelUnavailableError(WechatChannelError):
    """微信通道不可用——子进程启动失败。"""


class WechatChannel:
    """cc-weixin 子进程管理器。

    生命周期：
    - start() → 启动子进程，解析 API 地址
    - is_ready → True 表示子进程运行中且 API 地址已解析
    - is_logged_in → True 表示已登录微信
    - stop() → kill 子进程
    """

    def __init__(self) -> None:
        self._process: asyncio.subprocess.Process | None = None
        self._restart_count = 0
        self._ready = False
        self._logged_in = False
        self._api_base: str = ""  # cc-weixin 本地 HTTP API 地址
        self._http: httpx.AsyncClient | None = None  # 复用 HTTP 连接

    # ── 生命周期 ─────────────────────────────────────

    async def start(self) -> None:
        """启动 cc-weixin 子进程，解析其 HTTP API 地址。"""
        try:
            # WHY npx 而非全局安装：不污染用户环境，版本由 npx 自动管理
            self._process = await asyncio.create_subprocess_exec(
                "npx", "cc-weixin",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,  # cc-weixin 把日志打到 stderr
            )
            logger.info("cc_weixin_started", pid=self._process.pid)
            await self._wait_ready(timeout=CC_WEIXIN_STARTUP_TIMEOUT)
        except FileNotFoundError:
            raise WechatChannelUnavailableError(
                "npx 未找到。请安装 Node.js 22+ 后重试。"
            )
        except Exception as e:
            raise WechatChannelUnavailableError(f"cc-weixin 启动失败: {e}")

    async def stop(self) -> None:
        """停止 cc-weixin 子进程 + 关闭 HTTP 客户端。"""
        if self._http:
            await self._http.aclose()
            self._http = None
        if self._process and self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
            logger.info("cc_weixin_stopped")
        self._ready = False
        self._logged_in = False

    # ── 状态查询 ─────────────────────────────────────

    @property
    def is_ready(self) -> bool:
        """子进程是否就绪且 API 地址已解析。"""
        return self._ready and bool(self._api_base)

    @property
    def is_logged_in(self) -> bool:
        """是否已登录微信。"""
        return self._logged_in

    # ── QR 码 ────────────────────────────────────────

    async def get_qrcode_data_url(self) -> str:
        """获取当前登录二维码（PNG base64 data URL）。

        优先从 cc-weixin HTTP API 获取 QR 码数据，
        API 不可用时自己生成指向绑定流程的 QR 码。
        """
        # 尝试从 cc-weixin HTTP API 获取 QR 码
        if self._api_base and self._http:
            try:
                qr_data = await self._fetch_qrcode_from_api()
                if qr_data:
                    return self._render_qrcode_png(qr_data)
            except Exception as e:
                logger.warning("cc_weixin_qrcode_api_failed", error=str(e))

        # 回退：生成指向 Orbit 本地回调的绑定 URL
        # 此 QR 码由 Orbit 自己生成，用于绑定流程中展示
        import secrets
        bind_token = secrets.token_urlsafe(16)
        bind_url = f"http://127.0.0.1:18888/api/v1/wechat/callback?token={bind_token}"
        logger.info("qrcode_fallback_generated")
        return self._render_qrcode_png(bind_url)

    async def _fetch_qrcode_from_api(self) -> str | None:
        """从 cc-weixin HTTP API 获取 QR 码数据。返回 QR 内容字符串或 None。"""
        if not self._http:
            return None
        # cc-weixin 典型 API: GET /qrcode → { "qrcode": "https://ilinkai.weixin.qq.com/..." }
        resp = await self._http.get(
            urljoin(self._api_base, "/qrcode"),
            timeout=CC_WEIXIN_API_TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("qrcode") or data.get("url") or data.get("data")
        logger.debug("cc_weixin_qrcode_http_error", status=resp.status_code)
        return None

    @staticmethod
    def _render_qrcode_png(data: str) -> str:
        """将字符串渲染为 QR 码 PNG，返回 data:image/png;base64 URL。"""
        qr = qrcode.QRCode(version=1, box_size=10, border=2)
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return f"data:image/png;base64,{b64encode(buf.getvalue()).decode()}"

    # ── 消息收发 ─────────────────────────────────────

    async def send_message(self, openid: str, content: str) -> None:
        """通过 cc-weixin HTTP API 发送消息到指定微信用户。

        cc-weixin 典型 API: POST /send { openid, content } → { ok: true }
        失败时抛 WechatChannelUnavailableError。
        """
        if not self._ready or not self._api_base:
            raise WechatChannelUnavailableError("微信通道未就绪")

        if not self._http:
            self._http = self._create_http_client()

        try:
            resp = await self._http.post(
                urljoin(self._api_base, "/send"),
                json={"openid": openid, "content": content},
                timeout=CC_WEIXIN_API_TIMEOUT,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("ok") or data.get("success"):
                    logger.debug("wechat_message_sent", openid=openid, length=len(content))
                    return
            # API 返回非成功状态
            body = resp.text[:200]
            logger.warning("wechat_send_failed", status=resp.status_code, body=body)
            raise WechatChannelUnavailableError(f"cc-weixin 返回 {resp.status_code}: {body}")
        except httpx.TimeoutException:
            raise WechatChannelUnavailableError("cc-weixin API 超时")
        except httpx.RequestError as e:
            raise WechatChannelUnavailableError(f"cc-weixin API 请求失败: {e}")

    # ── 内部方法 ─────────────────────────────────────

    def _create_http_client(self) -> httpx.AsyncClient:
        """创建复用的 HTTP 客户端。"""
        return httpx.AsyncClient(
            base_url=self._api_base,
            timeout=CC_WEIXIN_API_TIMEOUT,
        )

    async def _wait_ready(self, timeout: float = CC_WEIXIN_STARTUP_TIMEOUT) -> None:
        """等待子进程就绪——读取 stdout 解析监听地址和登录状态。"""
        if not self._process or not self._process.stdout:
            return

        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            line_bytes = await asyncio.wait_for(
                self._process.stdout.readline(),
                timeout=min(5.0, max(0.5, deadline - asyncio.get_event_loop().time())),
            )
            if not line_bytes:
                break

            decoded = line_bytes.decode("utf-8", errors="replace").strip()
            logger.debug("cc_weixin_stdout", line=decoded)

            # 解析监听地址——cc-weixin 格式："listening on http://127.0.0.1:XXXXX"
            if not self._api_base:
                match = _LISTEN_PATTERN.search(decoded)
                if match:
                    self._api_base = match.group(1)
                    self._ready = True
                    self._http = self._create_http_client()
                    logger.info("cc_weixin_api_parsed", base=self._api_base)

            # 检测登录状态
            if "logged in" in decoded.lower() or "login success" in decoded.lower():
                self._logged_in = True
                logger.info("cc_weixin_logged_in")

        if not self._api_base:
            logger.warning("cc_weixin_no_listen_addr", timeout=timeout)
            # 进程已在运行但未解析到 API 地址——标记为 ready 允许后续重试
            self._ready = True

    async def _restart_if_needed(self) -> None:
        """子进程崩溃时尝试重启。"""
        if self._restart_count >= MAX_RESTART_ATTEMPTS:
            raise WechatChannelUnavailableError(
                f"cc-weixin 重启 {MAX_RESTART_ATTEMPTS} 次均失败，已放弃"
            )

        self._restart_count += 1
        logger.warning("cc_weixin_restarting", attempt=self._restart_count)
        await self.stop()
        await asyncio.sleep(2.0)
        await self.start()
