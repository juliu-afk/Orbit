// 关闭 Windows 控制台——Tauri WebView 提供 UI
#![windows_subsystem = "windows"]

use std::fs;
use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Child, Command};
use std::thread;
use std::time::{Duration, Instant};

/// 编译期嵌入 orbit-backend.exe，运行时解压到临时目录
const BACKEND_EXE: &[u8] = include_bytes!("../orbit-backend.exe");

/// 将嵌入的后端 exe 写到临时目录，返回路径
fn extract_backend() -> PathBuf {
    let dir = std::env::temp_dir().join("orbit");
    fs::create_dir_all(&dir).ok();
    let exe_path = dir.join("orbit-backend.exe");
    // 每次启动强制写入——确保更新生效（SSD 上 ~0.5s，可接受）
    let _ = fs::remove_file(&exe_path);
    fs::write(&exe_path, BACKEND_EXE).expect("无法解压后端程序");
    exe_path
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

/// TCP 轮询等后端就绪，最多等 30 秒
fn wait_for_backend(addr: &str, timeout_secs: u64) -> bool {
    let deadline = Instant::now() + Duration::from_secs(timeout_secs);
    while Instant::now() < deadline {
        if TcpStream::connect_timeout(&addr.parse().unwrap(), Duration::from_secs(1)).is_ok() {
            return true;
        }
        thread::sleep(Duration::from_millis(500));
    }
    false
}

/// 清理临时目录中的后端 exe（删不掉就留 %TEMP%，Windows 自动清）
fn cleanup_backend(exe_path: &PathBuf) {
    let _ = fs::remove_file(exe_path);
}

fn main() {
    // 解压后端到临时目录
    let backend_path = extract_backend();

    println!("Orbit — 启动后端...");
    let mut backend = start_backend(&backend_path);

    if wait_for_backend("127.0.0.1:18888", 30) {
        println!("后端就绪，打开窗口...");
    } else {
        eprintln!("⚠ 后端启动超时，仍尝试打开窗口");
    }

    // Tauri v2——程序化创建窗口，直接加载后端 URL
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
