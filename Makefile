.PHONY: init up down install test test-unit test-integration test-e2e test-smoke lint format typecheck clean

# 一键拉起：启动容器 + 安装依赖（Step 0.2 SC1：5分钟内可用）
init: up install

# 启动基础设施容器（PostgreSQL / Redis / LiteLLM）
up:
	docker compose up -d
	@echo "等待服务健康..."
	@sleep 5
	docker compose ps

# 停止容器
down:
	docker compose down

# 安装依赖（Poetry）
install:
	poetry install

# 运行全部测试
test:
	poetry run pytest tests/ -q --cov=src/orbit --cov-report=term

# 分层测试（开发计划 3.4.1）
test-unit:
	poetry run pytest tests/unit/ -q

test-integration:
	poetry run pytest tests/integration/ -q

test-smoke:
	poetry run pytest tests/e2e/ -q -k "smoke"

test-e2e:
	@echo ">>> 启动 E2E 基础设施..."
	docker compose -f docker-compose.test.yml up -d --wait 2>/dev/null || echo "Docker 不可用——降级到 ProcessSandbox"
	-poetry run pytest tests/e2e/ -v -m e2e --tb=long --timeout=120; \
	EXIT=$$?; \
	docker compose -f docker-compose.test.yml down -v 2>/dev/null || true; \
	exit $$EXIT

# 代码检查（与 CI + pre-commit 一致：ruff + mypy）
lint:
	poetry run ruff check src/ tests/
	poetry run ruff format --check src/ tests/
	poetry run mypy src/

format:
	poetry run ruff check --fix src/ tests/
	poetry run ruff format src/ tests/

typecheck:
	poetry run mypy src/

# 启动开发服务器
dev:
	poetry run uvicorn orbit.api.main:app --reload --host 0.0.0.0 --port 8000

# 清理
clean:
	rm -rf .pytest_cache .coverage htmlcov .mutmut-cache dist build *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +