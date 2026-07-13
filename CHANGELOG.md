# Changelog

## [v0.49.0] — 2026-07-14

### Added
- **ChatterAgent 文件引用自动读取** (#297): 用户在聊天中用反引号引用文件路径时自动读取并注入 LLM 上下文。
- **斜杠命令** (#297): `/watch <url>` 视频分析、`/ocr <file>` 图片 OCR、`/parse <file>` 文档解析。
- **Agent 级 spawn_subagent 工具** (#298): Agent 在 ReAct 循环中可平行 spawn 子 Agent，MAX_CONCURRENT=4。
- **聊天框四级权限模式** (#299): Manual / Edit Automatically / Plan / Auto Mode。
- **SkillRegistry 通用注册中心** (#299): SKILL.md 自动发现 + 斜杠/自然语言匹配 + CRUD + 版本回滚。
- **ComposeOrchestrator.run_skill_chain()** (#299): 聊天框直接触发多步编排。
- **Skill 管理面板** (#299): 前端 `/skills` 可视化编辑 + 热更新。

### Fixed
- **OCR/file_parser workspace 隔离** (#297): 新增 `_guard_path` 防路径穿越。
- **视频 URL 检测覆盖不全** (#297): 扩展 Twitch/TikTok/X + 直链。

### Changed
- **InputBox 模式按钮**: Ask/Edit/Agent → Manual/Edit Automatically/Plan/Auto Mode
- **ToolRegistry**: dispatch() 加四级权限门禁

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
