"""generate_repo_map.py — 生成 PR 轻量 Repo Map。

输入: changed-files.txt, pr-meta.json, rule-scan.md (由前面脚本生成)
输出: repo-map.md — 结构化 PR 影响面摘要

内容:
    - PR 摘要 (标题、状态)
    - 变更文件分类 (backend API / models / schemas / services / core / tests / frontend / docs)
    - 权限扫描摘要
    - 建议 Reviewer 关注点
"""

import json
import sys
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


PROJECT_ROOT = Path(__file__).resolve().parents[3]
AUTOMATIONS_DIR = PROJECT_ROOT / ".automations" / "pr-review"

# 文件分类规则
PATH_CLASSIFIERS = [
    ("Backend API", lambda p: p.startswith("backend/app/api/")),
    ("Backend Models", lambda p: p.startswith("backend/app/models/")),
    ("Backend Schemas", lambda p: p.startswith("backend/app/schemas/")),
    ("Backend Services", lambda p: p.startswith("backend/app/services/")),
    ("Backend Core / Auth / Permission", lambda p: p.startswith("backend/app/core/") or "permission" in p.lower()),
    ("Backend Other", lambda p: p.startswith("backend/")),
    ("Tests", lambda p: "test" in p.lower() or p.startswith("tests/")),
    ("Frontend", lambda p: p.endswith((".tsx", ".ts", ".jsx", ".js", ".css", ".scss")) or p.startswith("frontend/")),
    ("Docs", lambda p: p.endswith(".md") or p.startswith("docs/")),
    ("Config / CI", lambda p: any(p.startswith(prefix) for prefix in [".github/", ".claude/", "pnpm-", "package.", "tsconfig", "vite."])),
]


def classify_file(path: str) -> str:
    """根据路径分类文件。"""
    for category, predicate in PATH_CLASSIFIERS:
        if predicate(path):
            return category
    return "Other"


