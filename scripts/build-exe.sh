#!/usr/bin/env bash
# build-exe.sh —— Orbit 完整 exe 构建流水线
#
# 流水线：前端构建 → 复制到 backend/static/ → PyInstaller 打包后端 → Tauri 打包壳 → 输出 exe
# 四个步骤缺一不可。不要单独跑其中几步然后说"没变化"。
#
# 用法: bash scripts/build-exe.sh
# 输出: Deliverables/Orbit.exe（完整桌面应用）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FRONTEND_DIR="$ROOT/frontend"
BACKEND_DIR="$ROOT/backend"
TAURI_DIR="$ROOT/src-tauri"
DELIVERABLES="$ROOT/Deliverables"

echo "============================================"
echo " Orbit 完整构建流水线"
echo "============================================"

# ── Step 1: 前端构建 ──
echo ""
echo "[1/4] 构建前端..."
cd "$FRONTEND_DIR"
CI=true pnpm build 2>&1 | tail -3
echo "  ✓ 前端构建完成 → $FRONTEND_DIR/dist/"

# ── Step 2: 复制到 backend/static/ ──
echo ""
echo "[2/4] 复制前端产物到 backend/static/（先清旧文件）..."
# WHY: 清空再复制——避免旧版 JS/CSS 残留混入 PyInstaller 包，导致 exe 膨胀
rm -rf "$BACKEND_DIR/static/"*
cp -r "$FRONTEND_DIR/dist/"* "$BACKEND_DIR/static/"
echo "  ✓ 已复制 → $BACKEND_DIR/static/"

# ── Step 3: PyInstaller 打包后端 ──
echo ""
echo "[3/4] PyInstaller 打包后端..."
cd "$BACKEND_DIR"
# WHY: 清 build 缓存 → 避免旧缓存漏打包新模块
rm -rf build/
pyinstaller orbit.spec --distpath dist --workpath build --noconfirm 2>&1 | grep -E "(INFO: Build|completed|Error)"
echo "  ✓ 后端 exe → $BACKEND_DIR/dist/Orbit.exe"

# 替换 Tauri 内嵌的 backend exe
cp "$BACKEND_DIR/dist/Orbit.exe" "$TAURI_DIR/orbit-backend.exe"
echo "  ✓ 已复制到 $TAURI_DIR/orbit-backend.exe"

# ── Step 4: Tauri 打包壳 ──
echo ""
echo "[4/4] Tauri 打包桌面应用..."
cd "$ROOT"
./frontend/node_modules/.bin/tauri build 2>&1 | grep -E "(Built application|Finished|Error)"
echo "  ✓ Tauri exe → $TAURI_DIR/target/release/orbit.exe"

# ── 输出 ──
mkdir -p "$DELIVERABLES"
cp "$TAURI_DIR/target/release/orbit.exe" "$DELIVERABLES/Orbit.exe"

echo ""
echo "============================================"
echo " ✓ 构建完成"
echo "   $DELIVERABLES/Orbit.exe"
ls -lh "$DELIVERABLES/Orbit.exe"
echo "============================================"
