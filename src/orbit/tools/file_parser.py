"""V15.1 多模态 P3：FileParserRegistry——统一文件解析。

支持 pdf/docx/xlsx/pptx/txt → Markdown。
WHY 统一接口：Agent 不关心文件类型，一个 Tool 全搞定。
"""

from __future__ import annotations

from pathlib import Path

from orbit.tools.models import ToolPermission, ToolSchema

PARSER_SCHEMA = ToolSchema(
    name="file_parser",
    version="1.0.0",
    description="解析文件内容——PDF/Word/Excel/PPT/文本 → Markdown",
    parameters={
        "file_path": {"type": "string", "description": "文件路径"},
    },
    permissions=[ToolPermission.READ],
    allowed_agents=["qa", "developer", "clarifier", "architect", "reviewer"],
    timeout_seconds=30,
    is_async=True,
)


async def file_parser(file_path: str) -> dict:
    """统一文件解析入口。

    Returns:
        {"text": str, "pages": int, "file_type": str}
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    ext = path.suffix.lower()

    if ext == ".pdf":
        return await _parse_pdf(path)
    elif ext in (".docx", ".doc"):
        return await _parse_docx(path)
    elif ext in (".xlsx", ".xls"):
        return await _parse_xlsx(path)
    elif ext == ".pptx":
        return await _parse_pptx(path)
    elif ext in (".txt", ".md", ".py", ".js", ".ts", ".vue", ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini"):
        return await _parse_text(path)
    else:
        raise ValueError(f"不支持的文件类型: {ext}")


async def _parse_pdf(path: Path) -> dict:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text)
    return {"text": "\n\n".join(pages), "pages": len(reader.pages), "file_type": "pdf"}


async def _parse_docx(path: Path) -> dict:
    from docx import Document
    doc = Document(str(path))
    paras = [p.text for p in doc.paragraphs if p.text.strip()]
    # 也提取表格
    for table in doc.tables:
        for row in table.rows:
            cells = [cell.text for cell in row.cells]
            paras.append(" | ".join(cells))
    return {"text": "\n".join(paras), "pages": 1, "file_type": "docx"}


async def _parse_xlsx(path: Path) -> dict:
    from openpyxl import load_workbook
    wb = load_workbook(str(path), read_only=True, data_only=True)
    sheets = []
    for name in wb.sheetnames:
        ws = wb[name]
        rows = []
        for row in ws.iter_rows(values_only=True):
            cells = [str(c) if c is not None else "" for c in row]
            if any(cells):  # 跳过全空行
                rows.append(" | ".join(cells))
        sheets.append(f"## {name}\n" + "\n".join(rows[:500]))  # 上限防 OOM
    wb.close()
    return {"text": "\n\n".join(sheets), "pages": len(wb.sheetnames), "file_type": "xlsx"}


async def _parse_pptx(path: Path) -> dict:
    from pptx import Presentation
    prs = Presentation(str(path))
    slides = []
    for i, slide in enumerate(prs.slides):
        texts = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    if para.text.strip():
                        texts.append(para.text.strip())
        if texts:
            slides.append(f"## Slide {i+1}\n" + "\n".join(texts))
    return {"text": "\n\n".join(slides), "pages": len(prs.slides), "file_type": "pptx"}


async def _parse_text(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    return {"text": text, "pages": 1, "file_type": path.suffix.lstrip(".")}


def _register():
    from orbit.tools.registry import get_registry
    get_registry().register(PARSER_SCHEMA, file_parser)

_register()
