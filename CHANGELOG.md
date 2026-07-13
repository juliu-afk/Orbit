# Changelog

## [v0.49.0] — 2026-07-13

### Added
- **ChatterAgent 文件引用自动读取** (#297): 用户在聊天中用反引号引用文件路径（如 `src/main.py`）时，自动读取并注入 LLM 上下文。代码文件→read_file，图片→OCR，文档→file_parser，视频 URL→提示 /watch。
- **斜杠命令** (#297): `/watch <url>` 视频分析、`/ocr <file>` 图片 OCR、`/parse <file>` 文档解析——三条独立 WebSocket 命令通路。
- **Agent 级 spawn_subagent 工具** (#298): Agent 在 ReAct 循环中可平行 spawn 子 Agent（architect/developer/reviewer/qa）。深度限制 1 层，全局 MAX_CONCURRENT=4 共享。
- **多媒体工具权限修复** (#297): `file_parser`/`ocr_document`/`watch_video`/`gui_agent` 加入 ROLE_TOOLS——之前因缺失对 Agent 不可见。

### Fixed
- **OCR/file_parser workspace 隔离** (#297): `ocr_document` + `file_parser` 新增 `_guard_path`，防止通过 OCR 读取工作区外敏感文件并发送到外部 API。
- **视频 URL 检测覆盖不全** (#297): 扩展 `_VIDEO_URL_RE` + 新增 `_VIDEO_FILE_URL_RE`——覆盖 Twitch/TikTok/X + 直链 .mp4/.mov。

## [v0.48.0] — 2026-07-13

### Added
- **Windows 休眠/屏保阻止** (#287): `launcher.py` 启动时调 `SetThreadExecutionState`，Orbit 长时间跑 Agent 任务期间 PC 不进入休眠。仅 win32，零依赖。

### Fixed
- **settings 不持久化** (#290): watch 对象用缩写键名 `{t,fl,ar,...}` 但 `UserSettings` 接口期望完整键名 `{theme,fileTreeLeft,...}` → `load()` 时 `{...DEFAULTS, ...{t:"light"}}` 不覆盖 `DEFAULTS.theme`（键名不匹配）→ 设置刷新后丢失。改为完整键名 + `watch<UserSettings>` 泛型。

### Changed
- **底部状态栏移除窗口控制按钮** (#291): 移除 ─ □ ✕ 三按钮——应在 Tauri 自定义标题栏处理，不在底部状态栏。

---

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。
