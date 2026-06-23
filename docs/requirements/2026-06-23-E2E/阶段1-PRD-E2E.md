# 阶段1 PRD — Step 6.2 E2E 集成测试

> 基线：`docs/PRD+ADR_6阶段.md` Step 6.2（PRD+ADR 已定稿）。
> 增量：边缘情况、测试数据契约、Mock 策略、环境隔离矩阵。

## 1. 背景与现状

Orbit 系统已集成 5 个模块（调度器/LLM网关/三图谱/8层防幻觉/驾驶舱），但无端到端测试覆盖。当前测试基础设施：

| 项 | 现状 |
|---|---|
| 单元测试 | 192 用例，覆盖所有模块 |
| 集成测试 | 4 用例（`test_health_api.py`） |
| E2E 测试 | 零 |
| 性能测试 | 零 |
| Docker Compose | 存在（PG+Redis+LiteLLM），无 test override |
| 数据库 | SQLite（生产 PG，MVP SQLite） |
| Windows 环境 | Docker Desktop 不一定可用 |

**核心问题**：不知道各模块协同是否能跑通完整链路。一个调度器 bug 可能在单元测试通过的情况下导致端到端流程断裂。

## 2. 用户故事

| # | 作为 | 我希望 | 以便 | P |
|---|---|---|---|---|
| US1 | QA 工程师 | 运行 `make e2e-test` 执行完整任务生命周期测试 | 每次 PR 自动验证核心链路不断 | P0 |
| US2 | 开发者 | 本地跑 E2E 不需要 Docker | 快速迭代不依赖容器 | P0 |
| US3 | QA 工程师 | Mock LLM 返回可预测的响应 | E2E 结果稳定可重复，不受外部 API 波动影响 | P0 |
| US4 | 运维 | E2E 失败时看到清晰的错误报告 | 3 分钟内定位哪个模块断了 | P1 |
| US5 | 技术负责人 | 性能基准测试报告 P95 延迟 | 知道系统在什么并发量下会退化 | P1 |

## 3. 功能需求

### 3.1 E2E 场景

| 场景 | 名称 | 流程 | 验证点 |
|------|------|------|--------|
| S1 | **正常流程** | POST /tasks → 创建任务 → 调度器执行 IDLE→PARSING→...→DONE | 状态流转正确、最终 DONE |
| S2 | **重试修复** | 创建任务 → Mock LLM 前 2 次失败 → 第 3 次成功 | 重试计数递增、最终 SUCCESS |
| S3 | **熔断降级** | 创建任务 → Mock LLM 持续 5xx → 熔断器触发 | 熔断器 opened、任务 FAILED、降级日志 |
| S4 | **WebSocket 推送** | 创建任务 → 连接 WS `/ws/dashboard` → 订阅 → 接收状态推送 | WS 消息类型正确、task:update 有 dag |
| S5 | **防幻觉告警** | 创建任务 → Mock LLM 返回高熵输出 → L3 触发告警 | alert:new 推送到 WS、severity=warning |

### 3.2 Mock LLM 策略

PRD+ADR Q1 决议：**默认 Mock LLM，每周一次真实 LLM 夜间构建**。

Mock 设计：
- `MockLLMClient` 实现 `LLMClient` 接口（或继承）
- 可配置：`response_content`（固定返回）、`fail_count`（前 N 次抛异常）、`entropy`（控制 L3 触发）
- 环境变量 `ORBIT_MOCK_LLM=true` 启用，`false` 走真实 LiteLLM

### 3.3 性能基准

| 指标 | CI 阈值 | 预发布阈值 |
|------|---------|-----------|
| 单任务 P50 延迟 | <3s | <1.5s |
| 单任务 P95 延迟 | <12s | <8s |
| 并发 3 任务 P95 | <20s | <15s |
| Token/任务 | —（暂不阻塞） | — |

性能测试用 `pytest-benchmark` 或简单 `time.perf_counter`，不引入 locust（MVP 阶段过度）。

### 3.4 Allure 报告

- `pytest --alluredir=reports/allure` 生成
- CI artifact 上传（GitHub Actions `actions/upload-artifact`）
- 不强制作为门禁，作为辅助排障工具

