# 阶段1-PRD-多模态P3-ComputerUse+文件

> 基线：P0/P1/P2 · 2026-07-10
> 阶段：P3 — Computer Use + FileParserRegistry + Office 读写

---

## 1. 背景

P0-P2 完成了"看图"能力。但 Orbit Agent 仍不能"操作"——不能操控桌面软件、不能解析 Office 文件。P3 补上"手"。

## 2. 用户故事

| 优先级 | 故事 | 价值 |
|--------|------|------|
| **P0** | Agent 能截图+分析+操作桌面（点击/输入/滚动） | 端到端 GUI 自动化测试 |
| **P0** | Agent 能解析 pdf/docx/xlsx 文件内容 | 代码审查/文档分析输入 |
| **P1** | Agent 能生成/修改 Office 文件 | 产出 word/excel/ppt |
| **P2** | Agent 自主完成完整应用操作流程 | 全自动回归测试 |

## 3. 验收标准

| # | 标准 |
|---|------|
| **SC1** | `gui_agent` Tool：截图→P0 模型分析→定位元素→PyAutoGUI 操作→验证 |
| **SC2** | `file_parser` Tool：pdf/docx/xlsx 统一读取接口，输出 Markdown |
| **SC3** | `office_write` Tool：生成 .xlsx/.docx/.pptx 文件 |

## 4. 范围

- ✅ gui_agent Tool（mss 截图 + P0 VisionAdapter 分析 + PyAutoGUI 操作）
- ✅ FileParserRegistry（pypdf + python-docx + openpyxl 统一读取）
- ✅ office_write（openpyxl + python-docx + python-pptx 生成）
- ❌ 不做复杂 GUI 操作链编排（P3 只做单步操作）
- ❌ 不做跨平台兼容（先 Windows）

## 5. 依赖

| 依赖 | 许可 | 新增 |
|------|------|------|
| mss | MIT | ✅ |
| PyAutoGUI | BSD | ✅ |
| pypdf | BSD | ✅ |
| python-docx | MIT | ✅ |
| openpyxl | MIT | ✅ |
| python-pptx | MIT | ✅ |
