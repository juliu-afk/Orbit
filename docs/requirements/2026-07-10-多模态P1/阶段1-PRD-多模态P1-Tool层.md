# 阶段1-PRD-多模态P1-Tool层

> 基线：P0 多模态 LLM 网关集成（PR #259 审查中）
> 阶段：P1 — 图片/视频 Tool + OCR + 审计截图
> 日期：2026-07-10

---

## 1. 背景

P0 已完成 Gateway 层——Agent 能通过 `LLMRequest.content` 传入图片/视频。但这只是"通道"——Agent 还需要**工具**来实际操作多媒体内容：下载视频、提取帧、做 OCR、保存审计截图。

P1 构建 Tool 层——让 Agent 从"能看图"升级到"能处理多媒体任务"。

## 2. 用户故事

| 优先级 | 故事 | 价值 |
|--------|------|------|
| **P0** | QA Agent 收到 bug 录屏 → 自动分析并定位问题 | 核心场景——录屏诊断 |
| **P0** | Agent 看到图片中的文字 → 通过 OCR 提取 | 截图/文档信息提取 |
| **P1** | Agent 从技术分享视频中提取知识点 → 存入 Knowledge Graph | 多模态知识摄入 |
| **P1** | Agent 关键决策点自动截图存档 → 审计可追溯 | 审计合规 |
| **P2** | Agent 批量处理长视频 → 自动分段分析 | 长视频处理 |

## 3. 验收标准

### SC1：watch_video Tool（P0 必须）
```
/watch <url> → yt-dlp 下载 → ffmpeg 抽帧 → P0 三梯度模型分析 → 返回结果
```
- 支持 YouTube/B站/本地文件
- 帧预算：≤30s→30帧, 10min→100帧封顶
- 字幕优先：有原生字幕 → 直接带字幕分析，不跑 ASR

### SC2：ocr_document Tool（P0 必须）
```
/ocr <image|pdf> → DeepSeek-OCR 2 API → 结构化文本
```
- 支持图片（截图/扫描件）+ PDF
- 输出 Markdown 格式（保留表格结构）

### SC3：video_capture 审计截图（P1 必须）
```
Agent 关键决策点 → 自动截图 → ffmpeg 去重 → trajectory DB
```
- 决策点：过账/配置变更/数据修改/代码生成
- 帧去重：16×16 灰度 + MAD 阈值 2.0（复用落地方案 §C.1 算法）
- 截图存储在 trajectory 旁，审计时回溯

### SC4：watch.md SKILL 模板（P1）
```
Agent 加载技能模板 → 知道何时/如何调用视频/OCR Tool
```
- 描述 Tool 参数、适用场景、帧预算策略

## 4. 范围

- ✅ **做**：watch_video Tool + ocr_document Tool + video_capture 审计 + SKILL 模板
- ❌ **不做**：GUI Agent / Computer Use（P3）
- ❌ **不做**：前端 Chat 面板多模态输入（P2）
- ❌ **不做**：私有化 MiniCPM-V 部署（P2）
- ❌ **不做**：音频转录（faster-whisper）——优先用原生字幕

## 5. 技术依赖

| 依赖 | 用途 | 许可 | 新增？ |
|------|------|------|--------|
| yt-dlp | 视频下载（1800+ 平台） | Unlicense | ✅ 新增 |
| ffmpeg | 关键帧抽取 + 帧去重 | GPL（系统级） | ⚠️ 系统依赖——需安装 |
| opencv-python-headless | 帧去重算法（备选） | Apache 2.0 | ✅ 可选——ffmpeg 可替代 |
| DeepSeek-OCR 2 API | 文档/表格 OCR | — | ✅ 新 API Key |

## 6. 边缘情况

| 场景 | 预期 |
|------|------|
| 视频无字幕 | 提示用户——"无字幕，是否启用 ASR？（需 faster-whisper）" |
| yt-dlp 下载失败（墙/限流） | 提示用户——"该平台不可用，请提供本地文件" |
| 视频 >1GB | 下载前警告——"视频较大，预计 X MB，是否继续？" |
| OCR 图片模糊 | 返回低置信度标记——"图片模糊，OCR 结果可能不准" |
| 审计截图存储空间满 | 自动淘汰旧截图——保留最近 N 个 session |
| ffmpeg 未安装 | Tool 注册时检测——提示"请安装 ffmpeg" |

## 7. 文件预览

```
src/orbit/tools/
├── video_tools.py        # 新建：watch_video + extract_frames + download_video
├── ocr_tools.py          # 新建：ocr_document + ocr_table
├── __init__.py           # 修改：注册新 Tool

src/orbit/observability/
├── video_capture.py      # 新建：审计截图管线

src/orbit/compose/skills/
├── watch.md              # 新建：视频分析 SKILL 模板

tests/unit/
├── test_video_tools.py   # 新建
├── test_ocr_tools.py     # 新建
```