## 5. 边缘情况

| 场景 | 测试行为 | 断言 |
|------|---------|------|
| **Docker 不可用** | 测试标记 skip，不报 FAIL | `pytest.skip("Docker unavailable")` |
| **Docker 沙箱超时** | 代码执行超过 node_timeout | 节点 FAILED，error="Timeout" |
| **Docker 镜像缺失** | 沙箱引用的镜像不存在 | 明确报错 "image not found"，非 500 |
| **沙箱代码逃逸尝试** | 执行 `os.system("rm -rf /")` | 沙箱内执行，宿主机不受影响（安全验证） |
| **任务创建后立即查询状态** | GET /tasks/{id} | state=IDLE, progress=0.0 |
| **并发创建 3 任务** | 同时 POST 3 任务 | 3 个均 200，task_id 互不相同 |
| **取消执行中的任务** | POST /tasks/{id}/cancel | 状态→CANCELLED |
| **WS 断线重连** | 杀 WS 连接 → 重连 → 恢复订阅 | 收到后续事件 |
| **数据库连接断开** | 杀 PG 容器 → 恢复 | 任务可恢复（检查点机制） |
| **空 PRD / 超长 PRD** | POST with invalid prd | 422 校验失败 |
| **端口冲突** | 5433/6380 已被占用 | docker-compose 报错，E2E 不静默换端口 |

## 4. 环境隔离

**核心原则：E2E 测试必须走真实 Docker 基础设施。** Orbit 的沙箱模块（`src/orbit/sandbox/executor.py`）依赖 Docker Engine 执行代码隔离，跳过 Docker = 跳过核心安全机制。

| 层 | 策略 |
|---|---|
| **数据库** | PostgreSQL（docker-compose.test.yml 专用容器），端口 5433（避免冲突） |
| **Redis** | Redis（docker-compose.test.yml 专用容器），端口 6380 |
| **沙箱** | 真实 Docker Engine，`docker run` 代码片段隔离执行 |
| **LLM** | Mock LLM（零 API 成本，确定性输出），夜间构建用真实 LLM |
| **FastAPI** | 同进程 TestClient（`httpx.AsyncClient`），不单独容器化 |
| **Docker 不可用时** | `@pytest.mark.skipif(no_docker(), reason="Docker unavailable")` |
| **数据清理** | `docker compose down -v` 销毁 test 容器+卷，零残留 |

### docker-compose.test.yml

```yaml
# E2E 专用——独立于开发环境的容器
services:
  postgres-test:
    image: postgres:15
    ports: ["5433:5432"]
    environment:
      POSTGRES_USER: test
      POSTGRES_PASSWORD: test
      POSTGRES_DB: orbit_test
    tmpfs: /var/lib/postgresql/data  # 内存存储，加速 + 自动清理

  redis-test:
    image: redis:7.2
    ports: ["6380:6379"]
```

## 6. 数据契约

### 6.1 E2E 测试 fixture

```python
@pytest.fixture(scope="session")
def docker_available() -> bool:
    """检测 Docker 是否可用。不可用时 skip 所有 E2E。"""
    import subprocess
    try:
        subprocess.run(["docker", "info"], capture_output=True, timeout=5, check=True)
        return True
    except Exception:
        return False

@pytest.fixture(scope="session")
async def e2e_env(docker_available):
    """启动 docker-compose.test.yml → 创建 app + scheduler + 所有真实组件。"""
    if not docker_available:
        pytest.skip("Docker unavailable")
    # docker compose -f docker-compose.test.yml up -d --wait
    subprocess.run(["docker", "compose", "-f", "docker-compose.test.yml", "up", "-d", "--wait"], check=True)
    # 启动真实 PG checkpointer + Redis + MockLLM + Sandbox(real Docker)
    bus = EventBus()
    llm = MockLLMClient()
    cp = PostgresCheckpointManager(url="postgresql://test:test@localhost:5433/orbit_test")
    sandbox = DockerSandbox()  # 真实 Docker Engine
    scheduler = Scheduler(llm_client=llm, checkpoint_manager=cp, event_bus=bus, sandbox=sandbox)
    app = create_app(event_bus=bus)
    app.state.scheduler = scheduler
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        yield client
    # teardown
    subprocess.run(["docker", "compose", "-f", "docker-compose.test.yml", "down", "-v"], check=True)
```

