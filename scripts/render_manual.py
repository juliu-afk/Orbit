#!/usr/bin/env python3
"""Orbit 说明书渲染器 —— 零依赖 Markdown → HTML。

WHY 零依赖：项目禁止随意新增依赖（见 CONTRIBUTING.md），且说明书需长期可重复生成。
本脚本只覆盖 docs/manual/ 实际用到的 Markdown 子集：标题、表格、代码块、
引用、列表、水平线、加粗、行内代码、链接。不追求通用 Markdown 兼容。

用法：
    python scripts/render_manual.py            # 渲染 docs/manual/*.md → docs/manual/html/*.html
    python scripts/render_manual.py <src> <out> # 自定义源目录/输出目录
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

# 行内规则：先抽取行内代码为占位符，避免其内部被加粗/链接规则误伤，最后还原。
_INLINE_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def _render_inline(text: str) -> str:
    # 1) 转义 HTML 特殊字符（先做，防止注入与显示错乱）
    text = html.escape(text, quote=False)
    # 2) 行内代码抽出为占位符
    codes: list[str] = []

    def _stash(m: re.Match[str]) -> str:
        codes.append(m.group(1))
        return f"\x00{len(codes) - 1}\x00"

    text = _INLINE_CODE.sub(_stash, text)
    # 3) 加粗、链接（.md 链接改指向同目录 .html，保证站内导航闭环）
    text = _BOLD.sub(r"<strong>\1</strong>", text)

    def _linkify(m: re.Match[str]) -> str:
        label, href = m.group(1), m.group(2)
        if href.endswith(".md"):
            href = href[:-3] + ".html"
        elif ".md#" in href:
            href = href.replace(".md#", ".html#")
        return f'<a href="{href}">{label}</a>'

    text = _LINK.sub(_linkify, text)
    # 4) 还原行内代码
    for i, code in enumerate(codes):
        text = text.replace(f"\x00{i}\x00", f"<code>{html.escape(code, quote=False)}</code>")
    return text


def _slugify(text: str) -> str:
    # 标题锚点：保留中英文与数字，其余转连字符
    text = re.sub(r"<[^>]+>", "", text)
    text = text.strip().lower()
    text = re.sub(r"[^\w一-鿿]+", "-", text)
    return text.strip("-")


def _is_table_sep(line: str) -> bool:
    # 表格分隔行形如 |---|:--:|---| 或 --- | ---
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    return bool(cells) and all(re.fullmatch(r":?-{2,}:?", c) for c in cells)


def _render_table(rows: list[str]) -> str:
    def cells(line: str) -> list[str]:
        return [c.strip() for c in line.strip().strip("|").split("|")]

    header = cells(rows[0])
    body = [cells(r) for r in rows[2:]]
    out = ["<table>", "<thead><tr>"]
    out += [f"<th>{_render_inline(c)}</th>" for c in header]
    out.append("</tr></thead><tbody>")
    for row in body:
        out.append("<tr>" + "".join(f"<td>{_render_inline(c)}</td>" for c in row) + "</tr>")
    out.append("</tbody></table>")
    return "\n".join(out)


def md_to_html_body(md: str) -> str:
    lines = md.split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)
    in_code = False
    code_buf: list[str] = []
    list_open = False

    def close_list() -> None:
        nonlocal list_open
        if list_open:
            out.append("</ul>")
            list_open = False

    while i < n:
        line = lines[i]

        # 代码块围栏
        if line.startswith("```"):
            if in_code:
                out.append(
                    "<pre><code>" + html.escape("\n".join(code_buf), quote=False) + "</code></pre>"
                )
                code_buf = []
                in_code = False
            else:
                close_list()
                in_code = True
            i += 1
            continue
        if in_code:
            code_buf.append(line)
            i += 1
            continue

        stripped = line.strip()

        # 空行
        if not stripped:
            close_list()
            i += 1
            continue

        # 水平线
        if stripped in ("---", "***", "___"):
            close_list()
            out.append("<hr>")
            i += 1
            continue

        # 表格（当前行含 | 且下一行是分隔行）
        if "|" in line and i + 1 < n and _is_table_sep(lines[i + 1]):
            close_list()
            tbl = [line, lines[i + 1]]
            j = i + 2
            while j < n and "|" in lines[j] and lines[j].strip():
                tbl.append(lines[j])
                j += 1
            out.append(_render_table(tbl))
            i = j
            continue

        # 标题
        m = re.match(r"(#{1,6})\s+(.*)", line)
        if m:
            close_list()
            level = len(m.group(1))
            content = _render_inline(m.group(2))
            out.append(f'<h{level} id="{_slugify(m.group(2))}">{content}</h{level}>')
            i += 1
            continue

        # 引用
        if stripped.startswith(">"):
            close_list()
            quote = [re.sub(r"^\s*>\s?", "", lines[i])]
            j = i + 1
            while j < n and lines[j].strip().startswith(">"):
                quote.append(re.sub(r"^\s*>\s?", "", lines[j]))
                j += 1
            out.append("<blockquote>" + _render_inline(" ".join(quote)) + "</blockquote>")
            i = j
            continue

        # 列表项（- 或 数字.）
        m = re.match(r"\s*(?:[-*]|\d+\.)\s+(.*)", line)
        if m:
            if not list_open:
                out.append("<ul>")
                list_open = True
            out.append(f"<li>{_render_inline(m.group(1))}</li>")
            i += 1
            continue

        # 普通段落
        close_list()
        out.append(f"<p>{_render_inline(stripped)}</p>")
        i += 1

    close_list()
    if in_code:  # 容错：文件以未闭合代码块结尾
        out.append("<pre><code>" + html.escape("\n".join(code_buf), quote=False) + "</code></pre>")
    return "\n".join(out)


_CSS = """
:root { --fg:#1f2328; --bg:#ffffff; --muted:#656d76; --border:#d0d7de;
        --accent:#0969da; --code-bg:#f6f8fa; }
@media (prefers-color-scheme: dark) {
  :root { --fg:#e6edf3; --bg:#0d1117; --muted:#8b949e; --border:#30363d;
          --accent:#4493f8; --code-bg:#161b22; } }
* { box-sizing: border-box; }
body { margin:0; color:var(--fg); background:var(--bg);
       font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans CJK SC",
       "Microsoft YaHei",Helvetica,Arial,sans-serif; line-height:1.6; }
main { max-width:960px; margin:0 auto; padding:2rem 1.5rem 4rem; }
h1,h2,h3,h4 { line-height:1.25; margin-top:1.6em; }
h1 { border-bottom:2px solid var(--border); padding-bottom:.3em; }
h2 { border-bottom:1px solid var(--border); padding-bottom:.25em; }
a { color:var(--accent); text-decoration:none; }
a:hover { text-decoration:underline; }
code { background:var(--code-bg); padding:.15em .35em; border-radius:6px;
       font-family:"SFMono-Regular",Consolas,"Liberation Mono",monospace; font-size:.9em; }
pre { background:var(--code-bg); padding:1rem; border-radius:8px; overflow-x:auto;
      border:1px solid var(--border); }
pre code { background:none; padding:0; }
blockquote { margin:1em 0; padding:.4em 1em; color:var(--muted);
             border-left:4px solid var(--border); }
table { border-collapse:collapse; width:100%; margin:1em 0; display:block; overflow-x:auto; }
th,td { border:1px solid var(--border); padding:.5em .8em; text-align:left; }
th { background:var(--code-bg); }
hr { border:none; border-top:1px solid var(--border); margin:2em 0; }
ul { padding-left:1.5em; }
"""

_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{css}</style>
</head>
<body><main>
{body}
</main></body>
</html>
"""


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "docs" / "manual"
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else src / "html"
    out.mkdir(parents=True, exist_ok=True)

    md_files = sorted(src.glob("*.md"))
    if not md_files:
        print(f"no markdown found: {src}")
        return 1

    for md_path in md_files:
        text = md_path.read_text(encoding="utf-8")
        # 标题取首个 # 行
        m = re.search(r"^#\s+(.*)", text, re.MULTILINE)
        title = re.sub(r"<[^>]+>", "", m.group(1)) if m else md_path.stem
        body = md_to_html_body(text)
        page = _PAGE.format(title=html.escape(title), css=_CSS, body=body)
        (out / f"{md_path.stem}.html").write_text(page, encoding="utf-8")
        print(f"[ok] {md_path.name} -> html/{md_path.stem}.html")

    print(f"\ndone: {len(md_files)} pages -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
