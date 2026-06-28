---
name: pr-review
version: "1.0"
description: |
  Orbit 仓库 PR 审查工作流。基于 P0/P1/P2 三级分类 + CI 硬门禁，
  使用 gh CLI 双轨工作流（checkout + comment）。
trigger_keywords:
  - "审一下"
  - "审查"
  - "复审"
  - "PR"
  - "code review"
---

# PR 审查 Skill —— Orbit 仓库专用

## 一、审查门禁（硬性，缺一不可）

| 门禁 | 阈值 | 检查方式 |
|------|------|----------|
| P0 清零 | 0 项 | 手动审查 |
| P1 清零 | 0 项 | 手动审查 |
| CI 全绿 | 10/10 pass | `gh pr checks <n>` |
| 覆盖率 | ≥80% | `pytest --cov-fail-under=80` |
| black 格式化 | pass | CI lint-typecheck |

**规则**：任一门禁未通过 → 否决（Request Changes），不可合入。

## 二、问题分级

| 级别 | 定义 | 示例 |
|------|------|------|
| **P0** | 阻塞级：功能崩溃、安全漏洞、数据丢失 | mock 失效调用真实 API；`allow_outside=True` 导致任意文件写入 |
| **P1** | 功能缺陷：逻辑错误、降级失效、行为不一致 | 裸 except 窄化漏掉 `TimeoutError`；commit message 与代码不符 |
| **P2** | 代码质量：注释/docstring/空行/噪音提交 | docstring 回退；`.orbit/memory/MEMORY.md` 进 git |

## 三、审查工作流

### 3.1 获取 PR 信息
```bash
gh pr view <n> --repo <owner/repo> --json number,title,state,commits,files,headRefName,mergeStateStatus
gh pr diff <n> --repo <owner/repo>
gh pr checks <n> --repo <owner/repo>
```

### 3.2 本地验证（网络允许时）
```bash
gh pr checkout <n> --repo <owner/repo> --branch pr<n>_verify
python -m pytest tests/unit/ -q --cov=src/orbit --cov-fail-under=80
```

### 3.3 审查报告模板

```markdown
## PR #<n> 审查报告（R<round>）

**审查结果：<结论>**

### 变更摘要
| 文件 | 变更 | 评估 |
|------|------|------|
| ... | ... | ... |

### 问题清单
| 级别 | 编号 | 问题 | 说明 |
|------|------|------|------|
| P0 | P0-1 | ... | ... |

### 门禁
| 项 | 状态 |
|----|------|
| P0 清零 | ... |
| CI 全绿 | ... |
| 覆盖率 ≥80% | ... |

### 结论
...
```

### 3.4 上传到 GitHub
```bash
cat > /tmp/pr<n>_review.md << 'EOF'
<报告内容>
EOF
gh pr comment <n> --repo <owner/repo> --body-file /tmp/pr<n>_review.md
```

## 四、已知陷阱（Gotcha）

1. **裸 except 窄化**：`except Exception` → `(RuntimeError, OSError, ImportError)` 会漏掉 `asyncio.TimeoutError`（非 OSError 子类）、litellm 业务异常。熔断器不记录失败 → 与实际失步。
2. **docker/kubectl 白名单**：攻击面远超模式匹配覆盖能力，`docker run --privileged -v /:/host alpine rm -rf /host` 可容器逃逸。应单独实现参数校验器。
3. **filesystem 路径解析**：`WorkspaceGuard.validate()` 内部执行 `Path(path).resolve()`，其结果取决于 cwd。必须先 `(_WORKSPACE_ROOT / path).resolve()` 再传入 guard。
4. **测试 fixture 硬编码路径**：`/fake/repo` 在 Linux CI 触发 `PermissionError`。统一使用 `tmp_path`。
5. **mock 随重构失效**：`generate_stream()` 重构为委托 `generate_stream_with_tools()` 后，旧 mock 仍指向 `_stream_completion` → 调用真实 API → CI 超时/认证错误。
6. **state 被无条件覆盖**：`resolve()` 方法末尾 `record.state = target_state` 会覆盖 `AUTO_PR` 分支设置的 `PR_OPEN`。应改为条件赋值。
7. **运行时记忆文件进 git**：`.orbit/memory/MEMORY.md` 设计为追加模式，37 处重复标题说明是噪音。应加入 `.gitignore`。
8. **SQLite database locked**：unit-test (3.11) 偶发 flaky fail，与 PR 无关，可忽略。

## 五、多 PR 并行审查

当用户同时要求审查多个 PR 时：
1. 并行 `gh pr view` + `gh pr diff` 获取信息
2. 按 PR 编号顺序逐个审查
3. 每份报告独立文件 `/tmp/pr<n>_review.md`
4. 最后统一 `gh pr comment` 上传

## 六、复审（R2+）流程

1. 重新 `gh pr view` 获取最新 commits
2. 对比 R1 问题清单逐项验证
3. 如全部解决 → APPROVED
4. 如有遗留 → 更新问题清单，继续否决
5. 上传 R2 报告到 GitHub
