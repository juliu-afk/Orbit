"""D:\\OrbitBasePackages\\ 基础代码包库的索检与注册。

索检流程（不调 LLM）:
1. 加载 index.json → 候选包列表
2. 按语言/框架/特性标签匹配
3. 返回候选包摘要（仅描述 + 预估 token，不含代码）

LLM 决策流程（调 GLM-5.2）:
4. 候选包摘要 → LLM 评估成本/收益 → full | skeleton | skip
5. 按决策返回模板内容

注册流程（项目做多了自动积累）:
- 新增基础代码包 → 写入库目录 + 更新 index.json
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from orbit.brief.models import BasePackage, PackageDecision

if TYPE_CHECKING:
    from orbit.gateway.client import LLMClient

logger = structlog.get_logger("orbit.brief.package_library")

# ── 默认库路径 ─────────────────────────────────────────────
# WHY 环境变量优先: 跨平台兼容——Linux/macOS 无 D:盘。
# ORBIT_BASE_PACKAGES_PATH 可覆盖；默认 ~/.orbit/base-packages/
DEFAULT_LIBRARY_PATH = os.environ.get(
    "ORBIT_BASE_PACKAGES_PATH",
    os.path.join(os.path.expanduser("~"), ".orbit", "base-packages"),
)
INDEX_FILE = "index.json"


class PackageLibrary:
    """基础代码包库——索检 + 注册 + LLM 决策。

    Usage:
        lib = PackageLibrary()
        candidates = lib.search("python", "fastapi")
        # 如果有候选，让 LLM 决策
        decision = await lib.decide_injection(llm, project_analysis, candidates)
    """

    def __init__(self, library_path: str = DEFAULT_LIBRARY_PATH) -> None:
        self._library_path = library_path
        self._index: list[BasePackage] | None = None

    @property
    def library_path(self) -> str:
        return self._library_path

    def _ensure_library(self) -> None:
        """确保库目录和 index.json 存在。"""
        os.makedirs(self._library_path, exist_ok=True)
        index_path = os.path.join(self._library_path, INDEX_FILE)
        if not os.path.isfile(index_path):
            Path(index_path).write_text("[]", encoding="utf-8")
            # P2-2: 首次初始化明确提示
            logger.warning(
                "base_package_library_empty",
                path=self._library_path,
                hint="基础代码包库为空。运行 'orbit init-packages' 或手动添加模板到 index.json",
            )

    def _load_index(self) -> list[BasePackage]:
        """加载 index.json 为 BasePackage 列表（内存缓存）。"""
        if self._index is not None:
            return self._index
        self._ensure_library()
        index_path = os.path.join(self._library_path, INDEX_FILE)
        try:
            data = json.loads(Path(index_path).read_text(encoding="utf-8"))
            self._index = [BasePackage.from_dict(item) for item in data]
        except (json.JSONDecodeError, FileNotFoundError):
            self._index = []
        # P2-2: 空索引警告——首次使用时提示用户初始化
        if not self._index:
            logger.info(
                "base_package_library_empty_on_load",
                path=self._library_path,
                hint="无可用基础代码包。新项目将跳过模板注入。设置 ORBIT_BASE_PACKAGES_PATH 指向已有库或运行初始化脚本。",
            )
        return self._index

    def _save_index(self) -> None:
        """保存内存中的索引到 index.json。"""
        if self._index is None:
            return
        index_path = os.path.join(self._library_path, INDEX_FILE)
        data = [pkg.to_dict() for pkg in self._index]
        Path(index_path).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def search(
        self,
        language: str = "",
        framework: str = "",
        features: list[str] | None = None,
    ) -> list[BasePackage]:
        """按语言/框架/特性标签索检基础代码包。

        返回匹配度排序的候选包列表（仅元数据，不含代码模板内容）。

        Args:
            language: 目标语言，如 "python"
            framework: 目标框架，如 "fastapi"（可选）
            features: 需要的特性标签，如 ["async", "sqlalchemy"]（可选）

        Returns:
            按匹配度降序排列的 BasePackage 列表
        """
        index = self._load_index()
        features = features or []
        scored: list[tuple[int, BasePackage]] = []

        for pkg in index:
            score = 0
            if language and pkg.language.lower() == language.lower():
                score += 10
            if framework and pkg.framework.lower() == framework.lower():
                score += 5
            if features:
                pkg_features_lower = {f.lower() for f in pkg.features}
                for feat in features:
                    if feat.lower() in pkg_features_lower:
                        score += 3
            if score > 0:
                scored.append((score, pkg))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [pkg for _, pkg in scored]

    def register(
        self,
        package_id: str,
        language: str,
        framework: str = "",
        features: list[str] | None = None,
        description: str = "",
        template_files: dict[str, str] | None = None,
    ) -> BasePackage:
        """注册新的基础代码包——写入库目录 + 更新索引。

        Args:
            package_id: 唯一标识，如 "python-cli-click"
            language: 编程语言
            framework: 框架名（可选）
            features: 特性标签列表
            description: 一句话描述
            template_files: {相对路径: 文件内容} ——如果不是 Cookiecutter 格式

        Returns:
            注册的 BasePackage 对象
        """
        self._load_index()

        # 检查重复
        existing = [p for p in self._index if p.id == package_id]
        if existing:
            logger.info("package_already_registered", id=package_id)
            return existing[0]

        # 写入模板文件
        pkg_dir = os.path.join(self._library_path, package_id)
        template_dir = os.path.join(pkg_dir, "template")
        os.makedirs(template_dir, exist_ok=True)

        file_count = 0
        if template_files:
            for rel_path, content in template_files.items():
                abs_path = os.path.join(template_dir, rel_path)
                os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                Path(abs_path).write_text(content, encoding="utf-8")
                file_count += 1

        # 写入 manifest.yaml
        manifest_lines = [
            f"id: {package_id}",
            f"language: {language}",
            f"framework: {framework}",
            "features:",
        ]
        for f in (features or []):
            manifest_lines.append(f"  - {f}")
        manifest_lines.append(f"description: \"{description}\"")
        manifest_lines.append(f"format: cookiecutter")

        manifest_path = os.path.join(pkg_dir, "manifest.yaml")
        Path(manifest_path).write_text("\n".join(manifest_lines), encoding="utf-8")

        # 估算 token
        total_chars = sum(len(c) for c in (template_files or {}).values())
        estimated_tokens = max(1, total_chars // 3)  # 粗略: 3 字符 ≈ 1 token

        pkg = BasePackage(
            id=package_id,
            language=language,
            framework=framework,
            features=features or [],
            description=description,
            file_count=file_count,
            estimated_tokens=estimated_tokens,
            cookiecutter_compat=False,  # 非 Cookiecutter 格式默认 false
            path=package_id + "/",
        )

        self._index.append(pkg)
        self._save_index()

        logger.info("package_registered", id=package_id, files=file_count, tokens=estimated_tokens)
        return pkg

    def get_template_files(self, package_id: str) -> dict[str, str]:
        """获取指定包的模板文件内容。

        Args:
            package_id: 包 ID

        Returns:
            {相对路径: 文件内容} 映射
        """
        template_dir = os.path.join(self._library_path, package_id, "template")
        if not os.path.isdir(template_dir):
            return {}

        files: dict[str, str] = {}
        for root, _dirs, filenames in os.walk(template_dir):
            for fname in filenames:
                abs_path = os.path.join(root, fname)
                rel_path = os.path.relpath(abs_path, template_dir)
                try:
                    files[rel_path] = Path(abs_path).read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    logger.warning("template_read_failed", path=abs_path)
        return files

    def get_skeleton(self, package_id: str) -> str:
        """获取包的目录骨架（仅目录树，不含文件内容）。

        WHY 独立方法: LLM 决策 skeleton 时只需目录结构，节省 token。
        """
        template_dir = os.path.join(self._library_path, package_id, "template")
        if not os.path.isdir(template_dir):
            return ""

        lines: list[str] = []
        for root, dirs, filenames in os.walk(template_dir):
            # 过滤 Cookiecutter 变量目录（{{...}}）
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            rel_root = os.path.relpath(root, template_dir)
            indent = "  " * (rel_root.count(os.sep) + 1) if rel_root != "." else ""
            if rel_root != ".":
                lines.append(f"{indent}{os.path.basename(rel_root)}/")
            for fname in sorted(filenames):
                file_indent = indent + "  " if rel_root != "." else "  "
                lines.append(f"{file_indent}{fname}")
        return "\n".join(lines)

    async def decide_injection(
        self,
        llm: "LLMClient",
        language: str,
        framework: str,
        features: list[str],
        project_file_count: int,
        candidate_packages: list[BasePackage],
    ) -> PackageDecision:
        """让 GLM-5.2 决策基础代码包注入策略。

        WHY LLM 决策: 代码质量提升 vs token 消耗的权衡需要上下文理解，
        确定性规则无法覆盖所有场景。

        Args:
            llm: 已 pin 到 GLM-5.2 的 LLMClient
            language: 项目语言
            framework: 项目框架
            features: 项目特性
            project_file_count: 已有文件数
            candidate_packages: 候选包列表

        Returns:
            PackageDecision with decision + reason
        """
        if not candidate_packages:
            return PackageDecision(decision="skip", reason="无匹配的基础代码包")

        # 构建候选包摘要（仅描述，不含代码）
        candidates_text = "\n".join(
            f"- **{p.id}**: {p.description}（{p.file_count} 文件, ~{p.estimated_tokens} tokens）"
            for p in candidate_packages
        )

        prompt = f"""你是一个 Token 成本优化器。请决定是否将基础代码包注入到即将执行的 Agent 任务中。