### 6.2 测试断言模板

```python
# 所有 E2E 断言遵循：创建→等待→验证
async def test_e2e_normal_flow(e2e_client):
    # 1. 创建任务
    resp = await e2e_client.post("/api/v1/tasks", json={"prd": "写一个排序函数"})
    assert resp.status_code == 200
    task_id = resp.json()["task_id"]

    # 2. 轮询直到终态
    for _ in range(30):  # 最多 30s
        r = await e2e_client.get(f"/api/v1/tasks/{task_id}")
        state = r.json()["state"]
        if state in ("DONE", "FAILED", "CANCELLED"):
            break
        await asyncio.sleep(1)

    # 3. 验证终态
    assert state == "DONE"
```

## 7. 验收标准

| # | 标准 | 验证方式 |
|---|---|---|
| AC1 | `pytest -m e2e` 3 场景全通过 | CI 运行 |
| AC2 | 正常流程 30s 内到达 DONE | 轮询超时断言 |
| AC3 | 熔断场景中熔断器 opened | `circuit_breaker.state == "OPEN"` |
| AC4 | WS 推送包含正确 `type` 字段 | `task:update` / `token:update` / `alert:new` |
| AC5 | 所有 E2E 测试使用 Mock LLM，零外部 API 调用 | 代码审查确认 |
| AC6 | E2E 测试可用 `make e2e-test` 一键运行 | Makefile 验证 |
| AC7 | 测试结束后无残留数据 | teardown 清理 SQLite 文件 |

## 8. 沙箱隔离兜底方案

**不接受 E2E 因 Docker 不可用而 skip。** 必须有降级路径。

### 双层沙箱策略

| 层级 | 条件 | 引擎 | 隔离强度 |
|------|------|------|---------|
| **L1 主方案** | Docker Engine 可用 | `DockerSandbox`（`docker run`） | 强——容器级隔离 |
| **L2 兜底** | Docker 不可用 | `ProcessSandbox`（`subprocess`） | 中——进程级隔离 |

### ProcessSandbox（L2 兜底）—— Windows 原生三层防御

当 Docker 不可用时，自动降级到 Windows 原生隔离。不用虚拟机、不加 Docker、不加第三方驱动。

#### 三层防御（纵深）

| 层 | 机制 | 作用 | 实现 |
|---|---|---|---|
| **L2a 文件/注册表/网络隔离** | AppContainer | 内核级 capability 沙箱——限制文件系统访问、注册表读写、网络出站 | Win32 `CreateAppContainerProfile` + `SetTokenInformation` |
| **L2b 进程资源管控** | Job Object | 父进程退出时杀所有子进程 + 内存上限 | `CreateJobObject` + `SetInformationJobObject` |
| **L2c 写保护** | Low Integrity Level | 禁止写入 Medium+ IL 对象（防篡改系统文件） | `SetTokenInformation(TOKEN_MANDATORY_LABEL)` |

> 三层叠加 → 近似 Docker 容器级隔离，但零虚拟化开销。
> Chromium/Edge 用同样机制做渲染器沙箱。

#### Windows 实现伪代码

```python
# src/orbit/sandbox/process_sandbox.py
def execute_in_appcontainer(code: str, timeout: int, caps: SandboxCapabilities):
    """Windows 原生沙箱执行。

    1. CreateAppContainerProfile("OrbitSandbox")
    2. DeriveAppContainerSid → 生成 capability SID
    3. SetNamedSecurityInfo(temp_dir, ..., appcontainer_sid) → 授权工作目录
    4. CreateProcess(
         lpApplicationName="python",
         lpCommandLine=f"-c {code}",
         lpProcessAttributes=PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES,
         ...
       )
    5. AssignProcessToJobObject(job, process) → 资源限制
    6. WaitForSingleObject(process, timeout) → 超时 TerminateProcess
    """
```

