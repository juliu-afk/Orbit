#!/bin/bash
# Orbit 桌面版完整构建链
# 用法: bash scripts/build-desktop.sh
#
# 两段式:
#   1. PyInstaller 编译后端 → Deliverables/Orbit-backend.exe
#   2. 复制到 src-tauri/ + Tauri cargo build → Deliverables/Orbit.exe (桌面壳)
#
# 注意: 仅改前端 → 只需步骤 1.5 + 2
#       仅改后端 → 需要完整的 1→2→3→4→5

set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== 0. 杀旧进程 ==="
taskkill //F //IM Orbit.exe 2>/dev/null || true
taskkill //F //IM orbit-backend.exe 2>/dev/null || true
sleep 2

echo "=== 0.5 PyInstaller spec check ==="
python scripts/check_spec.py || { echo "FAIL: spec check failed, fix before build"; exit 1; }

echo "=== 1. 前端构建 ==="
cd frontend
CI=true pnpm build
cd "$ROOT"

echo "=== 2. 复制前端产物到后端 static ==="
rm -rf backend/static/assets
cp -r frontend/dist/* backend/static/

echo "=== 3. PyInstaller 编译后端 ==="
rm -rf backend/build
cd backend
python -m PyInstaller orbit.spec --distpath ../Deliverables --workpath build --noconfirm
cd "$ROOT"
ls -lh Deliverables/Orbit.exe

echo "=== 4. 替换 Tauri 内嵌后端 ==="
cp Deliverables/Orbit.exe src-tauri/orbit-backend.exe
ls -lh src-tauri/orbit-backend.exe

echo "=== 5. Tauri cargo build ==="
cd src-tauri
cargo build --release
cd "$ROOT"

echo "=== 6. 输出桌面版 ==="
cp src-tauri/target/release/orbit.exe Deliverables/Orbit.exe
ls -lh Deliverables/Orbit.exe

echo "=== 7. API smoke test ==="
# 启动 exe → 等待就绪 → 测探针+health+chat → 杀进程
start "" "Deliverables/Orbit.exe"
sleep 5
python scripts/smoke_test.py --timeout 60
SMOKE_EXIT=$?
taskkill //F //IM Orbit.exe 2>/dev/null || true
taskkill //F //IM orbit-backend.exe 2>/dev/null || true
if [ $SMOKE_EXIT -ne 0 ]; then
    echo "FAIL: smoke test failed, check logs"
    exit 1
fi

echo ""
echo "✅ 构建完成: Deliverables/Orbit.exe"
echo "   Tauri 桌面壳 (内嵌 orbit-backend.exe + WebView 窗口)"
