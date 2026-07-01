"""Orbit 全链路测试库。

模拟真实用户操作，覆盖所有场景，全链路、点到点。

子模块:
    factories/  — 模型工厂，一行创建有效测试实例
    mocks/      — 可配置 Mock，注入失败/延迟/特定输出
    builders/   — 业务流构建器，链式构建完整链路
    scenarios/  — 预定义场景，真实用户操作序列
    assertions/ — Orbit 专用断言
"""
