# compose:watch — 视频理解技能

> V15.1 多模态 P1 · Agent 视频分析技能

---

## 元数据

```yaml
name: compose:watch
version: 1.0.0
description: 视频理解技能——下载、抽帧、转录、分析。让 Agent "看懂"视频。
phase: implement
tools: [watch_video, ocr_document]
agent_role: [qa, developer, clarifier]
```

## 触发条件

Agent 遇到以下场景时加载此技能：
- 用户发送视频 URL（YouTube、B站等）
- 用户发送本地视频文件（.mp4/.mov）
- 用户描述 bug 并要求"看录屏"
- 用户要求"分析这个视频"

## 工作流

```
1. 判断视频来源
   ├── URL → watch_video(url=..., question=...)
   └── 本地文件 → watch_video(url="/path/to/file.mp4", question=...)

2. 视频分析策略
   ├── 短视频(<3min) → 分析全部内容
   ├── 中等视频(3-10min) → 聚焦用户问题
   └── 长视频(>10min) → 先用 start=... end=... 定位目标片段

3. 结果处理
   ├── Bug诊断 → 输出：时间点 + UI元素 + 根因 + 相关代码
   ├── 技术分享 → 提取知识点 → 存入 Knowledge Graph
   └── 一般分析 → 结构化总结
```

## 帧预算建议

```
≤30s   → 默认 30 帧（密集采样）
30s-3m → 默认 60 帧（平衡）
>3m    → 默认 100 帧（广度优先）
>10m   → 建议用 start/end 参数聚焦片段，而非全片分析
```

## 字幕策略

- 优先使用原生字幕（免费，yt-dlp --write-subs）
- 无字幕 → 告知用户，询问是否启用 ASR（需 faster-whisper）
- 中文视频优先 zh-Hans 字幕，其次 zh，最后 en

## 成本注意

- watch_video 走 P0 三梯度路由——T2 标准（免费）
- 长视频自动降级 T3（GLM-4.6V 付费）
- OCR 走 DeepSeek-OCR 2（$0.15/M tokens）
