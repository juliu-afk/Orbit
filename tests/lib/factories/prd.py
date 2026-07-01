"""PRD 工厂——创建测试用结构化 PRD 文本。

生成中文 PRD 文本，用于测试需求澄清和任务创建的输入。
"""

from __future__ import annotations

DEFAULT_PRD = """## 需求：实现用户登录功能

### 背景
当前系统缺少用户认证，需要实现基于 JWT 的登录功能。

### 验收标准
1. 用户可用用户名+密码登录
2. 登录成功后返回 access_token（有效期 24h）和 refresh_token（有效期 7d）
3. 密码错误 5 次后账号锁定 30 分钟
4. Token 过期后返回 401

### 约束
- 密码必须 bcrypt 哈希
- Token 用 HS256 签名
- 不依赖第三方认证服务
"""

SHORT_PRD = "实现用户登录 API——POST /auth/login 端点，返回 JWT token。"

COMPLEX_PRD = """## 需求：实现多租户 RBAC 权限系统

### 背景
系统需要支持多租户隔离 + 基于角色的权限控制（RBAC）。
每个租户有独立的用户、角色、权限集合。

### 验收标准
1. 租户 CRUD——创建/查询/更新/删除租户，删除为软删除
2. 角色管理——每个租户可定义自定义角色（admin/editor/viewer 为默认角色）
3. 权限分配——权限为 {resource}:{action} 格式（如 "voucher:create"、"report:export"）
4. 用户-角色关联——用户可属于多个角色，权限取并集
5. 租户隔离——用户只能访问所属租户的数据
6. API 中间件——从 JWT 提取 tenant_id，注入请求上下文
7. 权限缓存——Redis 缓存用户权限（TTL 5 分钟），Role 变更时主动失效
8. 审计日志——所有权限变更记录审计日志

### 约束
- 权限字符串格式：{resource}:{action}，resource 为小写下划线，action 为 CRUD 标准动词
- 禁止跨租户数据访问
- 超级管理员（system_admin）可跨租户查看，但不可修改
"""


def create_prd(
    complexity: str = "normal",
    **kwargs: str,
) -> str:
    """创建结构化 PRD 文本。

    Args:
        complexity: 复杂度级别
            - "short": 简短需求（一行）
            - "normal": 标准需求（含背景/验收标准/约束）
            - "complex": 复杂需求（多模块交叉）

    Returns:
        Markdown 格式 PRD 文本
    """
    prd_map = {
        "short": SHORT_PRD,
        "normal": DEFAULT_PRD,
        "complex": COMPLEX_PRD,
    }
    return prd_map.get(complexity, DEFAULT_PRD)
