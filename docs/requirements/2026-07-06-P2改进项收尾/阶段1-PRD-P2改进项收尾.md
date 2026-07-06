# 阶段1-PRD-P2改进项收尾.md

## 背景
基于 Orbit_Full_Audit_Report.html P2 改进项（排除测试覆盖类），10 项可快速交付的代码质量/安全/文档修复。

## 用户故事

### P2-1: 安全加固（P1 级别）
**作为** Orbit 运维人员，**我希望** terminal 执行有命令白名单且审计日志不可篡改，**以便** 财税场景下通过安全审计。

验收标准：
- AC1: `/terminal/exec` 端点添加命令白名单（git/python/pytest/npm/pnpm/poetry/ruff/ls/dir/cat/echo）
- AC2: 审计日志写入时附带 SHA256 哈希链（每条含前条哈希）
- AC3: 非白名单命令返回 403 + 审计记录

### P2-2: 孤立模块接线
**作为** Orbit 开发者，**我希望** TestGapDetector 接入管线，**以便** QA 阶段自动检测测试覆盖空洞。

验收标准：
- AC1: TestGapDetector 在 VERIFYING 完成后被调用
- AC2: 检测结果写入 context L2 供 QA Agent 消费
- AC3: fail-open——detector 异常不阻断任务

### P2-3: 代码质量——防御性修复
**作为** Orbit 维护者，**我希望** 运行时异常路径有保护，**以便** 生产环境不因 None 引用崩溃。

验收标准：
- AC1: `_redis_client = None` 后下游 CheckpointManager 做 None 检查
- AC2: HallucinationPipeline 构造时 graph=None 不做 AttributeError
- AC3: build_for_role() 缓存 Prebuilder 实例（首次创建，后续复用）

### P2-4: 代码质量——消除重复
**作为** 前端开发者，**我希望** 类型定义唯一、路由注入统一，**以便** 维护时不需要改多个地方。

验收标准：
- AC1: PeakPromptData 类型三重定义合并为一个源
- AC2: 7 个路由文件的 set_workspace 改用共享 `_workspace.py` 模块

### P2-5: 文档澄清
**作为** 新加入的开发者，**我希望** 模糊注释有明确的意图说明，**以便** 理解哪些是设计意图哪些是未完成。

验收标准：
- AC1: `context/matcher.py` 注释说明何时实现 + 依赖条件
- AC2: `hallucination/l6_contract.py` 注释说明"不报错"是设计意图及理由

## 成功指标
- 安全扫描零新增告警
- 所有现有测试通过
- 代码行变更 < 200 行
- 不引入新依赖

## Non-Goals
- ❌ 前端 fetch() 全量迁移（30+ 处改动范围太大）
- ❌ Prebuilder dict 副作用修复（行为变更需全量回归）
- ❌ DbGraphEngine/ConfigGraphEngine 实际索引（大功能）
- ❌ evolution/communication/core 测试覆盖（另开 PR）
- ❌ CORS/Redis TLS（桌面工具场景可接受）
