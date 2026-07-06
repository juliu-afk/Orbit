# Orbit 生产镜像（Step 7.1）
# WHY python:3.11-slim：与 pyproject.toml 约束一致（>=3.11,<3.14）
FROM python:3.11-slim

WORKDIR /app

# 安装 Poetry
RUN pip install --no-cache-dir "poetry>=2.0"

# 先复制依赖文件（利用 Docker 层缓存——改代码不改依赖时跳过重装）
COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.create false \
    && poetry install --only main --no-root --no-interaction \
    && pip uninstall poetry -y  # 生产镜像不需要 poetry

# 复制源代码 + 安装项目包
COPY src/ ./src/
# P1-2 (PR#131): --no-root 安装依赖后需单独装项目包——
# 否则 uvicorn orbit.api.main:app 找不到 orbit 模块
RUN poetry install --only-root --no-interaction 2>/dev/null || \
    pip install -e . 2>/dev/null || \
    true  # fallback: pyproject 未配置 packages 时由 PYTHONPATH 兜底

# P0-14 (Issue#126): 非 root 用户运行——容器逃逸后限制攻击面
# P1-2 (PR#131): PYTHONPATH 确保 src/ 下 orbit 包可被导入
ENV PYTHONPATH=/app/src
RUN useradd -m -s /bin/bash orbit && chown -R orbit:orbit /app
USER orbit

# Prometheus 指标端口
EXPOSE 18888

# WHY uvicorn 而非 gunicorn：MVP 单 worker + asyncio 已够，
# 多 worker 共享 EventBus（asyncio.Queue）会导致事件丢失。
CMD ["uvicorn", "orbit.api.main:app", "--host", "0.0.0.0", "--port", "18888"]
