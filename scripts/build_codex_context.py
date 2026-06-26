"""build_codex_context.py — 合并 Claude 上下文文件为 Codex AGENTS.md。

Codex CLI 读取项目根目录的 AGENTS.md（类似 Claude Code 的 CLAUDE.md）。
此脚本将核心上下文文件合并为单一的 AGENTS.md。

输入:
    CLAUDE.md              — 核心规则
    docs/WORKFLOW.md       — 开发工作流
    docs/accounting-rules.md — 会计准则

输出:
    AGENTS.md              — Codex 上下文文件（项目根目录）

用法:
    python scripts/build_codex_context.py
"""

import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


PROJECT_ROOT = Path(__file__).resolve().parents[1]

SOURCE_FILES = [
    PROJECT_ROOT / "CLAUDE.md",
    PROJECT_ROOT / "docs" / "WORKFLOW.md",
    PROJECT_ROOT / "docs" / "accounting-rules.md",
]

OUTPUT_FILE = PROJECT_ROOT / "AGENTS.md"


def hash_file(path: Path) -> str:
    """计算文件 SHA256 前 8 位。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:8]


def build() -> str:
    """构建 AGENTS.md 内容。"""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    hashes = {f.name: hash_file(f) if f.exists() else "MISSING" for f in SOURCE_FILES}

    lines = [
        "# Code-Insight-Financial — Codex Context (AGENTS.md)",
        "",
        f"> 自动生成于 {now}",
        f"> 源文件: CLAUDE.md (sha256:{hashes['CLAUDE.md']})",
        f">          WORKFLOW.md (sha256:{hashes['WORKFLOW.md']})",
        f">          accounting-rules.md (sha256:{hashes['accounting-rules.md']})",
        "",
        "> [WARN] 本文件由 scripts/build_codex_context.py 自动生成。",
        ">       修改源文件后请重新运行脚本，不要手动编辑此文件。",
        "",
        "---",
        "",
    ]

    # 1. CLAUDE.md 全文
    claude_path = PROJECT_ROOT / "CLAUDE.md"
    if claude_path.exists():
        claude_content = claude_path.read_text(encoding="utf-8")
        lines.append(claude_content)
        lines.append("")
    else:
        lines.append("> [WARN] CLAUDE.md 不存在")
        lines.append("")

    lines.append("---")
    lines.append("")

    # 2. WORKFLOW.md 全文
    workflow_path = PROJECT_ROOT / "docs" / "WORKFLOW.md"
    if workflow_path.exists():
        workflow_content = workflow_path.read_text(encoding="utf-8")
        lines.append(workflow_content)
        lines.append("")
    else:
        lines.append("> [WARN] docs/WORKFLOW.md 不存在")
        lines.append("")

    lines.append("---")
    lines.append("")

    # 3. accounting-rules.md 全文
    rules_path = PROJECT_ROOT / "docs" / "accounting-rules.md"
    if rules_path.exists():
        rules_content = rules_path.read_text(encoding="utf-8")
        lines.append(rules_content)
        lines.append("")
    else:
        lines.append("> [WARN] docs/accounting-rules.md 不存在")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"*Generated at {now} | Source hashes: CLAUDE.md={hashes['CLAUDE.md']}, WORKFLOW.md={hashes['WORKFLOW.md']}, accounting-rules.md={hashes['accounting-rules.md']}*")

    return "\n".join(lines)


def main() -> None:
    print("构建 Codex AGENTS.md...")

    # 检查源文件
    missing = [f for f in SOURCE_FILES if not f.exists()]
    if missing:
        print(f"[WARN] 以下源文件不存在: {[str(f) for f in missing]}")

    # 生成
    content = build()
    OUTPUT_FILE.write_text(content, encoding="utf-8")

    size_kb = len(content) / 1024
    hashes = {f.name: hash_file(f) if f.exists() else "MISSING" for f in SOURCE_FILES}
    print(f"[OK] AGENTS.md 已生成 ({size_kb:.1f} KB)")
    print(f"  CLAUDE.md -> sha256:{hashes['CLAUDE.md']}")
    print(f"  WORKFLOW.md -> sha256:{hashes['WORKFLOW.md']}")
    print(f"  accounting-rules.md -> sha256:{hashes['accounting-rules.md']}")
    print(f"  -> {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
