# Changelog

## [v0.49.0] — 2026-07-14

### Added
- **聊天框四级权限模式** (#299): Manual / Edit Automatically / Plan / Auto Mode 对标 Claude Code for VS Code。模式状态通过 WebSocket 传后端，ToolRegistry.dispatch() 加四级门禁。
- **SkillRegistry 通用注册中心** (#299): 扫描 SKILL.md → 斜杠命令动态匹配 + 自然语言自动匹配（≥0.7 置信度直接触发）。新增 Skills CRUD + 版本管理 + 回滚 API。
- **ComposeOrchestrator.run_skill_chain()** (#299): 聊天框可直接触发多步编排链，不需要写 spec YAML。
- **Skill 可视化管理面板** (#299): 前端 `/skills` 路由，列表+编辑器+版本历史。
- **Skill 热更新** (#299): 文件系统 watcher 监听 SKILL.md 变化 → 自动重载。
- **31 个新模块单元测试** (#299): `test_skills/` 覆盖 registry/match/CRUD/version/context。

### Changed
- **InputBox 模式按钮**: Ask/Edit/Agent → Manual/Edit Automatically/Plan/Auto Mode
- **ChatterAgent prompt**: 新增 skill + chain 自然语言匹配规则
- **ToolRegistry**: dispatch() 加 `_check_mode_gate()` 四级权限门禁

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
