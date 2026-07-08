"""抽象解释 (V14.2+Theory 方向22).

Galois连接——防幻觉管道层级的可靠上近似:
  L1处理符号存在性→L4处理类型一致性→L7处理运行时行为
  每层抽象域是上层精化——L1失败→L4/L7的抽象语义无意义.

用法:
    analyzer = AbstractPipelineAnalyzer()
    deps = analyzer.analyze_dependencies(["L1","L4","L7"])
    print(deps)  # → {"L1": {"affects":["L4","L7"]}, ...}
"""
from __future__ import annotations

# 防幻觉层级抽象域定义
_ABSTRACT_DOMAINS = {
    "L1": {"name": "SymbolExistence", "precision": "coarse"},
    "L4": {"name": "TypeConsistency", "precision": "medium", "depends_on": ["L1"]},
    "L7": {"name": "RuntimeBehavior", "precision": "fine", "depends_on": ["L1", "L4"]},
    "L2": {"name": "DynamicTrace", "precision": "medium", "depends_on": ["L7"]},
    "L3": {"name": "EntropyMonitor", "precision": "medium"},
    "L5": {"name": "Z3Formal", "precision": "fine", "depends_on": ["L4"]},
    "L6": {"name": "ContractVerify", "precision": "medium", "depends_on": ["L4"]},
    "L8": {"name": "ConfigDrift", "precision": "coarse"},
}


class AbstractPipelineAnalyzer:
    """防幻觉管道抽象解释器——可靠上近似分析."""

    @staticmethod
    def analyze_dependencies(layers: list[str] | None = None) -> dict:
        """分析层级依赖——哪些层失败会必然影响后续层.

        Returns: {layer: {affects:[...], depends:[...], reliable:bool}}
        """
        if layers is None:
            layers = list(_ABSTRACT_DOMAINS.keys())
        result = {}
        for name in layers:
            info = _ABSTRACT_DOMAINS.get(name, {})
            # 所有依赖此层的下游层
            affects = [l for l, d in _ABSTRACT_DOMAINS.items()
                       if name in d.get("depends_on", [])]
            result[name] = {
                "affects": affects,
                "depends": info.get("depends_on", []),
                "reliable": len(affects) == 0,  # 无下游依赖→可独立判定
            }
        return result

    @staticmethod
    def skip_recommendation(failed_layer: str, active_layers: list[str]) -> list[str]:
        """给定某层失败→建议跳过哪些层（可靠上近似）.

        返回: 必定受影响的层列表（可靠——不漏报假阴性）
        """
        deps = AbstractPipelineAnalyzer.analyze_dependencies(active_layers)
        info = deps.get(failed_layer, {})
        affected = set(info.get("affects", []))
        # 传递闭包: A→B, B→C → A→C
        changed = True
        while changed:
            changed = False
            for layer in list(affected):
                if layer in deps:
                    for a in deps[layer].get("affects", []):
                        if a not in affected and a != failed_layer:
                            affected.add(a)
                            changed = True
        return sorted(affected)
