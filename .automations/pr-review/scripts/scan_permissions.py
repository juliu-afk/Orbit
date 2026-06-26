"""scan_permissions.py — 扫描 PR changed files 中的 require_permission 调用。

输入: changed-files.txt (由 fetch_pr_context.py 生成)
输出: rule-scan.md — Markdown 格式的扫描报告

检测规则:
    P0: 空权限 / 变量（非字面量）
    P1: 权限字符串未在 rbac.py Permission 枚举中注册
    P2: 格式建议（仅含下划线无冒号→单段权限；本项目的 snake_case 格式合法）
"""

import re
import sys
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


PROJECT_ROOT = Path(__file__).resolve().parents[3]
AUTOMATIONS_DIR = PROJECT_ROOT / ".automations" / "pr-review"
RBAC_PATH = PROJECT_ROOT / "backend" / "app" / "core" / "rbac.py"

# require_permission 匹配模式
RE_PERMISSION = re.compile(
    r'(?:Depends\s*\(\s*)?require_permission\s*\(\s*'
    r'(?:'
    r'"(?P<dquote>[^"]*)"'        # 双引号字符串
    r"|"
    r"'(?P<squote>[^']*)'"         # 单引号字符串
    r"|"
    r'(?P<variable>[^)"\']+)'      # 非字面量（变量/表达式）
    r')'
    r'\s*\)'
)


def load_permission_registry() -> set[str]:
    """从 rbac.py 的 Permission 枚举中提取所有已注册权限字符串。"""
    if not RBAC_PATH.exists():
        return set()

    content = RBAC_PATH.read_text(encoding="utf-8")
    registered = set()

    # 匹配 Permission 枚举中的值: NAME = "permission_string"
    # 这些值在 class Permission(StrEnum) 内部
    in_permission_class = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("class Permission"):
            in_permission_class = True
            continue
        if in_permission_class and stripped.startswith("class "):
            break  # 出了 Permission 类
        if not in_permission_class:
            continue
        # 匹配 NAME = "xxx"
        m = re.match(r'^\w+\s*=\s*"(?P<perm>[a-z][a-z0-9_]*)"', stripped)
        if m:
            registered.add(m.group("perm"))

    return registered


def scan_file(filepath: Path, registry: set[str]) -> list[dict]:
    """扫描单个 Python 文件，返回发现列表。"""
    findings = []
    try:
        content = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return findings

    for match in RE_PERMISSION.finditer(content):
        line_no = content[:match.start()].count('\n') + 1
        # 跳过注释行（# 开头的行）
        line_start = content.rfind('\n', 0, match.start()) + 1
        line_content = content[line_start:match.start()]
        if line_content.lstrip().startswith('#'):
            continue
        perm_str = match.group("dquote") or match.group("squote") or ""
        is_variable = match.group("variable") is not None

        finding = {
            "file": str(filepath.relative_to(PROJECT_ROOT)),
            "line": line_no,
            "permission_string": match.group("dquote") or match.group("squote") or match.group("variable"),
            "is_variable": is_variable,
            "suspicion": None,
            "reason": "",
        }

        # 规则 1: 空权限 → P0
        if not is_variable and perm_str == "":
            finding["suspicion"] = "P0"
            finding["reason"] = "空权限字符串 — 端点无 RBAC 保护，任何人都可访问"

        # 规则 2: 非字符串字面量（变量/表达式） → P0
        elif is_variable:
            finding["suspicion"] = "P0"
            finding["reason"] = f"权限使用变量 `{perm_str}` 而非字符串字面量 — 无法静态验证权限是否已注册"

        # 规则 3: 字符串字面量但未在 Permission 枚举中注册 → P1
        elif registry and perm_str not in registry:
            finding["suspicion"] = "P1"
            finding["reason"] = f"权限 `{perm_str}` 未在 rbac.py Permission 枚举中找到 — 可能未注册或拼写错误"

        # 通过
        else:
            finding["reason"] = "已注册"

        findings.append(finding)

    return findings


