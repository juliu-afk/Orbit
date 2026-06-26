# PR Review Context Prep — Token 节省工具

把 PR 审核输入链路从「Agent 多轮探索 GitHub → 全量读文件」改为「gh CLI 预下载 → 规则扫描 → Repo Map → 精简输入」。

## 快速开始

```bash
cd .automations/pr-review

# 1. 下载 PR 数据
python scripts/fetch_pr_context.py 85

# 2. 扫描权限字符串
python scripts/scan_permissions.py 85

# 3. 生成 Repo Map
python scripts/generate_repo_map.py 85

# 4. 生成 Reviewer 输入
python scripts/build_reviewer_input.py 85
```

执行后产物在 `.automations/pr-review/85/`：

| 文件 | 说明 |
|------|------|
| `pr-meta.json` | PR 元数据（title, body, files, comments, reviews） |
| `pr.diff` | 完整 diff（Reviewer 仅在需要时读） |
| `changed-files.txt` | 变更文件列表 |
| `rule-scan.md` | `require_permission` 权限字符串扫描报告 |
| `repo-map.md` | 结构化 PR 影响面摘要 |
| `reviewer-input.md` | **精简 Review 上下文——不含完整 diff** |

## 原理

```
gh CLI 预下载 PR 数据 → 确定性规则扫描 → Repo Map 摘要 → Reviewer Agent 精读关键片段
```

核心原则：**LLM 负责判断；脚本负责读取、筛选、定位、统计、比对。**

## 依赖

- Python 3（仅标准库，零新依赖）
- `gh` CLI（需已登录 `gh auth login`）

## Token 节省预估

每次 PR 审核节省 ~5000-15000 token：

- `fetch_pr_context.py`：省 2-3 轮 Agent tool call
- `scan_permissions.py`：省 LLM 读 53 个文件全文查找权限字符串
- `generate_repo_map.py`：省 Agent 盲目探索目录树
- `build_reviewer_input.py`：**最大节省**——reviwer-input.md 不含完整 diff

## 验收

以 PR #85 为例：

```bash
python scripts/fetch_pr_context.py 85
python scripts/scan_permissions.py 85
python scripts/generate_repo_map.py 85
python scripts/build_reviewer_input.py 85
```

应生成全部 6 个产物，且 reviewer-input.md 不含完整 diff。

## 后续规划

- Phase 2: 接 ast-grep 结构化扫描、Repomix 压缩上下文
- Phase 3: 扩展到测试/方案/编码/调试/文档/发布环节