#### Unix 降级

Linux/macOS：`subprocess` + `preexec_fn` 设置 `rlimit` + `unshare`（CLONE_NEWNET 禁网络）。

```python
def _unix_sandbox(code, timeout, temp_dir):
    subprocess.run(
        ["python", "-c", code],
        timeout=timeout,
        cwd=temp_dir,
        env={"PATH": "/usr/bin", "HOME": temp_dir},
        preexec_fn=_drop_privileges,  # rlimit + unshare
        capture_output=True,
    )
```

#### 与 DockerSandbox 的差异

| 维度 | DockerSandbox (L1) | ProcessSandbox (L2) |
|------|-------------------|---------------------|
| 隔离层 | 容器（namespace + cgroup） | AppContainer + Job + LowIL |
| 网络隔离 | 独立 network namespace | AppContainer 网络 capability 禁用 |
| 文件系统 | 独立 overlayfs | 临时目录 + AppContainer ACL |
| 资源限额 | cgroup (CPU/内存) | Job Object（内存上限 + 进程数） |
| 镜像 | Docker image（可固化的 Python 版本） | 宿主编译 Python |
| 启动耗时 | ~200-500ms | <10ms（纯进程创建） |
| 安全强度 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |

#### E2E 行为

- Docker 可用 → L1 DockerSandbox，日志 `sandbox=Docker`
- Docker 不可用 + Windows → L2a+b+c AppContainer+Job+LowIL
- Docker 不可用 + Unix → L2 rlimit+unshare
- **全部不可用 → 系统拒绝启动**，错误信息：`"无可用沙箱隔离机制。请安装 Docker 或启用 Windows AppContainer。系统无法在不安全环境运行。"`

> 硬停止规则：Orbit 设计前提是代码执行必须有隔离。连降级方案都失败意味着无法保证宿主编安全——此时唯一正确行为是拒绝启动，而不是静默裸奔。

### 场景矩阵

| 场景 | Docker 可用 | Docker 不可用 |
|------|-----------|-------------|
| S1 正常流程 | DockerSandbox | ProcessSandbox |
| S2 重试修复 | DockerSandbox | ProcessSandbox |
| S3 熔断降级 | DockerSandbox | ProcessSandbox |
| S4 WS 推送 | —（不涉及沙箱） | — |
| S5 防幻觉告警 | —（不涉及沙箱） | — |
| 沙箱逃逸测试 | DockerSandbox 必须 | **跳过**（ProcessSandbox 无法保证逃逸防护） |

## 9. Non-Goals

- Locust 分布式压测（MVP 用简单并发测试替代）
- Cypress/Playwright UI 测试（Step 6.1 范围）
- 安全渗透测试
- 真实 LLM 夜间构建（基础设施待配）
- 多操作系统沙箱测试（仅 Linux 容器，Windows 容器不在 MVP）

## 10. 待确认

| # | 问题 | 决议 |
|---|---|---|
| Q1 | Docker Compose 用于 E2E | **是**。docker-compose.test.yml（PG+Redis） |
| Q2 | Mock LLM 位置 | `tests/e2e/mock_llm.py`，不进 src |
| Q3 | Docker 不可用时行为 | **自动降级到 ProcessSandbox**，不 skip |
| Q4 | CI 新增 GitHub Actions job | 是——`e2e-test` job，依赖 `unit-test` |
| Q5 | 端口分配 | PG=5433, Redis=6380 |
| Q6 | ProcessSandbox 放 src 还是 tests？ | `src/orbit/sandbox/process_sandbox.py`——与 DockerSandbox 同级，生产也可用 |
| Q7 | Windows AppContainer API 太复杂？ | 用 `pywin32` 封装（`win32security`/`win32job`）。Chromium/Edge 验证了此方案可行性 |
| Q8 | Unix 降级方案 | rlimit + unshare(CLONE_NEWNET)，零新依赖 |
| Q9 | 沙箱逃逸测试 | 仅 L1（Docker）执行——L2 无法保证逃逸防护 |