def build_rule_scan(pr_number: int, findings: list[dict], changed_files: list[str], registry: set[str]) -> str:
    """生成 rule-scan.md 内容。"""
    python_files = [f for f in changed_files if f.endswith(".py")]
    scanned_files = set(f["file"] for f in findings)

    lines = [
        f"# Rule Scan — PR #{pr_number} 权限字符串扫描",
        "",
        f"**扫描范围**: {len(python_files)} 个 Python 文件",
        f"**发现调用**: {len(findings)} 处 require_permission",
        f"**权限注册表**: {len(registry)} 个已注册权限（来自 rbac.py Permission 枚举）",
        f"**扫描时间**: 自动生成",
        "",
    ]

    if not python_files:
        lines.append("## 结果")
        lines.append("")
        lines.append("PR 中无 Python 文件变更，未扫描权限调用。")
        return "\n".join(lines)

    if not findings:
        lines.append("## 结果")
        lines.append("")
        lines.append("[PASS] No suspicious permission issues found.")
        lines.append("")
        lines.append("所有 `require_permission` 调用均使用合法字符串字面量且已在 rbac.py 注册。")
        return "\n".join(lines)

    # 分组
    p0 = [f for f in findings if f["suspicion"] == "P0"]
    p1 = [f for f in findings if f["suspicion"] == "P1"]
    clean = [f for f in findings if f["suspicion"] is None]

    lines.append("## 汇总")
    lines.append("")
    lines.append("| 严重程度 | 数量 |")
    lines.append("|---------|------|")
    lines.append(f"| [P0] 阻断合并 — 空权限/变量 | {len(p0)} |")
    lines.append(f"| [P1] 应修复 — 未注册权限 | {len(p1)} |")
    lines.append(f"| [PASS] 通过 | {len(clean)} |")
    lines.append("")

    if p0:
        lines.append("## [P0] 阻断合并")
        lines.append("")
        for f in p0:
            lines.append(f"- **[{f['file']}:{f['line']}]({f['file']}#L{f['line']})**")
            lines.append(f"  - 权限字符串: `{f['permission_string']}`")
            lines.append(f"  - {f['reason']}")
        lines.append("")

    if p1:
        lines.append("## [P1] 应修复 — 权限未在 rbac.py 注册")
        lines.append("")
        lines.append("以下权限字符串在 changed files 中使用，但在 `backend/app/core/rbac.py` 的 Permission 枚举中未找到：")
        lines.append("")
        for f in p1:
            lines.append(f"- **[{f['file']}:{f['line']}]({f['file']}#L{f['line']})**")
            lines.append(f"  - 权限字符串: `{f['permission_string']}`")
            lines.append(f"  - {f['reason']}")
        lines.append("")
        lines.append("**修复**: 在 `rbac.py` Permission 枚举中注册权限，或在端点使用正确的已注册权限字符串。")
        lines.append("")

    if clean:
        lines.append("## [PASS] 通过的调用")
        lines.append("")
        for f in clean:
            lines.append(f"- [{f['file']}:{f['line']}]({f['file']}#L{f['line']}) — `{f['permission_string']}`")
        lines.append("")

    # 未扫描到调用的 Python 文件 → 潜在新增端点缺权限
    unscanned = [f for f in python_files if f not in scanned_files]
    if unscanned:
        lines.append("## 未扫描到权限调用的 Python 文件")
        lines.append("")
        lines.append("以下 Python 文件在 diff 中，但未检测到 `require_permission` 调用：")
        lines.append("")
        for f in unscanned:
            lines.append(f"- {f}")
        lines.append("")
        lines.append("> [WARN] 如果这些文件包含新增 API 端点，请手动检查是否需要添加权限保护。")

    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) < 2:
        print("用法: python scan_permissions.py <PR_NUMBER>")
        print("示例: python scan_permissions.py 85")
        sys.exit(1)

    try:
        pr_number = int(sys.argv[1])
    except ValueError:
        print(f"错误: PR 号必须是数字，收到: {sys.argv[1]}")
        sys.exit(1)

    # 加载权限注册表
    registry = load_permission_registry()
    print(f"权限注册表: {len(registry)} 个已注册权限")

    pr_dir = AUTOMATIONS_DIR / str(pr_number)
    changed_files_path = pr_dir / "changed-files.txt"

    if not changed_files_path.exists():
        print(f"错误: 未找到 {changed_files_path}，请先运行 fetch_pr_context.py {pr_number}")
        sys.exit(1)

    changed_files = [
        line.strip() for line in changed_files_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    print(f"变更文件总数: {len(changed_files)}")
    python_count = len([f for f in changed_files if f.endswith(".py")])
    print(f"其中 Python 文件: {python_count}")

    all_findings = []
    for rel_path in changed_files:
        if not rel_path.endswith(".py"):
            continue
        filepath = PROJECT_ROOT / rel_path
        if not filepath.exists():
            print(f"  [SKIP] {rel_path} — 文件不存在于本地")
            continue
        findings = scan_file(filepath, registry)
        if findings:
            print(f"  [OK] {rel_path} — {len(findings)} 处 require_permission")
        all_findings.extend(findings)

    # 生成报告
    rule_scan = build_rule_scan(pr_number, all_findings, changed_files, registry)
    output_path = pr_dir / "rule-scan.md"
    output_path.write_text(rule_scan, encoding="utf-8")
    print(f"\n扫描完成 -> {output_path}")
    print(f"共发现 {len(all_findings)} 处 require_permission 调用")

    p0_count = len([f for f in all_findings if f["suspicion"] == "P0"])
    p1_count = len([f for f in all_findings if f["suspicion"] == "P1"])
    if p0_count > 0:
        print(f"[FAIL] {p0_count} 处 P0 问题（空权限/变量），请立即修复")
    if p1_count > 0:
        print(f"[WARN] {p1_count} 处 P1 问题（未注册权限），请确认是否需注册")
    if p0_count == 0 and p1_count == 0:
        print("[PASS] 所有权限字符串均已注册")


if __name__ == "__main__":
    main()
