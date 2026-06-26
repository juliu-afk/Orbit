"""fetch_pr_context.py — 根据 PR 号预下载 GitHub PR 数据。

输入: PR number (命令行参数)
输出: .automations/pr-review/{PR}/
        pr-meta.json      — PR 元数据 (title, body, files, comments, reviews)
        pr.diff           — 完整 diff
        changed-files.txt — 变更文件列表（每行一个路径）

依赖: gh CLI (需已登录)
"""

import json
import subprocess
import sys
from pathlib import Path

# Windows GBK 终端兼容: 强制 UTF-8 输出
if sys.stdout.encoding != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


PROJECT_ROOT = Path(__file__).resolve().parents[3]  # Code-Insight-Financial/
AUTOMATIONS_DIR = PROJECT_ROOT / ".automations" / "pr-review"


def run_gh(args: list[str]) -> str:
    """运行 gh 命令，失败时打印错误并退出。"""
    try:
        result = subprocess.run(
            ["gh", *args],
            capture_output=True, text=True, encoding="utf-8",
            cwd=str(PROJECT_ROOT),
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            # 常见错误友好提示
            if "Could not resolve to a Pull Request" in stderr:
                print(f"错误: PR 不存在，请检查 PR 号是否正确。\n{stderr}")
            elif "not authenticated" in stderr.lower() or "auth" in stderr.lower():
                print(f"错误: gh CLI 未登录，请运行 `gh auth login`。\n{stderr}")
            else:
                print(f"错误: gh 命令执行失败。\n{stderr}")
            sys.exit(result.returncode)
        return result.stdout
    except FileNotFoundError:
        print("错误: 未找到 gh CLI。请安装 GitHub CLI: https://cli.github.com/")
        sys.exit(1)


def fetch(pr_number: int) -> None:
    """下载 PR 数据并写入输出文件。"""
    output_dir = AUTOMATIONS_DIR / str(pr_number)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. 下载 PR 元数据
    print(f"正在获取 PR #{pr_number} 元数据...")
    meta_json = run_gh([
        "pr", "view", str(pr_number),
        "--json", "title,body,files,comments,reviews",
    ])
    # 验证 JSON 格式
    meta = json.loads(meta_json)
    meta_path = output_dir / "pr-meta.json"
    meta_path.write_text(meta_json, encoding="utf-8")
    print(f"  ✓ pr-meta.json ({len(meta.get('files', []))} 个文件, {len(meta.get('comments', []))} 条评论)")

    # 2. 下载 diff
    print("正在获取 diff...")
    diff = run_gh(["pr", "diff", str(pr_number)])
    diff_path = output_dir / "pr.diff"
    diff_path.write_text(diff, encoding="utf-8")
    diff_lines = diff.count('\n')
    print(f"  ✓ pr.diff ({diff_lines} 行)")

    # 3. 提取变更文件列表
    changed_files = [f["path"] for f in meta.get("files", [])]
    files_path = output_dir / "changed-files.txt"
    files_path.write_text("\n".join(changed_files) + "\n", encoding="utf-8")
    print(f"  ✓ changed-files.txt ({len(changed_files)} 个文件)")

    print(f"\n输出目录: {output_dir}")


def main() -> None:
    if len(sys.argv) < 2:
        print("用法: python fetch_pr_context.py <PR_NUMBER>")
        print("示例: python fetch_pr_context.py 85")
        sys.exit(1)

    try:
        pr_number = int(sys.argv[1])
    except ValueError:
        print(f"错误: PR 号必须是数字，收到: {sys.argv[1]}")
        sys.exit(1)

    fetch(pr_number)


if __name__ == "__main__":
    main()
