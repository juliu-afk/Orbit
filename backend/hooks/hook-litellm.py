"""PyInstaller hook for litellm — collect ALL submodules AND data files.

WHY: litellm has 1727+ .py modules AND many .json data files (tokenizers, etc.)
that PyInstaller cannot discover. We filesystem-scan everything.
"""

import os
from pathlib import Path

import litellm
from PyInstaller.utils.hooks import collect_data_files

_litellm_dir = Path(litellm.__file__).parent
_pkg_root = _litellm_dir.parent  # site-packages/

# 1. Collect all .py submodules
hiddenimports = []
for root, dirs, files in os.walk(_litellm_dir):
    for f in files:
        if f.endswith(".py"):
            fp = Path(root) / f
            rel = fp.relative_to(_pkg_root).with_suffix("")
            mod = ".".join(rel.parts)
            if mod.endswith(".__init__"):
                mod = mod[:-9]
            hiddenimports.append(mod)

# 2. Collect all .json data files (tokenizer configs, model prices, etc.)
#    PyInstaller datas format: [(src, dest_dir), ...]
datas = []
for root, dirs, files in os.walk(_litellm_dir):
    for f in files:
        if f.endswith(".json"):
            src = str(Path(root) / f)
            rel_dir = str(Path(root).relative_to(_pkg_root))
            datas.append((src, rel_dir))
