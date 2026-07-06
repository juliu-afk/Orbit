# 阶段 1 PRD — UX 短期优化（7 项）

> 基线：[Orbit 安全与UX评估报告](../../research/Orbit-安全与UX评估报告-2026-07-07.html)
> 范围：短期 Wins（1-2 周，低工作量高影响）

---

## 1. 背景

UX 评分 2.8/5.0。短期 7 项改进可提升至 ~3.5。全部前端改动，零后端。

## 2. 用户故事

| # | 功能 | 现状 | 用户故事 |
|---|------|------|---------|
| 1 | 模式选择器 | 无 | 用户想区分"提问"vs"编辑"vs"自主执行"，而非所有输入走同一通道 |
| 2 | Diff 可视化 | `<pre>` 原始文本 | 用户想看到并排 diff，能 Accept/Reject 每处改动 |
| 3 | 消息历史搜索 | 无 | 用户想在聊天记录中搜索关键词 |
| 4 | 非阻塞连接提示 | 全屏阻断遮罩 | 连接断开时不应完全阻断 UI |
| 5 | 统一连接管理 | 3 套独立连接 | 统一管理 WS/SSE/HTTP poll 的连接状态 |
| 6 | 骨架加载 | 无 | 面板加载时应显示骨架屏而非空白 |
| 7 | 设置 UI | localStorage 隐形 | 用户应能可视化配置 Agent 行为/模型/快捷键 |

## 3. 验收标准

| AC | 描述 |
|----|------|
| AC-1 | 输入框上方显示 Ask / Edit / Agent 三按钮模式选择器 |
| AC-2 | CodeDiffPanel 替换为 MonacoDiffEditor，含 Approve/Reject |
| AC-3 | ChatPanel 顶部搜索框，输入关键词过滤消息 |
| AC-4 | ConnectionOverlay 改为顶部非阻塞 banner + 自动重试倒计时 |
| AC-5 | useConnectionManager 统一管理 WS+SSE+HTTP 连接状态 |
| AC-6 | ChatPanel/FileTree/Monaco 加载时显示骨架屏 |
| AC-7 | 设置面板可配置 theme/快捷键/Agent 模型等 |
| AC-8 | 现有测试保持通过 + 前端构建 zero TS errors |

## 4. Non-Goals

- 完整 Agent 计划展示（中期 #8）
- @-mention 自动完成（中期 #9）
- Rules/Memory 面板（中期 #10）
- 命令面板（中期 #11）
