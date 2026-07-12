# Changelog

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
