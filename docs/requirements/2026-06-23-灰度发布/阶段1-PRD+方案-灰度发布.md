# Step 7.1 灰度发布 — PRD+技术方案（MVP 版）

> 基线：`docs/PRD+ADR_7阶段.md`。MVP 版聚焦容器化+基础 K8s，Istio/ArgoRollouts/Grafana/Tempo 延后。

## 1. 背景

Orbit 系统已通过全部测试（204 pytest），需要生产部署方案。原 PRD+ADR 覆盖完整的 K8s+Istio+ArgoCD+可观测性栈，但 MVP 阶段仅需核心交付物。

## 2. MVP 范围

| 交付物 | MVP | V2 |
|--------|-----|-----|
| Docker 镜像 | ✅ Dockerfile + build | 多阶段构建优化 |
| K8s 部署 | ✅ Helm Chart（Deployment+Service+Ingress） | Istio VirtualService |
| 灰度发布 | ✅ `kubectl rollout` 原生滚动更新 | ArgoRollouts 金丝雀 5%→50%→100% |
| 监控 | ✅ Prometheus `/metrics` 端点 | Grafana 仪表盘 |
| 日志 | ✅ stdout/stderr（容器运行时采集） | Loki/ELK |
| 链路追踪 | ❌ | OpenTelemetry + Tempo |
| 告警 | ❌ | AlertManager + 钉钉 |
| CI/CD | ✅ GitHub Actions 构建+推送镜像 | ArgoCD GitOps |

## 3. 用户故事

| # | 作为 | 我希望 | P |
|---|---|---|---|
| US1 | SRE | `docker pull orbit:latest` 然后 `docker run` 直接跑起来 | P0 |
| US2 | SRE | `helm install orbit ./chart` 部署到 K8s | P0 |
| US3 | 运维 | Prometheus 自动发现 `/metrics` 并采集 | P1 |
| US4 | 开发者 | PR 合并后 CI 自动构建镜像推送到仓库 | P1 |

## 4. 交付物

### 4.1 Dockerfile

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml poetry.lock ./
RUN pip install poetry && poetry config virtualenvs.create false && poetry install --no-dev
COPY src/ ./src/
EXPOSE 18888
CMD ["uvicorn", "orbit.api.main:app", "--host", "0.0.0.0", "--port", "18888"]
```

### 4.2 Helm Chart

```
chart/orbit/
├── Chart.yaml
├── values.yaml
├── templates/
│   ├── deployment.yaml
│   ├── service.yaml
│   └── ingress.yaml
```

### 4.3 Prometheus 指标

FastAPI 加 `prometheus_fastapi_instrumentator` → 自动暴露 `/metrics`。

### 4.4 CI

`.github/workflows/docker-build.yml`：build → push → docker-compose smoke test。

## 5. 验收标准

| # | 标准 |
|---|---|
| AC1 | `docker build -t orbit . && docker run -p 18888:18888 orbit` → `/health` 返回 200 |
| AC2 | `helm template chart/orbit/ --debug` 无错误 |
| AC3 | `curl /metrics` 返回 Prometheus 格式指标 |
| AC4 | CI `docker-build` job 通过 |

## 6. 影响范围

```
Dockerfile
chart/orbit/
  Chart.yaml, values.yaml
  templates/deployment.yaml, service.yaml, ingress.yaml
.github/workflows/docker-build.yml
src/orbit/api/main.py  # + prometheus_fastapi_instrumentator
```

依赖：`prometheus_fastapi_instrumentator`（生产依赖，1 个包）。

## 7. Non-Goals

- Istio + ArgoRollouts 金丝雀发布
- Grafana/Tempo/Loki/ELK
- AlertManager 告警
- 多集群联邦
- HPA 自动扩缩容

---

> PRD+方案合并完成。确认后直接进阶段3编码。
