"""配置图谱引擎（Step 3.3）。

解析配置文件（.env/yml/json/nginx/ini），计算 SHA256 指纹，
检测漂移（与黄金基线对比），自动修复（Test 环境回滚到基线）。

为防幻觉 L8（配置漂移检测）提供数据支撑。
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

import structlog
import yaml
from dotenv import dotenv_values
from sqlalchemy.ext.asyncio import async_sessionmaker

from orbit.graph.engines.base import GraphEngineBase
from orbit.graph.models.nodes import ConfigNode

logger = structlog.get_logger()

# 支持的配置文件扩展名
SUPPORTED_EXTENSIONS = {".env", ".yml", ".yaml", ".json", ".ini", ".conf"}
# 基线表（内存版，后续可换持久化）
_config_baselines: dict[str, dict] = {}


class ConfigGraphError(Exception):
    """配置图谱错误基类。"""


class ParseConfigError(ConfigGraphError):
    """配置文件解析失败。"""


class ConfigGraphEngine(GraphEngineBase):
    """配置图谱引擎。

    接口：
    - compute_hash(file_path) → str：SHA256
    - scan_and_index(directory) → int：扫描并索引
    - detect_drift() → list[dict]：检测漂移
    - auto_fix(file_path) → bool：自动修复（Test 环境）
    """

    def __init__(
        self,
        session_factory: async_sessionmaker,
        base_dir: str,
        env: str = "dev",
        backup_dir: str | None = None,
    ):
        super().__init__(session_factory)
        self.base_dir = Path(base_dir)
        self.env = env
        self.backup_dir = Path(backup_dir) if backup_dir else self.base_dir / ".backups"

    def _is_config_file(self, path: Path) -> bool:
        """判断是否为支持的配置文件。

        WHY .env 特殊处理：Path('.env').suffix 返回 ''（无扩展名分隔），
        需按文件名判断。.yml/.yaml/.json/.ini 按扩展名。
        """
        if path.name == ".env":
            return True
        if path.suffix in SUPPORTED_EXTENSIONS:
            return True
        # nginx.conf / php.ini 等按文件名匹配
        return path.name in {"nginx.conf", "php.ini", "my.cnf"}

    def _parse_file(self, file_path: Path) -> str:
        """解析配置文件，返回规范化字符串（用于 hash）。

        WHY 规范化：相同配置不同格式（空格/顺序）应产生相同 hash。
        """
        try:
            if file_path.name == ".env" or ".env" in file_path.name:
                # .env 用 dotenv 解析（dict 排序后 JSON 化）
                vals = dotenv_values(file_path)
                return json.dumps(dict(sorted(vals.items())), ensure_ascii=False)
            if file_path.suffix in (".yml", ".yaml"):
                with file_path.open(encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                return json.dumps(data, sort_keys=True, ensure_ascii=False)
            if file_path.suffix == ".json":
                with file_path.open(encoding="utf-8") as f:
                    data = json.load(f)
                return json.dumps(data, sort_keys=True, ensure_ascii=False)
            if file_path.suffix == ".ini" or file_path.name in {"php.ini", "my.cnf"}:
                # ini 类用 configparser 解析（简化：保留原始文本去多余空白）
                text = file_path.read_text(encoding="utf-8")
                return re.sub(r"\s+", " ", text).strip()
            if "nginx.conf" in file_path.name or file_path.suffix == ".conf":
                text = file_path.read_text(encoding="utf-8")
                return re.sub(r"\s+", " ", text).strip()
            raise ParseConfigError(f"不支持的文件类型: {file_path}")
        except ParseConfigError:
            raise
        except Exception as e:
            raise ParseConfigError(f"解析 {file_path} 失败: {e}") from e

    def compute_hash(self, file_path: Path | str) -> str:
        """SC3: 计算配置文件 SHA256 指纹。"""
        path = Path(file_path)
        content = self._parse_file(path)
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    async def scan_and_index(self) -> int:
        """扫描 base_dir，索引所有配置文件。返回文件数。

        WHY 每次扫描清空基线：避免多个实例/测试间基线残留导致漂移误报。
        基线只在本次扫描周期内有效，下次扫描重建。
        """
        _config_baselines.clear()
        if not self.base_dir.exists():
            logger.warning("config_dir_not_found", dir=str(self.base_dir))
            return 0
        count = 0
        for path in self.base_dir.rglob("*"):
            if path.is_file() and self._is_config_file(path):
                try:
                    await self._index_config_file(path)
                    count += 1
                except ParseConfigError as e:
                    logger.warning("config_parse_skipped", file=str(path), error=str(e))
        logger.info("config_graph_indexed", files=count)
        return count

    async def _index_config_file(self, path: Path) -> None:
        """索引单个配置文件到 ConfigNode + 建立基线。"""
        file_hash = self.compute_hash(path)
        import uuid

        node_id = uuid.uuid4().hex
        content = path.read_text(encoding="utf-8")
        await self.upsert_node(
            ConfigNode,
            node_id,
            name=path.name,
            type="config",
            hash=file_hash,
            file_path=str(path),
            env=self.env,
            meta={"size": len(content)},
        )
        # 建立黄金基线（首次扫描时记录）
        key = str(path)
        if key not in _config_baselines:
            _config_baselines[key] = {
                "hash": file_hash,
                "content": content,
                "file_path": str(path),
            }

    async def detect_drift(self) -> list[dict]:
        """SC1: 检测配置漂移。返回漂移文件列表。"""
        drifts = []
        for file_path_str, baseline in _config_baselines.items():
            path = Path(file_path_str)
            if not path.exists():
                drifts.append({"file": file_path_str, "expected": baseline["hash"], "actual": None})
                continue
            try:
                current_hash = self.compute_hash(path)
                if current_hash != baseline["hash"]:
                    drifts.append(
                        {
                            "file": file_path_str,
                            "expected": baseline["hash"],
                            "actual": current_hash,
                        }
                    )
            except ParseConfigError as e:
                logger.warning("drift_check_failed", file=file_path_str, error=str(e))
        return drifts

    async def auto_fix(self, file_path: str) -> bool:
        """SC2: 自动修复（用基线内容覆盖）。

        WHY 生产环境禁止自动修复：仅告警，人工介入（PRD 待定决议）。
        """
        if self.env == "prod":
            raise ConfigGraphError("生产环境禁止自动修复，仅告警")
        path = Path(file_path)
        baseline = _config_baselines.get(str(path))
        if baseline is None:
            logger.warning("no_baseline_for_fix", file=file_path)
            return False
        # 备份原文件（PRD Q1：修复前必须备份）
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = self.backup_dir / f"{path.name}.bak"
        if path.exists():
            shutil.copy2(path, backup_path)
        # 用基线覆盖
        path.write_text(baseline["content"], encoding="utf-8")
        logger.info("config_auto_fixed", file=file_path, backup=str(backup_path))
        return True

    def update_baseline(self, file_path: str) -> None:
        """更新黄金基线（人工触发，PRD Q2）。"""
        path = Path(file_path)
        content = path.read_text(encoding="utf-8")
        _config_baselines[str(path)] = {
            "hash": self.compute_hash(path),
            "content": content,
            "file_path": str(path),
        }
        logger.info("baseline_updated", file=file_path)
