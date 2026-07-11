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
    # 双语约定：块级文本用 `||`（前后空格可有可无）分隔中英——中文在前、英文在后。
    # 处理顺序：先抽出行内代码与链接（保护其中的 |），再按 `||` 切分双语，最后还原。
    # WHY：链接标签内也可能带 `||`（如导航"返回目录 || Back"），必须先把链接整体保护起来，
    #       否则 `||` 会把 [label](href) 拦腰截断，导致 Markdown 链接失效。
    codes: list[str] = []
    links: list[str] = []

    def _stash_code(m: re.Match[str]) -> str:
        codes.append(m.group(1))
        return f"\x00C{len(codes) - 1}\x00"

    text = _INLINE_CODE.sub(_stash_code, text)

    def _stash_link(m: re.Match[str]) -> str:
        label, href = m.group(1), m.group(2)
        if href.endswith(".md"):
            href = href[:-3] + ".html"
        elif ".md#" in href:
            href = href.replace(".md#", ".html#")
        links.append(f'<a href="{html.escape(href, quote=True)}">{_emit(label, codes, [])}</a>')
        return f"\x00L{len(links) - 1}\x00"

    text = _LINK.sub(_stash_link, text)
    return _emit(text, codes, links)


def _emit(text: str, codes: list[str], links: list[str]) -> str:
    # 按 `||` 切分双语；英文包进 <span class="en">（小号灰色块，紧贴中文下方）
    if "||" in text:
        zh, en = re.split(r"\s*\|\|\s*", text, maxsplit=1)
        return f'{_plain(zh, codes, links)}<span class="en">{_plain(en, codes, links)}</span>'
    return _plain(text, codes, links)


def _plain(text: str, codes: list[str], links: list[str]) -> str:
    # 转义 → 加粗 → 还原代码/链接占位符（还原在转义之后，避免 <a>/<code> 被二次转义）
    text = html.escape(text, quote=False)
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    for i, code in enumerate(codes):
        text = text.replace(f"\x00C{i}\x00", f"<code>{html.escape(code, quote=False)}</code>")
    for i, link in enumerate(links):
        text = text.replace(f"\x00L{i}\x00", link)
    return text


def _slugify(text: str) -> str:
    # 标题锚点：保留中英文与数字，其余转连字符
    text = re.sub(r"<[^>]+>", "", text)
    text = text.strip().lower()
    text = re.sub(r"[^\w一-鿿]+", "-", text)
    return text.strip("-")


# 单元格分隔：只按"单个 |"切分，不切分双语分隔符 `||`（否则 `中文 || English` 被误拆成空列）
_CELL_SPLIT = re.compile(r"(?<!\|)\|(?!\|)")


def _split_cells(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in _CELL_SPLIT.split(s)]


def _is_table_sep(line: str) -> bool:
    # 表格分隔行形如 |---|:--:|---| 或 --- | ---
    cells = _split_cells(line)
    return bool(cells) and all(re.fullmatch(r":?-{2,}:?", c) for c in cells)


def _render_table(rows: list[str]) -> str:
    header = _split_cells(rows[0])
    body = [_split_cells(r) for r in rows[2:]]
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
.en { display:block; font-size:.82em; font-weight:400; color:var(--muted);
      line-height:1.45; margin-top:.15em; }
h1 .en, h2 .en, h3 .en, h4 .en { font-size:.6em; margin-top:.2em; }
th .en, td .en { font-size:.8em; }
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
