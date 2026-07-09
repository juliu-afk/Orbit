"""V15.1 多模态 P3：Office 文件生成 Tool。

/create <type> → 生成 .xlsx / .docx / .pptx 文件。
WHY Agent 需要写文件：测试报告、数据导出、文档生成。
"""

from __future__ import annotations

from pathlib import Path

from orbit.tools.models import ToolPermission, ToolSchema

OFFICE_SCHEMA = ToolSchema(
    name="office_create",
    version="1.0.0",
    description="生成 Office 文件——Excel/Word/PPT",
    parameters={
        "file_type": {"type": "string", "description": "xlsx | docx | pptx"},
        "output_path": {"type": "string", "description": "输出文件路径"},
        "content": {"type": "object", "description": "内容——xlsx: [[row1],[row2],...], docx: [paragraph,...], pptx: [{title, bullets},...]"},
    },
    permissions=[ToolPermission.WRITE],
    allowed_agents=["developer", "qa", "architect"],
    timeout_seconds=30,
    is_async=True,
)


async def office_create(file_type: str, output_path: str, content: dict | list) -> dict:
    """生成 Office 文件。

    Returns:
        {"path": str, "file_type": str, "size_bytes": int}
    """
    if file_type == "xlsx":
        return await _create_xlsx(output_path, content)
    elif file_type == "docx":
        return await _create_docx(output_path, content)
    elif file_type == "pptx":
        return await _create_pptx(output_path, content)
    else:
        raise ValueError(f"不支持的文件类型: {file_type}，支持: xlsx/docx/pptx")


async def _create_xlsx(path: str, content: dict | list) -> dict:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"

    rows = content if isinstance(content, list) else content.get("rows", [])
    for row in rows:
        ws.append(row if isinstance(row, list) else [row])

    wb.save(path)
    return {"path": path, "file_type": "xlsx", "size_bytes": Path(path).stat().st_size}


async def _create_docx(path: str, content: dict | list) -> dict:
    from docx import Document
    doc = Document()

    title = content.get("title", "") if isinstance(content, dict) else ""
    if title:
        doc.add_heading(title, level=1)

    paragraphs = content if isinstance(content, list) else content.get("paragraphs", [])
    for p in paragraphs:
        doc.add_paragraph(str(p))

    doc.save(path)
    return {"path": path, "file_type": "docx", "size_bytes": Path(path).stat().st_size}


async def _create_pptx(path: str, content: dict | list) -> dict:
    from pptx import Presentation
    from pptx.util import Inches
    prs = Presentation()

    slides = content if isinstance(content, list) else content.get("slides", [])
    for slide_data in slides:
        slide = prs.slides.add_slide(prs.slide_layouts[1])  # Title + Content
        if isinstance(slide_data, dict):
            slide.shapes.title.text = slide_data.get("title", "")
            bullets = slide_data.get("bullets", [])
            if bullets and slide.placeholders[1].has_text_frame:
                tf = slide.placeholders[1].text_frame
                for b in bullets:
                    p = tf.add_paragraph()
                    p.text = str(b)
                    p.level = 0

    prs.save(path)
    return {"path": path, "file_type": "pptx", "size_bytes": Path(path).stat().st_size}


def _register():
    from orbit.tools.registry import get_registry
    get_registry().register(OFFICE_SCHEMA, office_create)

_register()
