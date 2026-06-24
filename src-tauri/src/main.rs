// 关闭 Windows 控制台——Tauri WebView 提供 UI
#![windows_subsystem = "windows"]

use std::fs;
use std::path::PathBuf;
use std::process::{Child, Command};

/// 编译期嵌入 orbit-backend.exe，运行时解压到临时目录
const BACKEND_EXE: &[u8] = include_bytes!("../orbit-backend.exe");

/// 将嵌入的后端 exe 写到临时目录，返回路径
fn extract_backend() -> PathBuf {
    let dir = std::env::temp_dir().join("orbit");
    fs::create_dir_all(&dir).ok();
    let exe_path = dir.join("orbit-backend.exe");

    // WHY 先杀旧进程再写: 上次异常退出（崩溃/强制结束）时旧进程可能
    // 仍占用 exe 文件，直接 remove+write 会失败（Os code 32）
    kill_existing_backend(&exe_path);

    let _ = fs::remove_file(&exe_path);
    fs::write(&exe_path, BACKEND_EXE).expect("无法解压后端程序");
    exe_path
}

/// 强制结束可能残留的旧后端进程
#[cfg(target_os = "windows")]
fn kill_existing_backend(_exe_path: &PathBuf) {
    use std::os::windows::process::CommandExt;
    // taskkill /F /IM orbit-backend.exe —— 结束所有同名进程
    let _ = std::process::Command::new("taskkill")
        .args(["/F", "/IM", "orbit-backend.exe"])
        .creation_flags(0x08000000) // CREATE_NO_WINDOW
        .output();
    // 短等进程退出 + 释放文件锁
    std::thread::sleep(std::time::Duration::from_millis(800));
}

#[cfg(not(target_os = "windows"))]
fn kill_existing_backend(_exe_path: &PathBuf) {
    // Unix: pkill orbit-backend
    let _ = std::process::Command::new("pkill")
        .args(["-f", "orbit-backend"])
        .output();
    std::thread::sleep(std::time::Duration::from_millis(800));
}

/// 启动后端进程，隐藏控制台窗口
fn start_backend(exe_path: &PathBuf) -> Child {
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        Command::new(exe_path)
            .creation_flags(CREATE_NO_WINDOW)
            .spawn()
            .expect("无法启动后端进程")
    }

    #[cfg(not(target_os = "windows"))]
    Command::new(exe_path)
        .spawn()
        .expect("无法启动后端进程")
}

/// 清理临时目录中的后端 exe
fn cleanup_backend(exe_path: &PathBuf) {
    let _ = fs::remove_file(exe_path);
}

fn main() {
    // 解压后端到临时目录
    let backend_path = extract_backend();

    println!("Orbit — 启动后端...");
    let mut backend = start_backend(&backend_path);

    // WHY 先开窗再等后端: PyInstaller one-file 解压+Python启动需 10-20s，
    // 先开窗用户立刻看到界面（WebView 显示 connection 状态"连接中..."），
    // 后端就绪后 WebSocket 自动连接，避免用户以为程序卡死。
    tauri::Builder::default()
        .setup(|app| {
            use tauri::WebviewUrl;
            use tauri::WebviewWindowBuilder;

            let _window = WebviewWindowBuilder::new(
                app,
                "main",
                WebviewUrl::External("http://127.0.0.1:18888".parse().unwrap()),
            )
            .title("Orbit — 多 Agent 驾驶舱")
            .inner_size(1400.0, 900.0)
            .resizable(true)
            .build()?;

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("Tauri 启动失败")
        .run(|_app, _event| {});

    // 窗口关闭 → 杀后端 → 清临时文件
    let _ = backend.kill();
    let _ = backend.wait();
    cleanup_backend(&backend_path);
    println!("Orbit 已退出");
}
