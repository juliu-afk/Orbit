"""代码模板库——业务层减熵 P1.

提供 TemplateRegistry 全局单例 get_registry() 供 AgentFactory 使用.
"""

from orbit.knowledge.templates.registry import TemplateRegistry, get_registry

__all__ = ["TemplateRegistry", "get_registry"]
