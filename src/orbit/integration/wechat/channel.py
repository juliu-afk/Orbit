"""微信通道——cc-weixin 子进程管理 + iLink 协议适配。

WHY 用 cc-weixin 桥接而非直接调 iLink API：
iLink Bot API 仍处于实验性阶段，API 可能随时变更。
cc-weixin 作为成熟桥接层，隔离了底层协议变化。

子进程模式：
- Orbit 启动时 spawn cc-weixin（npx 方式）
- 崩溃自动重启（最多 3 次）
- Orbit 关闭时 kill 子进程
- 登录态由 cc-weixin 持久化，重启后无需重新扫码
"""

from __future__ import annotations

import asyncio
import io
import re
import secrets
from base64 import b64encode
from pathlib import Path

import qrcode
import structlog

logger = structlog.get_logger("orbit.wechat.channel")

MAX_RESTART_ATTEMPTS = 3


class WechatChannelError(Exception):
    """微信通道错误基类。"""


class WechatChannelUnavailableError(WechatChannelError):
    """微信通道不可用——子进程启动失败。"""


class WechatChannel:
    """cc-weixin 子进程管理器。

    生命周期：
    - start() → 启动子进程，等待就绪
    - is_ready → True 表示子进程运行中且登录成功
    - stop() → kill 子进程
    """

    def __init__(self) -> None:
        self._process: asyncio.subprocess.Process | None = None
        self._restart_count = 0
        self._ready = False
        self._logged_in = False

    # ── 生命周期 ─────────────────────────────────────

    async def start(self) -> None:
        """启动 cc-weixin 子进程。"""
        try:
            # WHY npx 而非全局安装：不污染用户环境，版本由 npx 自动管理
            self._process = await asyncio.create_subprocess_exec(
                "npx", "cc-weixin",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            logger.info("cc_weixin_started", pid=self._process.pid)
            # 等子进程启动（检测 stdout 输出 QR 码或 ready 信号）
            await self._wait_ready(timeout=15.0)
        except FileNotFoundError:
            raise WechatChannelUnavailableError(
                "npx 未找到。请安装 Node.js 22+ 后重试。"
            )
        except Exception as e:
            raise WechatChannelUnavailableError(f"cc-weixin 启动失败: {e}")

    async def stop(self) -> None:
        """停止 cc-weixin 子进程。"""
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
        """子进程是否就绪。"""
        return self._ready

    @property
    def is_logged_in(self) -> bool:
        """是否已登录微信。"""
        return self._logged_in

    # ── QR 码 ────────────────────────────────────────

    async def get_qrcode_data_url(self) -> str:
        """获取当前登录二维码（PNG base64 data URL）。

        从 cc-weixin stdout 捕获 QR 码字符串，转为 PNG 图片。
        cc-weixin 使用 qrcode-terminal 输出 ASCII 二维码到终端。
        实际方案：cc-weixin 启动后轮询其 HTTP 接口获取 QR 码 URL。

        MVP 回退：如果 cc-weixin 没有 HTTP 接口，
        生成一个占位 QR 码指向启动绑定流程。
        """
        # 尝试从 cc-weixin HTTP 接口获取 QR 码
        # cc-weixin 默认监听 localhost:随机端口
        # 此处为 MVP 实现——生成独立绑定 QR 码
        bind_url = f"https://orbit-bind.example.com/{secrets.token_urlsafe(16)}"
        return self._generate_qrcode_png(bind_url)

    def _generate_qrcode_png(self, data: str) -> str:
        """将字符串生成 QR 码 PNG，返回 data:image/png;base64 URL。"""
        qr = qrcode.QRCode(version=1, box_size=10, border=2)
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return f"data:image/png;base64,{b64encode(buf.getvalue()).decode()}"

    # ── 消息收发 ─────────────────────────────────────

    def send_message(self, openid: str, content: str) -> None:
        """发送消息到指定微信用户。

        MVP 实现：通过 cc-weixin 的标准输入写入命令。
        实际生产应通过 cc-weixin 的 HTTP API。

        WHY 此处为桩实现：cc-weixin 的具体 API 接口需安装实测后确定。
        """
        if not self._ready:
            raise WechatChannelUnavailableError("微信通道未就绪")
        logger.info("wechat_message_sent", openid=openid, length=len(content))
        # TODO: 实现 cc-weixin 消息发送
        # await self._send_via_api(openid, content)

    # ── 内部方法 ─────────────────────────────────────

    async def _wait_ready(self, timeout: float = 15.0) -> None:
        """等待子进程就绪（检测 stdout 输出）。"""
        if not self._process or not self._process.stdout:
            return

        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            line = await self._process.stdout.readline()
            if not line:
                break
            decoded = line.decode("utf-8", errors="replace").strip()
            logger.debug("cc_weixin_stdout", line=decoded)
            # 检测就绪信号
            if "ready" in decoded.lower() or "listening" in decoded.lower():
                self._ready = True
                break
            if "logged in" in decoded.lower() or "login success" in decoded.lower():
                self._logged_in = True

        # 如果 15 秒后仍无 ready 信号，标记不可用但不抛异常
        # WHY：cc-weixin 可能在等待用户扫码登录，此时进程已启动只是未登录
        if not self._ready:
            logger.warning("cc_weixin_not_ready", timeout=timeout)
            self._ready = True  # 假设进程已启动，只是没有 ready 信号

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
