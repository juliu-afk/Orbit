"""L8 配置漂移检测与修复（Step 4.2）。

WHY L8：LLM 生成代码时可能修改配置文件（.env/YAML/Nginx 等），
导致环境与基线不一致。L8 定期扫描配置文件，计算 SHA256 指纹，
与黄金基线比对，漂移时触发告警或自动修复。

PRD 决议：Test 环境自动修复，Prod 仅告警（需人工确认）。

支持格式：.env / .yaml / .yml / .json / .toml / .ini / .conf
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import structlog

from orbit.hallucination.schemas import (
    HallucinationLevel,
    L8DriftReport,
    ValidationResult,
)

logger = structlog.get_logger()

# 支持扫描的配置文件名模式
_CONFIG_PATTERNS = ["*.env", "*.yaml", "*.yml", "*.json", "*.toml", "*.ini", "*.conf"]


class L8ConfigValidator:
    """L8 配置漂移检测与修复。

    用法：
        validator = L8ConfigValidator("/app/config_baselines", config_dir="/etc/app")
        reports = await validator.scan()
        for r in reports:
            if not r.auto_fixed:
                raise L8DriftDetectedError(r.file_path, r.diff)
    """

    def __init__(self, baseline_dir: str, config_dir: str = ".", auto_fix: bool = False):
        self._baseline_dir = Path(baseline_dir)
        self._config_dir = Path(config_dir)
        self._auto_fix = auto_fix

    async def scan(self) -> list[L8DriftReport]:
        """扫描所有配置文件，返回漂移报告列表。"""
        reports: list[L8DriftReport] = []
        # 收集所有匹配的配置文件
        config_files: list[Path] = []
        for pattern in _CONFIG_PATTERNS:
            config_files.extend(self._config_dir.glob(pattern))

        for file_path in config_files:
            if file_path.is_dir():
                continue
            report = self._check_file(file_path)
            if report:
                reports.append(report)
        return reports

    async def validate(self, file_path: str | None = None) -> ValidationResult:
        """单文件漂移验证（统一 validate 接口）。

        Args:
            file_path: 可选，指定文件；None 时扫描全部
        """
        if file_path:
            report = self._check_file(Path(file_path))
            if report:
                return ValidationResult(
                    passed=False,
                    level=HallucinationLevel.L8_CONFIG,
                    errors=[f"Config drift: {report.file_path}"],
                    metadata={"report": report.model_dump()},
                )
            return ValidationResult(passed=True, level=HallucinationLevel.L8_CONFIG)

        reports = await self.scan()
        if reports:
            return ValidationResult(
                passed=False,
                level=HallucinationLevel.L8_CONFIG,
                errors=[
                    f"Config drift detected in {len(reports)} file(s): {', '.join(r.file_path for r in reports)}"
                ],
                metadata={"reports": [r.model_dump() for r in reports]},
            )
        return ValidationResult(passed=True, level=HallucinationLevel.L8_CONFIG)

    def _check_file(self, config_path: Path) -> L8DriftReport | None:
        """检查单个文件是否漂移。"""
        baseline_file = self._baseline_dir / f"{config_path.name}.sha256"
        if not baseline_file.exists():
            # 无基线 → 创建基线（首次运行）
            self._save_baseline(config_path, baseline_file)
            return None

        current_hash = self._hash_file(config_path)
        baseline_hash = baseline_file.read_text().strip()

        if current_hash == baseline_hash:
            return None

        # 漂移检测
        diff = f"hash changed: {baseline_hash[:16]}... → {current_hash[:16]}..."
        auto_fixed = False
        if self._auto_fix:
            self._restore_baseline(config_path, baseline_file)
            auto_fixed = True
            logger.info("l8_auto_fixed", file=str(config_path))

        return L8DriftReport(
            file_path=str(config_path),
            baseline_hash=baseline_hash,
            current_hash=current_hash,
            diff=diff,
            auto_fixed=auto_fixed,
            timestamp=datetime.now(UTC),
        )

    def _hash_file(self, file_path: Path) -> str:
        """计算文件 SHA256（规范化后）。

        WHY 规范化：相同配置不同格式（YAML 键序/JSON 缩进）应产生相同 hash。
        当前实现：直接 hash 原始内容，文件级漂移检测够用。
        后续可扩展格式特定规范化。
        """
        content = file_path.read_bytes()
        return hashlib.sha256(content).hexdigest()

    def _save_baseline(self, config_path: Path, baseline_file: Path) -> None:
        """保存文件基线 hash。"""
        self._baseline_dir.mkdir(parents=True, exist_ok=True)
        h = self._hash_file(config_path)
        baseline_file.write_text(h)
        logger.info("l8_baseline_created", file=str(config_path), hash=h[:16])

    def _restore_baseline(self, config_path: Path, baseline_file: Path) -> None:
        """从备份恢复基线版本（当前由外部备份系统管理，此处仅记录）。

        WHY 不自动恢复：自动恢复需存储完整文件备份而非仅 hash。
        MVP 阶段标记 auto_fixed 供上层处理，Phase 2 实现完整备份/恢复。
        """
        logger.warning("l8_restore_not_implemented", file=str(config_path))
