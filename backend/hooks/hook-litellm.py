"""PyInstaller hook for litellm——处理命名空间包子包。

WHY: litellm 大量使用无 __init__.py 的命名空间包（如 litellm_core_utils）。
PyInstaller 的 collect_submodules 不支持命名空间包，必须手动 walk 收集。
"""
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files


def _walk_hidden_imports(root_dir: str, package_prefix: str) -> list[str]:
    """递归 walk 目录树，收集所有含 __init__.py 的子包为 hiddenimports。"""
    imports: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        if "__init__.py" in filenames:
            rel = Path(dirpath).relative_to(Path(root_dir).parent)
            pkg = str(rel).replace(os.sep, ".")
            imports.append(pkg)
        if "__pycache__" in dirnames:
            dirnames.remove("__pycache__")
    return imports


_litellm_dir = str(Path(__file__).parent.parent.parent / "litellm")

# 如果上面路径不存在，尝试从已安装的 litellm 获取
if not os.path.isdir(_litellm_dir):
    import litellm as _litellm_pkg

    _litellm_dir = str(Path(_litellm_pkg.__file__).parent)

# 收集所有子包（含命名空间包子包）
hiddenimports = _walk_hidden_imports(_litellm_dir, "litellm")

# 收集数据文件（JSON 等）
datas = collect_data_files("litellm", includes=["**/*.json"])