def build_repo_map(pr_number: int) -> str:
    """生成 repo-map.md。"""
    pr_dir = AUTOMATIONS_DIR / str(pr_number)

    # 读取输入
    meta = json.loads((pr_dir / "pr-meta.json").read_text(encoding="utf-8"))
    changed_files = [
        line.strip() for line in (pr_dir / "changed-files.txt").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    rule_scan = ""
    rule_scan_path = pr_dir / "rule-scan.md"
    if rule_scan_path.exists():
        rule_scan = rule_scan_path.read_text(encoding="utf-8")

    # 分类文件
    classified: dict[str, list[str]] = {}
    for f in changed_files:
        cat = classify_file(f)
        classified.setdefault(cat, []).append(f)

    # 提取 rule-scan 摘要
    p0_count = rule_scan.count("| 🔴 P0") if rule_scan else 0
    p1_count = rule_scan.count("| 🟡 P1") if rule_scan else 0
    has_permission_issues = "P0" in rule_scan and "0 |" not in rule_scan.split("🔴 P0")[1][:20] if rule_scan else False

    lines = [
        f"# PR Repo Map — #{pr_number}",
        "",
        "## PR Summary",
        f"- **PR**: #{pr_number}",
        f"- **Title**: {meta.get('title', 'N/A')}",
        f"- **Files Changed**: {len(changed_files)}",
        f"- **Comments**: {len(meta.get('comments', []))}",
        f"- **Reviews**: {len(meta.get('reviews', []))}",
        "",
        "## Changed Files by Category",
        "",
    ]

    # 按分类输出
    priority_order = [
        "Backend Core / Auth / Permission",
        "Backend API",
        "Backend Services",
        "Backend Models",
        "Backend Schemas",
        "Backend Other",
        "Frontend",
        "Tests",
        "Docs",
        "Config / CI",
        "Other",
    ]
    for cat in priority_order:
        if cat in classified:
            files = classified[cat]
            lines.append(f"### {cat} ({len(files)})")
            for f in sorted(files):
                lines.append(f"- {f}")
            lines.append("")

    # 权限扫描摘要
    lines.append("## Permission Scan Summary")
    lines.append("")
    if rule_scan:
        # 提取关键信息
        if has_permission_issues:
            lines.append(f"⚠️ **发现权限字符串问题**: P0={p0_count}, P1={p1_count}")
        else:
            lines.append("✅ 权限扫描未发现异常")
        lines.append("")
        lines.append("详见 `rule-scan.md`。")
    else:
        lines.append("rule-scan.md 未生成，请先运行 scan_permissions.py。")
    lines.append("")

    # 历史 Gotcha 提醒
    lines.append("## ⚠️ Historical Gotcha")
    lines.append("")
    lines.append("**require_permission 权限字符串问题已反复出现 5 次**: PR#73 → #75 → #78 → #83 → #84。")
    lines.append("")
    lines.append("Reviewer 必须检查:")
    lines.append("1. 新增写端点是否都有 `require_permission` 保护？")
    lines.append("2. 权限字符串拼写是否正确（module:action 格式）？")
    lines.append("3. 权限是否在 `rbac.py` 和 seed 数据中注册？")
    lines.append("4. 测试是否覆盖未授权/无权限场景？")
    lines.append("")

    # 建议关注点
    lines.append("## Suggested Reviewer Focus")
    lines.append("")

    # 根据变更内容生成针对性建议
    has_api_changes = any("api/" in f for f in changed_files)
    has_core_changes = any("core/" in f for f in changed_files)
    has_schema_changes = any("schemas/" in f for f in changed_files)
    has_service_changes = any("services/" in f for f in changed_files)
    has_test_changes = any("test" in f.lower() for f in changed_files)
    has_frontend_changes = any(f.endswith((".tsx", ".ts")) for f in changed_files)

    focus_items = []
    if has_api_changes or has_core_changes:
        focus_items.append("1. **权限字符串是否正确** —— 每个新增/修改端点是否有匹配的 `require_permission`？")
    if has_api_changes:
        focus_items.append("2. **API endpoint 是否有权限保护** —— 写端点必须有 RBAC，只读端点是否合理暴露？")
    if has_schema_changes or has_service_changes:
        focus_items.append("3. **Schema / Service / Model 是否一致** —— 字段变更是否三层同步？")
    if has_test_changes:
        focus_items.append("4. **测试是否覆盖负向权限场景** —— 未授权用户是否返回 403？")
    else:
        focus_items.append("4. **是否需要新增测试** —— 确认变更是否有对应测试覆盖？")
    if has_frontend_changes:
        focus_items.append("5. **前端调用是否匹配后端 API** —— 检查 endpoint 路径和方法是否一致。")

    if focus_items:
        lines.extend(focus_items)
    else:
        lines.append("根据变更内容确定审核重点。")

    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) < 2:
        print("用法: python generate_repo_map.py <PR_NUMBER>")
        print("示例: python generate_repo_map.py 85")
        sys.exit(1)

    try:
        pr_number = int(sys.argv[1])
    except ValueError:
        print(f"错误: PR 号必须是数字，收到: {sys.argv[1]}")
        sys.exit(1)

    pr_dir = AUTOMATIONS_DIR / str(pr_number)

    # 检查前置产物
    required = ["pr-meta.json", "changed-files.txt"]
    missing = [f for f in required if not (pr_dir / f).exists()]
    if missing:
        print(f"错误: 缺少前置产物: {missing}")
        print(f"请先运行 fetch_pr_context.py {pr_number}")
        sys.exit(1)

    print(f"正在生成 PR #{pr_number} Repo Map...")
    repo_map = build_repo_map(pr_number)
    output_path = pr_dir / "repo-map.md"
    output_path.write_text(repo_map, encoding="utf-8")
    print(f"✓ repo-map.md 已生成 → {output_path}")


if __name__ == "__main__":
    main()
