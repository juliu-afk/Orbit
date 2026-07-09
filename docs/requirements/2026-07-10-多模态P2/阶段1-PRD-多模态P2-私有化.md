# 阶段1-PRD-多模态P2-私有化

> 基线：P0 Gateway + P1 Tools · 2026-07-10
> 阶段：P2 — MiniCPM-V 4.6 私有化部署 + 隐私路由

---

## 1. 背景

P0/P1 的多模态调用全部走云端 API（智谱 GLM-4.1V/4.6V）。某些场景需要数据不出域：财务截图、内部文档、敏感 UI 界面。P2 部署本地 MiniCPM-V 4.6 作为私有化备选。

MiniCPM-V 4.6：1.3B 参数、Apache 2.0、仅需 6GB VRAM、Docker vLLM 一行命令启动。

## 2. 用户故事

| 优先级 | 故事 | 价值 |
|--------|------|------|
| **P0** | Agent 处理敏感截图时自动路由到本地模型 | 数据不出域 |
| **P1** | Docker Compose 一键启动本地视觉 LLM | 零配置部署 |
| **P2** | 本地模型不可用时自动降级到云端（需确认） | 可用性兜底 |

## 3. 验收标准

| # | 标准 | 验证 |
|---|------|------|
| **SC1** | `docker compose -f sandbox/docker-compose.vlm.yml up -d` 启动 MiniCPM-V vLLM 服务 | `curl localhost:8000/health` → 200 |
| **SC2** | TierRouter 新增 `Tier.PRIVATE`——路由到 `localhost:8000` 的 MiniCPM-V | 发截图 → 本地模型返回分析 |
| **SC3** | 隐私敏感数据（关键词：财务/内部/密钥/密码）自动走 PRIVATE tier | 集成测试 |

## 4. 范围

- ✅ Docker Compose 一键部署 MiniCPM-V 4.6
- ✅ TierRouter 加 PRIVATE 梯度
- ❌ 不训练/微调模型（直接用开源权重）
- ❌ 不优化推理速度（vLLM 默认配置）
- ❌ GPU 不可用时不做 CPU fallback（需 6GB VRAM）

## 5. 依赖

| 依赖 | 用途 | 新增 |
|------|------|------|
| Docker + nvidia-container-toolkit | vLLM 容器 | ⚠️ GPU 环境 |
| MiniCPM-V 4.6 权重 | HF 自动下载 | 首次 ~3GB |
| vLLM | 推理引擎 | 容器内置 |