## 项目现状
- 语言: {language}
- 框架: {framework or '未检测到'}
- 特性: {', '.join(features) if features else '未检测到'}
- 已有文件数: {project_file_count}

## 候选基础代码包
{candidates_text}

## 决策选项
- **full**: 注入所有模板文件内容到 Agent prompt。好处：Agent 能看到完整代码模板，生成一致的代码。成本：{sum(p.estimated_tokens for p in candidate_packages)} tokens。
- **skeleton**: 仅注入目录结构 + 关键配置文件名。好处：Agent 知道项目布局但不需要完整代码。成本：~200 tokens。
- **skip**: 不注入。项目已有足够代码，模板可能冲突或过时。

## 决策原则
- 空项目或文件数 < 5: 倾向 full——Agent 需要模板引导
- 文件数 5-20: 倾向 skeleton——Agent 需要结构但不应被模板束缚
- 文件数 > 20: 倾向 skip——已有代码已确立模式，模板可能导致冲突
- 如果项目已有自定义 auth/middleware/config: 跳过含同名文件的包

请只输出一行 JSON（不要解释）:
{{"decision": "full|skeleton|skip", "package_ids": ["pkg-id1", ...], "reason": "一句话理由"}}"""

        from orbit.gateway.schemas import LLMRequest

        response = await llm.generate(
            LLMRequest(
                prompt=prompt,
                system_prompt="你是 Token 成本优化器。只输出单行 JSON，不要额外解释。",
                temperature=0.1,  # 最低温度——决策应确定
                max_tokens=256,
            ),
            task_id=f"pkg-decision-{language}-{framework}",
            agent_name="brief_generator",
        )

        # 解析 JSON 响应
        try:
            import re

            content = response.content.strip()
            # 容错——提取第一个 JSON 对象
            match = re.search(r'\{[^{}]*\}', content)
            if match:
                data = json.loads(match.group())
                return PackageDecision(
                    decision=data.get("decision", "skip"),
                    package_ids=data.get("package_ids", []),
                    reason=data.get("reason", ""),
                )
        except (json.JSONDecodeError, KeyError):
            logger.warning("package_decision_parse_failed", content=response.content[:200])

        # 降级——简单规则
        if project_file_count < 5:
            return PackageDecision(
                decision="full",
                package_ids=[p.id for p in candidate_packages],
                reason="项目文件少，全量注入模板（LLM 解析失败，使用确定性降级规则）",
            )
        return PackageDecision(
            decision="skip",
            reason="LLM 解析失败，确定性降级规则: 已有文件数 > 5 → skip",
        )
