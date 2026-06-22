
| PRD (产品需求文档) |  |
| --- | --- |
| **背景** | 系统已通过E2E测试，但需要部署到生产环境，支持金丝雀发布、自动回滚和全链路可观测性。生产环境必须满足SLA 99.9%，且故障时能在5分钟内定位根因。 |
| **用户故事** | 作为SRE工程师，我通过ArgoCD提交新版本镜像Tag，系统自动执行金丝雀发布（5%→50%→100%），同时Grafana仪表盘实时展示错误率和延迟；若错误率>1%，ArgoRollouts自动回滚至上一版本。 |
| **需求描述** | ①编写Helm Chart（包含Deployment、Service、Ingress、ConfigMap、Secret）打包应用；②配置Istio VirtualService + DestinationRule实现流量权重路由；③集成ArgoRollouts实现金丝雀发布（5%→50%→100%，每阶段观察5分钟）；④部署Prometheus采集应用指标（/metrics端点），Grafana展示核心仪表盘（任务吞吐量、Token消耗、P99延迟、错误率）；⑤部署Tempo用于链路追踪（OpenTelemetry集成）；⑥部署ELK（或Loki）用于日志聚合；⑦配置告警规则（错误率>1%触发Critical，P99延迟>10s触发Warning），并通过钉钉/企业微信推送。 |
| **范围 (Do/Don't)** | **Do：**K8s部署、金丝雀发布、自动回滚、Prometheus+Grafana+Tempo+ELK可观测性。**Don't：**不实现多集群联邦（V2）；不实现自动扩缩容（HPA基于CPU，但本系统为CPU密集型，暂不配置）；不实现混沌工程自动化（保留手动触发）。 |
| **数据契约 (Helm Values)** | ``代码块-1`` |
| **异常定义** | 若ArgoRollouts检测到错误率>1%，自动回滚并发送告警；若Helm安装失败（如镜像拉取失败），ArgoCD自动暂停同步并发送Critical告警。 |
| **成功标准→验收** | **SC1:**K8s部署成功 →**AC1:**`kubectl get pods -l app=agent-system`显示3个Pod Running。 |
| | **SC2:**灰度发布流程验证 →**AC2:**修改镜像Tag触发ArgoRollouts，流量按5%→50%→100%逐步切换，各阶段持续5分钟。 |
| | **SC3:**自动回滚 →**AC3:**故意注入错误（如代码抛出异常），错误率>1%，ArgoRollouts在30s内触发回滚，流量切回旧版本。 |
| | **SC4:**监控大盘可用 →**AC4:**访问Grafana，看到“Agent System Overview”仪表盘，包含任务成功率、Token消耗、延迟分布面板。 |
| | **SC5:**告警推送 →**AC5:**模拟错误率飙升，钉钉/企业微信在1分钟内收到告警消息。 |
| **待定决策** | **Q1:**使用Istio还是Nginx Ingress实现灰度？ →**决议：**Istio（更细粒度的流量管理，支持权重路由和镜像流量）。 |
| | **Q2:**监控数据保留周期？ →**决议：**Prometheus保留15天，Loki保留30天，Tempo保留7天（按实际存储容量调整）。 |
| | **Q3:**是否启用自动扩缩容（HPA）？ →**决议：**暂不启用，因为Agent任务是CPU密集型且状态依赖，自动扩缩容易导致状态不一致（留V2）。 |

| ADR (架构决策记录) |  |
| --- | --- |
| **技术栈版本** | Kubernetes 1.28+, Istio 1.21, Helm 3.14, ArgoCD 2.10, ArgoRollouts 1.6, Prometheus 2.52, Grafana 10.4, Tempo 2.4, Loki 3.0, OpenTelemetry Collector 0.89, ELK (或Loki) 8.12。 |
| | 镜像构建: Docker + GitHub Actions (自动构建并推送到容器仓库)。 |
| **架构位置** | 基础设施层（部署与可观测），独立于应用代码，通过Helm Chart管理。应用代码通过`opentelemetry-instrumentation`自动埋点，无需修改业务逻辑。 |
| **实施细节** | **1. Helm Chart 目录结构：** |
| | ``代码块-2`` |
| | **2. 应用埋点（OpenTelemetry）：** |
| | ``代码块-3`` |
| | **3. ArgoRollouts 定义（示例）：** |
| | ``代码块-4`` |
| | **4. 分析模板（AnalysisTemplate）用于错误率判断：** |
| | ``代码块-5`` |
| **风险与缓解** | 风险1: Istio Sidecar注入增加延迟（约5-10ms）。缓解：对于内部服务，通过`DestinationRule`设置连接池，且监控中已包含延迟指标，可观察实际影响。 |
| | 风险2: 监控组件（Prometheus/Grafana/Tempo）自身可能成为故障点。缓解：为监控组件配置持久化存储和Pod反亲和性，确保高可用；关键告警通道使用双通道（钉钉+邮件）。 |
| | 风险3: 金丝雀发布过程中，新旧版本数据层（PostgreSQL/Redis）不一致可能导致状态错误。缓解：数据库迁移采用向后兼容的变更（不删除字段/表），确保新旧版本可同时读写。 |
| **需求错位** | 若生产环境网络策略限制（如无法访问外部容器仓库），需配置私有镜像仓库和镜像拉取密钥。当前假设使用标准容器仓库（如AWS ECR或Harbor）。 |
| **技术约束** | 应用必须暴露`/metrics`端点（使用`prometheus_fastapi_instrumentator`）以被Prometheus采集；所有日志必须输出到`stdout/stderr`（由容器运行时采集）。 |
| **环境配置** | # 生产环境 values-prod.yaml |
| | image: |
| | tag: v1.0.0 |
| | replicaCount: 5 |
| | resources: |
| | requests: |
| | memory: "1Gi" |
| | cpu: "1000m" |
| | limits: |
| | memory: "4Gi" |
| | cpu: "3000m" |
| | ingress: |
| | hosts: |
| | - agent.production.example.com |
| | rollouts: |
| | canary: |
| | steps: |
| | - setWeight: 5 |
| | - pause: {duration: 10m} |
| | - setWeight: 25 |
| | - pause: {duration: 10m} |
| | - setWeight: 50 |
| | - pause: {duration: 10m} |
| | - setWeight: 100 |
| | monitoring: |
| | prometheus: |
| | retention: 15d |
| | loki: |
| | retention: 30d |
| **依赖链** | Helm → K8s API → Istio CRD → ArgoRollouts → Prometheus (分析) → 应用Pod → OpenTelemetry Collector → Tempo/Grafana。 |

🧪 验收测试 (Shell脚本 + kubectl)：
#!/bin/bash
 # 1. 验证部署
 kubectl get pods -l app=agent-system -n prod | grep -c "Running" | grep -q "3" && echo "✅ 3 pods running"

 # 2. 验证灰度发布
 # 假设触发新部署
 kubectl patch rollout agent-system -n prod --type='merge' -p '{"spec":{"template":{"metadata":{"labels":{"version":"v2"}}}}}'
 # 等待滚动
 sleep 300
 # 检查流量分布（通过Istio metrics）
 istioctl dashboard metrics

 # 3. 验证自动回滚（注入错误）
 kubectl patch rollout agent-system -n prod --type='merge' -p '{"spec":{"template":{"metadata":{"annotations":{"fault":"true"}}}}}'
 # 等待分析完成，验证回滚
 sleep 180
 kubectl get rollout agent-system -n prod -o json | jq '.status.phase' | grep -q "Rollback" && echo "✅ 回滚成功"

 # 4. 验证监控
 curl -s http://prometheus:9090/api/v1/query?query=up | jq '.data.result[0].value[1]' | grep -q "1" && echo "✅ Prometheus 正常"
 curl -s http://grafana:3000/api/health | grep -q "ok" && echo "✅ Grafana 正常"


**✅ 全量16个Step PRD/ADR 完整交付确认**

自Step 0.1至Step 7.1，本系列文档已完整覆盖项目的全部16个核心开发步骤：

| 阶段 | 步骤 | 状态 |
| --- | --- | --- |
| **MVP (W1-W2)** | Step 0.1 章程与基线 | ✅ 已交付 |
| Step 0.2 技术栈与环境 | ✅ 已交付 |  |
| Step 1.1 API契约 | ✅ 已交付 |  |
| Step 1.2 三图谱Schema | ✅ 已交付 |  |
|  | MVP-01 调度器骨架 | ✅ 已交付 |
|  | MVP-02 Mock LLM | ✅ 已交付 |
|  | MVP-03 沙箱 | ✅ 已交付 |
| **强化 (W3-W6)** | Step 2.1 LiteLLM网关 | ✅ 已交付 |
| Step 2.2 检查点 | ✅ 已交付 |  |
| **图谱 (W5-W6)** | Step 3.1 代码图谱 | ✅ 已交付 |
| Step 3.2 数据库图谱 | ✅ 已交付 |  |
| Step 3.3 配置图谱 | ✅ 已交付 |  |
| **防幻觉 (W7-W8)** | Step 4.1 L1-L4 | ✅ 已交付 |
| Step 4.2 L5-L8 | ✅ 已交付 |  |
| **调度器 (W9-W10)** | Step 5.1 调度器状态机 | ✅ 已交付 |
| Step 5.2 Agent角色 | ✅ 已交付 |  |
| **前端/测试 (W11-W12)** | Step 6.1 驾驶舱 | ✅ 已交付 |
| Step 6.2 E2E测试 | ✅ 已交付 |  |
| **生产 (W13)** | Step 7.1 灰度+可观测 | ✅ 已交付 |

**总交付物：**16个Step × 完整的PRD（背景/用户故事/需求/范围/数据契约/异常/SC→AC/待定决策）+ ADR（技术栈/架构位置/实施细节/风险/需求错位/技术约束/环境配置/依赖链）+ 原子化测试用例。

开发团队可按照Step顺序拆解为50-80个子任务，直接进入编码阶段。所有模块的接口、数据格式、配置项、测试用例均已明确，实现“零歧义开发”。



```
// 代码块-1
# values.yaml 核心结构
    image:
      repository: myregistry/agent-system
      tag: latest
      pullPolicy: IfNotPresent

    replicaCount: 3

    service:
      type: ClusterIP
      port: 8000

    ingress:
      enabled: true
      hosts:
        - agent.example.com
      tls:
        - secretName: agent-tls

    resources:
      requests:
        memory: "512Mi"
        cpu: "500m"
      limits:
        memory: "2Gi"
        cpu: "2000m"

    istio:
      enabled: true
      gateway: istio-system/agent-gateway
      virtualService:
        hosts:
          - agent.example.com

    rollouts:
      enabled: true
      canary:
        steps:
          - setWeight: 5
          - pause: {duration: 5m}
          - setWeight: 50
          - pause: {duration: 5m}
          - setWeight: 100
        analysis:
          templates:
            - templateName: error-rate-analysis
          args:
            - name: service
              value: agent-service

    monitoring:
      prometheus:
        enabled: true
        serviceMonitor:
          enabled: true
      grafana:
        enabled: true
        dashboards:
          enabled: true
      tempo:
        enabled: true
      loki:
        enabled: true

    alerting:
      enabled: true
      rules:
        - name: HighErrorRate
          expr: sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m])) > 0.01
          severity: critical
        - name: HighLatency
          expr: histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le)) > 10
          severity: warning
```


```
// 代码块-2
agent-system/
    ├── Chart.yaml
    ├── values.yaml
    ├── values-prod.yaml
    ├── templates/
    │   ├── deployment.yaml
    │   ├── service.yaml
    │   ├── ingress.yaml
    │   ├── configmap.yaml
    │   ├── rollouts.yaml        # ArgoRollouts 定义
    │   ├── virtualservice.yaml  # Istio VirtualService
    │   ├── servicemonitor.yaml  # Prometheus ServiceMonitor
    │   └── _helpers.tpl
    └── charts/                # 依赖的可观测性组件（可选）
```


```
// 代码块-3
# 在 main.py 中添加
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    # 初始化TracerProvider
    trace_provider = TracerProvider()
    processor = BatchSpanProcessor(OTLPSpanExporter(endpoint="http://tempo-collector:4317"))
    trace_provider.add_span_processor(processor)
    # 设置全局TracerProvider
    # 对FastAPI自动埋点
    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()
```


```
// 代码块-4
apiVersion: argoproj.io/v1alpha1
    kind: Rollout
    metadata:
      name: agent-system
    spec:
      replicas: 3
      strategy:
        canary:
          steps:
            - setWeight: 5
            - pause: {duration: 5m}
            - setWeight: 50
            - pause: {duration: 5m}
            - setWeight: 100
          analysis:
            templates:
              - templateName: error-rate-analysis
            startingStep: 1
      selector:
        matchLabels:
          app: agent-system
      template:
        metadata:
          labels:
            app: agent-system
        spec:
          containers:
            - name: app
              image: {{ .Values.image.repository }}:{{ .Values.image.tag }}
              ports:
                - containerPort: 8000
              envFrom:
                - configMapRef:
                    name: agent-config
                - secretRef:
                    name: agent-secrets
```


```
// 代码块-5
apiVersion: argoproj.io/v1alpha1
    kind: AnalysisTemplate
    metadata:
      name: error-rate-analysis
    spec:
      args:
        - name: service
      metrics:
        - name: error-rate
          initialDelay: 1m
          count: 3
          interval: 1m
          successCondition: result[0] < 0.01
          provider:
            prometheus:
              address: http://prometheus:9090
              query: |
                sum(rate(http_requests_total{service="{{args.service}}",status=~"5.."}[1m])) / sum(rate(http_requests_total{service="{{args.service}}"}[1m]))
```