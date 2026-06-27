"""输出验证器 (Phase 2 AC10).

验证 Merge 结果是否符合 <200 行 + <10KB 约束。
"""

from __future__ import annotations

from orbit.dream.models import DreamConfig, DreamResult, DreamStatus


class DreamVerifier:
    """验证 dream 输出——尺寸检查 + 路径检查."""

    def __init__(self, config: DreamConfig | None = None) -> None:
        self._config = config or DreamConfig()

    def verify(self, content: str, output_path: str) -> DreamResult:
        """验证合并后的内容.

        Returns:
            DreamResult——包含验证状态和错误信息
        """
        errors: list[str] = []

        # 行数检查
        lines = content.count("\n") + (0 if content.endswith("\n") else 1)
        if lines > self._config.max_output_lines:
            errors.append(f"行数超限: {lines} > {self._config.max_output_lines}")

        # 字节数检查
        content_bytes = len(content.encode("utf-8"))
        if content_bytes > self._config.max_output_bytes:
            errors.append(f"字节数超限: {content_bytes} > {self._config.max_output_bytes}")

        if errors:
            return DreamResult(
                status=DreamStatus.REJECTED,
                output_path=output_path,
                lines=lines,
                bytes=content_bytes,
                errors=errors,
                verification_message="; ".join(errors),
            )

        return DreamResult(
            status=DreamStatus.COMPLETE,
            output_path=output_path,
            lines=lines,
            bytes=content_bytes,
            verification_message=f"通过——{lines} 行, {content_bytes} 字节",
        )
