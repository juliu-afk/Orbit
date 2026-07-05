---
name: compose:verify
description: 验证工作流——全量测试+覆盖率+spec对照+差距报告（对标 intended-vs-implemented）
phase: verify
tools: [exec_command, read_file]
agent_role: qa
---
# compose:verify

## 思考框架（必须遵守——对标 pm-ai-shipping intended-vs-implemented 差距检测）

### 验证三步法

#### 1. 自动化门禁（硬性——任一不通过 = FAIL）
- [ ] 单元测试 100% 通过: `pytest tests/unit/ -q`
- [ ] 集成测试 100% 通过: `pytest tests/integration/ -q`
- [ ] 覆盖率 ≥ 门禁线: `--cov-fail-under=80`
- [ ] Lint 0 错误: `ruff check`
- [ ] 类型检查 0 错误: `mypy src/`

#### 2. Spec 对照（软性——有差距标注 WARN）
逐条对照 spec/PRD 验收标准:
```
验收标准 1: "用户上传 CSV 后 5 秒内看到预览"
  → 实测: 10MB CSV 耗时 45 秒 ❌ GAP
  → 建议: 流式解析 + 前端分页

验收标准 2: "所有 API 端点需认证"
  → 检查: 3 个端点未加认证中间件 ❌ GAP
  → 位置: routes/public.py:12, routes/export.py:8, routes/health.py:5
```

#### 3. 回归检查（触及核心模块时强制）
- [ ] 相关模块已有测试全部通过（不只新增测试）
- [ ] 无性能退化（如有性能基线，对比关键路径耗时）

### 验证报告原则
- **不要只说"通过"**——列出每个门禁的实际结果
- **GAP 必须标注位置**——文件:行号 + 实测值 vs 期望值
- **不确定标注 UNCERTAIN**——不能验证的验收标准标注原因

## 流程
1. 跑全量单元测试——pytest tests/unit/ -q
2. 跑集成测试——pytest tests/integration/ -q
3. 检查覆盖率——--cov-fail-under=80
4. 跑 lint——ruff check
5. Spec 对照——逐条验收标准 vs 实际行为
6. 汇总验证报告

## 门禁
- 单元测试 100% 通过
- 集成测试 100% 通过
- 覆盖率 ≥ 80%
- lint 0 错误
- Spec 对照无 CRITICAL 级 GAP（WARN 级不阻塞，但必须记录）

## 输出格式
```markdown
# 验证报告: [需求简称]

## 自动化门禁
| 门禁 | 结果 | 详情 |
|------|------|------|
| 单元测试 | ✅/❌ | N passed, N failed |
| 集成测试 | ✅/❌ | N passed, N failed |
| 覆盖率 | XX% | 门禁: 80% |
| lint | ✅/❌ | N errors |
| 类型检查 | ✅/❌ | N errors |

## Spec 对照
| 验收标准 | 结果 | 证据/差距 |
|---------|------|----------|
| ... | ✅/❌/⚠️ | ... |

## 失败用例（如有）
- test_name: 错误信息（已修复/待修复）

## 整体判定: PASS / FAIL / PASS_WITH_WARNINGS
```
