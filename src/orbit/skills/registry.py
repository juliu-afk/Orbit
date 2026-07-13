"""SkillRegistry——通用 Skill 注册中心。

扫描 SKILL.md 文件 → 注册为 ChatSkill → 提供精确匹配 + 自然语言模糊匹配。
支持 CRUD、版本历史、热更新。

WHY 独立于 ComposeParser: ComposeParser 只服务于 spec→task 管道，
SkillRegistry 面向聊天框实时交互——需要自然语言匹配、置信度评分、热更新。
两者共享 SKILL.md 格式但用途不同。
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
import yaml

from orbit.skills.models import (
    ChatMode,
    ChatSkill,
    SkillMatchResult,
    SkillTriggerType,
    SkillVersion,
)

if TYPE_CHECKING:
    from orbit.skills.watcher import SkillWatcher

logger = structlog.get_logger("orbit.skills.registry")

# YAML frontmatter 正则: ---\n...\n---
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

# 默认 Skill 定义目录
_SKILLS_DEFINITIONS_DIR = Path(__file__).parent / "definitions"
# Compose 已有 Skill 目录
_COMPOSE_SKILLS_DIR = Path(__file__).parent.parent / "compose" / "skills"

# ── 自然语言匹配——关键词权重 ────────────────────────
# WHY 启发式评分: embed 语义匹配是后续优化项，先用关键词做快速意图检测。
# 匹配时按触发词命中数 + 触发词长度加权计算置信度。


class SkillRegistry:
    """通用 Skill 注册中心。

    Usage:
        registry = SkillRegistry()
        registry.discover()                    # 启动时扫描
        skill = registry.find_by_slash("review")   # /review → Skill
        matches = registry.match_by_text("帮我审查代码")  # 自然语言 → 候选
        registry.start_watcher()               # 启动热更新
    """

    def __init__(
        self,
        skills_dirs: list[Path] | None = None,
    ) -> None:
        self._skills: dict[str, ChatSkill] = {}
        self._version_history: dict[str, list[SkillVersion]] = {}
        self._skills_dirs = skills_dirs or [
            _SKILLS_DEFINITIONS_DIR,
            _COMPOSE_SKILLS_DIR,
        ]
        self._watcher: SkillWatcher | None = None

    # ── 发现 + 加载 ─────────────────────────────────

    def discover(self) -> list[ChatSkill]:
        """扫描所有 Skill 目录，解析 SKILL.md 文件。

        已有的 compose skills/ 自动标记 is_chat_skill=True 后
        可被聊天框调用。definitions/ 目录放聊天框专用 Skill。
        """
        if self._skills:
            return list(self._skills.values())

        for skills_dir in self._skills_dirs:
            if not skills_dir.exists():
                logger.debug("skills_dir_not_found", path=str(skills_dir))
                continue

            for md_file in sorted(skills_dir.glob("*.md")):
                try:
                    skill = self._load_skill_file(md_file)
                    if skill:
                        self._skills[skill.name] = skill
                        logger.debug("skill_loaded", name=skill.name, version=skill.version)
                except (OSError, UnicodeDecodeError, ValueError) as e:
                    logger.warning("skill_load_failed", file=str(md_file), error=str(e))

        logger.info("skills_discovered", count=len(self._skills))
        return list(self._skills.values())

    def reload(self, name: str | None = None) -> None:
        """热更新——重新解析指定 Skill 或全部 Skill。

        Args:
            name: None=全部重载，指定名=单个重载
        """
        if name is not None:
            skill = self._skills.get(name)
            if skill and skill.path:
                try:
                    new_skill = self._load_skill_file(Path(skill.path))
                    if new_skill:
                        self._save_version(name, new_skill.version, "热更新")
                        self._skills[name] = new_skill
                        logger.info("skill_reloaded", name=name, version=new_skill.version)
                except Exception as e:
                    logger.error("skill_reload_failed", name=name, error=str(e))
        else:
            # 全部重载——清缓存重新扫描
            old_skills = dict(self._skills)
            self._skills.clear()
            self.discover()
            # 恢复版本历史（不丢失）
            for name, skill in self._skills.items():
                if name in old_skills and skill.version != old_skills[name].version:
                    self._save_version(name, skill.version, "全量热更新")
            logger.info("skills_full_reload", count=len(self._skills))

    # ── 查询 ────────────────────────────────────────

    def find_by_slash(self, name: str) -> ChatSkill | None:
        """精确匹配 /xxx 命令 → Skill。

        Args:
            name: 斜杠后的字符串，如 "review"、"code-review"
        """
        if not self._skills:
            self.discover()
        # 精确匹配 + 前缀匹配
        clean = name.lstrip("/").strip().lower()
        for skill_name, skill in self._skills.items():
            if not skill.is_chat_skill:
                continue
            # 匹配 name 本身或其简化形式
            skill_short = skill_name.replace("compose:", "").replace(":", "-")
            if clean == skill_short or clean == skill_name.lower():
                return skill
        return None

    def match_by_text(self, text: str) -> list[SkillMatchResult]:
        """自然语言 → 候选 Skill 列表（按置信度降序）。

        策略: 关键词命中 + 触发词长度加权。
        后续可升级为 embed 语义匹配。

        Args:
            text: 用户原始输入（中文/英文）
        Returns:
            按 confidence 降序排列的匹配结果。
            空列表 = 无匹配。
        """
        if not self._skills:
            self.discover()

        text_lower = text.lower()
        results: list[SkillMatchResult] = []

        for name, skill in self._skills.items():
            if not skill.is_chat_skill:
                continue
            if not skill.triggers:
                continue

            # 计算命中数 + 最长触发词长度
            hits = 0
            best_trigger = ""
            best_len = 0
            for trigger in skill.triggers:
                t = trigger.lower()
                if t in text_lower:
                    hits += 1
                    if len(t) > best_len:
                        best_len = len(t)
                        best_trigger = trigger

            if hits == 0:
                continue

            # 置信度 = 基础 0.6（任一触发词命中）+ 长度奖励 + 多命中奖励
            # WHY 基础 0.6: ≥ 默认阈值 0.4-0.7 区间，确保单触发词命中可触发
            base = 0.6
            # 最长命中触发词 ≥ 4 字 → +0.2；≥ 2 字 → +0.1
            len_bonus = 0.2 if best_len >= 4 else (0.1 if best_len >= 2 else 0)
            # 命中多个触发词 → 每个额外命中 +0.1（最多 +0.3）
            multi_bonus = min(0.3, (hits - 1) * 0.1)
            confidence = min(1.0, base + len_bonus + multi_bonus)

            results.append(SkillMatchResult(
                skill=skill,
                confidence=round(confidence, 2),
                trigger_type=SkillTriggerType.NATURAL,
                matched_by=best_trigger,
            ))

        # 按置信度降序
        results.sort(key=lambda r: r.confidence, reverse=True)
        return results

    def list_all(self) -> list[ChatSkill]:
        """返回所有聊天框可调用的 Skill（供 API 列表 + 前端补全）。"""
        if not self._skills:
            self.discover()
        return [s for s in self._skills.values() if s.is_chat_skill]

    def get(self, name: str) -> ChatSkill | None:
        """按名称获取单个 Skill。"""
        if not self._skills:
            self.discover()
        return self._skills.get(name)

    # ── CRUD ────────────────────────────────────────

    def create(self, name: str, data: dict) -> ChatSkill:
        """创建新 Skill——写 SKILL.md 到 definitions/ 目录。"""
        skill_name = name.lower().replace(" ", "-")
        file_path = _SKILLS_DEFINITIONS_DIR / f"{skill_name}.md"
        if file_path.exists():
            raise FileExistsError(f"Skill {skill_name} 已存在")

        skill = ChatSkill(
            name=skill_name,
            description=data.get("description", ""),
            triggers=data.get("triggers", []),
            phase=data.get("phase", "chat"),
            tools=data.get("tools", []),
            agent_role=data.get("agent_role", "developer"),
            body=data.get("body", ""),
            version="1.0.0",
            path=str(file_path),
        )
        self._write_skill_file(skill)
        self._skills[skill_name] = skill
        self._save_version(skill_name, "1.0.0", "创建")
        logger.info("skill_created", name=skill_name)
        return skill

    def update(self, name: str, data: dict) -> ChatSkill:
        """更新已有 Skill——写回 SKILL.md。"""
        existing = self._skills.get(name)
        if not existing:
            raise FileNotFoundError(f"Skill {name} 不存在")

        # 版本号递增
        old_version = existing.version
        new_version = self._bump_version(old_version, data.get("version_bump", "patch"))

        updated = ChatSkill(
            name=name,
            description=data.get("description", existing.description),
            triggers=data.get("triggers", existing.triggers),
            phase=data.get("phase", existing.phase),
            tools=data.get("tools", existing.tools),
            agent_role=data.get("agent_role", existing.agent_role),
            body=data.get("body", existing.body),
            version=new_version,
            is_chat_skill=data.get("is_chat_skill", existing.is_chat_skill),
            is_chainable=data.get("is_chainable", existing.is_chainable),
            path=existing.path,
        )
        self._write_skill_file(updated)
        self._skills[name] = updated
        self._save_version(name, new_version, data.get("change_summary", "更新"))
        logger.info("skill_updated", name=name, version=new_version)
        return updated

    def delete(self, name: str) -> bool:
        """删除 Skill——同时删除 SKILL.md 文件。"""
        skill = self._skills.get(name)
        if not skill:
            return False
        if skill.path:
            try:
                Path(skill.path).unlink(missing_ok=True)
            except OSError as e:
                logger.error("skill_delete_file_failed", path=skill.path, error=str(e))
        del self._skills[name]
        logger.info("skill_deleted", name=name)
        return True

    # ── 版本管理 ────────────────────────────────────

    def get_versions(self, name: str) -> list[SkillVersion]:
        """获取 Skill 的版本历史列表。"""
        if not self._skills:
            self.discover()
        return self._version_history.get(name, [])

    def rollback(self, name: str, version: str) -> ChatSkill:
        """回滚 Skill 到指定版本。

        WHY 非破坏性: 回滚本身是新的版本——version 递增，
        不会丢失被回滚的版本的记录。
        """
        skill = self._skills.get(name)
        if not skill:
            raise FileNotFoundError(f"Skill {name} 不存在")

        # 查找目标版本
        versions = self._version_history.get(name, [])
        target = next((v for v in versions if v.version == version), None)
        if not target:
            raise FileNotFoundError(f"版本 {version} 不存在")

        # 从 Git 恢复文件内容 → 重新解析
        if skill.path:
            # P2-1: 路径合法性检查——禁止 .. 穿越 + 限制在工作区内
            _skill_path = Path(skill.path).resolve()
            _skills_root = _SKILLS_DEFINITIONS_DIR.resolve()
            _compose_root = _COMPOSE_SKILLS_DIR.resolve()
            if ".." in str(skill.path) or (
                not str(_skill_path).startswith(str(_skills_root))
                and not str(_skill_path).startswith(str(_compose_root))
            ):
                raise RuntimeError(f"Skill 路径非法: {skill.path}")
            try:
                import subprocess
                result = subprocess.run(
                    ["git", "show", f"{target.file_hash}:{skill.path}"],
                    capture_output=True, text=True,
                    cwd=Path(skill.path).parent,
                )
                if result.returncode == 0:
                    content = result.stdout
                    # 临时写回文件让 _load_skill_file 解析
                    tmp_path = Path(skill.path)
                    tmp_path.write_text(content, encoding="utf-8")
                    restored = self._load_skill_file(tmp_path)
                    if restored:
                        new_version = self._bump_version(skill.version, "patch")
                        restored.version = new_version
                        self._write_skill_file(restored)
                        self._skills[name] = restored
                        self._save_version(name, new_version, f"回滚到 v{version}")
                        logger.info("skill_rolled_back", name=name, from_ver=version, to_ver=new_version)
                        return restored
            except Exception as e:
                logger.error("skill_rollback_failed", name=name, error=str(e))
                raise RuntimeError(f"回滚失败: {e}") from e

        raise RuntimeError(f"无法回滚 Skill {name}——缺少文件路径或 Git 历史")

    # ── 编排链 ─────────────────────────────────────

    def build_chain(self, names: list[str]) -> list[ChatSkill]:
        """根据名称列表构建 Skill 链——供 ComposeOrchestrator 使用。

        Args:
            names: ["plan", "implement", "review"] 或 ["compose:plan", ...]
        Returns:
            按 names 顺序排列的 ChatSkill 列表。
        Raises:
            FileNotFoundError: 任一 Skill 不存在。
        """
        if not self._skills:
            self.discover()

        chain = []
        for name in names:
            skill = self._skills.get(name)
            if not skill:
                # 尝试去掉 compose: 前缀匹配
                short = name.replace("compose:", "")
                skill = self._skills.get(short)
            if not skill:
                raise FileNotFoundError(f"Skill {name} 不存在")
            if not skill.is_chainable:
                logger.warning("skill_not_chainable", name=skill.name)
            chain.append(skill)
        return chain

    # ── 热更新 ─────────────────────────────────────

    def start_watcher(self) -> None:
        """启动文件系统 watcher——检测 SKILL.md 变化 → 自动 reload。"""
        from orbit.skills.watcher import SkillWatcher
        if self._watcher is not None:
            return
        self._watcher = SkillWatcher(self, self._skills_dirs)
        self._watcher.start()
        logger.info("skill_watcher_started", dirs=[str(d) for d in self._skills_dirs])

    def stop_watcher(self) -> None:
        """停止文件系统 watcher。"""
        if self._watcher:
            self._watcher.stop()
            self._watcher = None

    # ── 内部方法 ────────────────────────────────────

    def _load_skill_file(self, md_file: Path) -> ChatSkill | None:
        """解析单个 SKILL.md → ChatSkill。兼容 compose Skill 格式。"""
        content = md_file.read_text(encoding="utf-8")
        match = _FRONTMATTER_RE.match(content)
        if not match:
            logger.warning("skill_no_frontmatter", file=str(md_file))
            return None

        frontmatter = yaml.safe_load(match.group(1))
        if not isinstance(frontmatter, dict):
            return None

        body = content[match.end():].strip()
        name = frontmatter.get("name", md_file.stem)
        # compose skill name 是 "compose:plan" 格式——提取短名
        is_chat = frontmatter.get("is_chat_skill", True)
        is_chainable = frontmatter.get("is_chainable", "compose:" in name)
        # compose skills 的 agent_role 在 frontmatter 里
        agent_role = frontmatter.get("agent_role", "developer")

        return ChatSkill(
            name=name,
            description=frontmatter.get("description", ""),
            triggers=frontmatter.get("triggers", []),
            phase=frontmatter.get("phase", "chat"),
            tools=frontmatter.get("tools", []),
            agent_role=agent_role,
            body=body,
            version=frontmatter.get("version", "1.0.0"),
            is_chat_skill=is_chat,
            is_chainable=is_chainable,
            path=str(md_file),
        )

    def _write_skill_file(self, skill: ChatSkill) -> None:
        """将 ChatSkill 写回 SKILL.md 文件。"""
        file_path = Path(skill.path) if skill.path else _SKILLS_DEFINITIONS_DIR / f"{skill.name}.md"
        _SKILLS_DEFINITIONS_DIR.mkdir(parents=True, exist_ok=True)

        frontmatter = {
            "name": skill.name,
            "description": skill.description,
            "triggers": skill.triggers,
            "phase": skill.phase,
            "tools": skill.tools,
            "agent_role": skill.agent_role,
            "version": skill.version,
            "is_chat_skill": skill.is_chat_skill,
            "is_chainable": skill.is_chainable,
        }
        yaml_str = yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False).strip()
        content = f"---\n{yaml_str}\n---\n\n{skill.body}\n"
        file_path.write_text(content, encoding="utf-8")
        skill.path = str(file_path)

    def _save_version(self, name: str, version: str, summary: str) -> None:
        """追加版本历史条目。"""
        if name not in self._version_history:
            self._version_history[name] = []
        # 计算当前文件 hash
        skill = self._skills.get(name)
        file_hash = ""
        if skill and skill.path:
            try:
                content = Path(skill.path).read_text(encoding="utf-8")
                file_hash = hashlib.sha256(content.encode()).hexdigest()[:12]
            except Exception:
                pass
        self._version_history[name].append(SkillVersion(
            version=version,
            changed_at=datetime.now(tz=timezone.utc).isoformat(),
            changed_by="user",
            diff_summary=summary,
            file_hash=file_hash,
        ))

    @staticmethod
    def _bump_version(current: str, bump: str) -> str:
        """语义化版本递增。

        Args:
            current: "1.2.0"
            bump: "major" | "minor" | "patch"
        """
        try:
            parts = [int(x) for x in current.split(".")]
        except (ValueError, AttributeError):
            parts = [1, 0, 0]
        while len(parts) < 3:
            parts.append(0)
        if bump == "major":
            parts[0] += 1; parts[1] = 0; parts[2] = 0
        elif bump == "minor":
            parts[1] += 1; parts[2] = 0
        else:  # patch
            parts[2] += 1
        return f"{parts[0]}.{parts[1]}.{parts[2]}"


# ── 全局单例 ────────────────────────────────────────
_registry_instance: SkillRegistry | None = None


def get_skill_registry() -> SkillRegistry:
    """获取全局 SkillRegistry 单例。"""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = SkillRegistry()
        _registry_instance.discover()
    return _registry_instance
