# Orbit 生产镜像（Step 7.1）
# WHY python:3.12-slim：轻量（~150MB），包含必要的 C 扩展编译工具链
FROM python:3.12-slim

WORKDIR /app

# 安装 Poetry
RUN pip install --no-cache-dir "poetry>=2.0"

# 先复制依赖文件（利用 Docker 层缓存——改代码不改依赖时跳过重装）
COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.create false \
    && poetry install --only main --no-interaction \
    && pip uninstall poetry -y  # 生产镜像不需要 poetry

# 复制源代码
COPY src/ ./src/

# Prometheus 指标端口
EXPOSE 18888

# WHY uvicorn 而非 gunicorn：MVP 单 worker + asyncio 已够，
# 多 worker 共享 EventBus（asyncio.Queue）会导致事件丢失。
CMD ["uvicorn", "orbit.api.main:app", "--host", "0.0.0.0", "--port", "18888"]
