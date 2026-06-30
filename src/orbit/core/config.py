"""全局配置：从环境变量读取，禁止硬编码任何密钥/连接串。

WHY 用 python-dotenv 而非 pydantic-settings：开发计划 3.4.1 明确指定
配置管理组件为 python-dotenv，保持技术栈与设计文档一致。
所有字段带默认值（占位符），生产部署时由环境变量注入真实值。
MVP 阶段不强制校验：真实 key 校验留待 Step 2.1（LiteLLM 网关）接入时实现。
"""

import os
import secrets
from dataclasses import dataclass

from dotenv import load_dotenv

# 加载 .env（开发环境），生产用真实环境变量注入
load_dotenv()


def _get(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _get_bool(key: str, default: bool = False) -> bool:
    return _get(key, str(default)).lower() in ("1", "true", "yes")


def _get_int(key: str, default: int = 0) -> int:
    try:
        return int(_get(key, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """全局配置单例（frozen 防止运行时被篡改）。"""

    # 基础
    APP_ENV: str = _get("APP_ENV", "dev")
    DEBUG: bool = _get_bool("DEBUG", True)
    PROJECT_NAME: str = _get("PROJECT_NAME", "Orbit")
    API_V1_STR: str = _get("API_V1_STR", "/api/v1")

    # 数据库（开发默认 SQLite 零依赖启动，生产切 PostgreSQL）
    DATABASE_URL: str = _get("DATABASE_URL", "sqlite+aiosqlite:///./data/graph.db")
    WORKSPACE_DIR: str = _get("WORKSPACE_DIR", "")  # Step 9: 项目根目录

    # Redis（检查点/缓存，Step 2.2 启用）
    REDIS_URL: str = _get("REDIS_URL", "redis://localhost:6379/0")

    # LiteLLM 网关（Step 2.1 启用，MVP 阶段不依赖）
    LITELLM_MASTER_KEY: str = _get("LITELLM_MASTER_KEY", "sk-dummy")
    LITELLM_PROXY_URL: str = _get("LITELLM_PROXY_URL", "http://localhost:4000")

    # 模型 API Keys
    OPENAI_API_KEY: str = _get("OPENAI_API_KEY", "sk-dummy")
    DEEPSEEK_API_KEY: str = _get("DEEPSEEK_API_KEY", "sk-dummy")
    ZAI_API_KEY: str = _get("ZAI_API_KEY", "sk-dummy")

    # 沙箱
    SANDBOX_TIMEOUT_SECONDS: int = _get_int("SANDBOX_TIMEOUT_SECONDS", 30)

    # ---- Step 4.1 防幻觉层 L1-L4 ----
    # WHY 按层独立开关：Dev 仅启用 L1/L4，Test 全量 L1-L4，Prod 仅 L1/L4
    ENABLE_L1: bool = _get_bool("ENABLE_L1", True)
    ENABLE_L2: bool = _get_bool("ENABLE_L2", False)  # 默认关闭（性能开销 ~200ms）
    ENABLE_L3: bool = _get_bool("ENABLE_L3", True)
    ENABLE_L4: bool = _get_bool("ENABLE_L4", True)

    # L3 熵阈值——模型级配置，GLM 0.73）
    # 模型级配置——不同模型 token 分布差异大，统一阈值误报率高
    ENTROPY_THRESHOLD_DEEPSEEK: float = float(_get("ENTROPY_THRESHOLD_DEEPSEEK", "0.75"))
    ENTROPY_THRESHOLD_GLM: float = float(_get("ENTROPY_THRESHOLD_GLM", "0.70"))

    # ---- Step 4.2 防幻觉层 L5-L8 ----
    ENABLE_L5: bool = _get_bool("ENABLE_L5", True)
    Z3_TIMEOUT_MS: int = _get_int("Z3_TIMEOUT_MS", 30000)  # 30s
    ENABLE_L6: bool = _get_bool("ENABLE_L6", True)
    OPENAPI_SPEC_PATH: str = _get("OPENAPI_SPEC_PATH", "/app/openapi.yaml")
    ENABLE_L7: bool = _get_bool("ENABLE_L7", True)
    ENABLE_L8: bool = _get_bool("ENABLE_L8", True)
    CONFIG_BASELINE_DIR: str = _get("CONFIG_BASELINE_DIR", "/app/config_baselines")

    # ---- Step 5.1 调度器 DAG ----
    MAX_CONCURRENT_NODES: int = _get_int("MAX_CONCURRENT_NODES", 3)
    NODE_TIMEOUT_SECONDS: int = _get_int("NODE_TIMEOUT_SECONDS", 30)
    MAX_RETRIES_PER_NODE: int = _get_int("MAX_RETRIES_PER_NODE", 2)
    L8_AUTO_FIX_ENABLED: bool = _get_bool("L8_AUTO_FIX_ENABLED", False)  # prod 默认 false

    # ---- Step 7.2 AgentOps 可观测性 ----
    # WHY 放 core/config 而非 observability/config：
    # core/config 管系统启动参数，AgentOps 管运维阈值。
    # 此处只放影响启动行为的开关，阈值细节在 observability/config.py。
    AGENTOPS_ENABLED: bool = _get_bool("AGENTOPS_ENABLED", True)

    # ---- Step 7.3 ResourceGuard 资源熔断 ----
    RESOURCE_GUARD_ENABLED: bool = _get_bool("RESOURCE_GUARD_ENABLED", True)
    RESOURCE_GUARD_TOKEN_CAPACITY: int = _get_int("RESOURCE_GUARD_TOKEN_CAPACITY", 100000)
    RESOURCE_GUARD_TOKEN_RATE: int = _get_int("RESOURCE_GUARD_TOKEN_RATE", 5000)
    RESOURCE_GUARD_BUDGET_MULTIPLIER: float = float(_get("RESOURCE_GUARD_BUDGET_MULTIPLIER", "1.5"))

    # ---- 安全：认证与 CORS ----
    # WHY 随机默认值：本地桌面工具每次启动生成新 token，防止跨站请求
    ORBIT_AUTH_TOKEN: str = _get("ORBIT_AUTH_TOKEN", secrets.token_urlsafe(32))
    # WHY 显式设置才启用鉴权：未设置环境变量时保持向后兼容（测试/开发）
    AUTH_ENABLED: bool = _get_bool("ORBIT_AUTH_ENABLED", "ORBIT_AUTH_TOKEN" in os.environ)
    # WHY tauri://localhost：Tauri 桌面壳通过自定义协议加载前端
    CORS_ORIGINS: str = _get("CORS_ORIGINS", "http://localhost:*,tauri://localhost")

    # ---- Phase 2: 上下文压缩 + /dream ----
    COMPRESSION_SUMMARY_MODEL: str = _get(
        "COMPRESSION_SUMMARY_MODEL", "openai/glm-4.7-flash"
    )  # WHY 免费模型: 压缩摘要不消耗主力 token
    COMPRESSION_SOFT_THRESHOLD: float = float(_get("COMPRESSION_SOFT_THRESHOLD", "0.50"))
    COMPRESSION_HARD_THRESHOLD: float = float(_get("COMPRESSION_HARD_THRESHOLD", "0.85"))
    DREAM_MODEL: str = _get("DREAM_MODEL", "openai/glm-4.7-flash")
    DREAM_AUTO_TRIGGER_DAYS: int = _get_int("DREAM_AUTO_TRIGGER_DAYS", 7)
    MEMORY_MAX_FILE_SIZE: int = _get_int("MEMORY_MAX_FILE_SIZE", 50_000)


settings = Settings()
