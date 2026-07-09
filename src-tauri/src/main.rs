// 关闭 Windows 控制台——Tauri WebView 提供 UI
#![windows_subsystem = "windows"]

use std::fs;
use std::fs::File;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};

const BOOT_HTML: &str = include_str!("../boot.html");
const BACKEND_EXE: &[u8] = include_bytes!("../orbit-backend.exe");

fn extract_backend() -> PathBuf {
    let dir = std::env::temp_dir().join("orbit");
    fs::create_dir_all(&dir).ok();
    let exe_path = dir.join("orbit-backend.exe");
    kill_existing_backend(&exe_path);
    let _ = fs::remove_file(&exe_path);
    fs::write(&exe_path, BACKEND_EXE).expect("无法解压后端程序");
    exe_path
}

#[cfg(target_os = "windows")]
fn kill_existing_backend(_exe_path: &PathBuf) {
    use std::os::windows::process::CommandExt;
    let _ = std::process::Command::new("taskkill")
        .args(["/F", "/IM", "orbit-backend.exe"])
        .creation_flags(0x08000000)
        .output();
    std::thread::sleep(std::time::Duration::from_millis(800));
}

#[cfg(not(target_os = "windows"))]
fn kill_existing_backend(_exe_path: &PathBuf) {
    let _ = std::process::Command::new("pkill")
        .args(["-f", "orbit-backend"])
        .output();
    std::thread::sleep(std::time::Duration::from_millis(800));
}

fn start_backend(exe_path: &PathBuf, log_path: &PathBuf) -> std::io::Result<Child> {
    let log_file = File::create(log_path)?;
    let err_file = log_file.try_clone()?;
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        let exe_dir = std::env::current_exe()
            .ok().and_then(|p| p.parent().map(|d| d.to_path_buf()))
            .unwrap_or_default();
        Command::new(exe_path)
            .env("ORBIT_HOME", &exe_dir)
            .creation_flags(CREATE_NO_WINDOW)
            .stdout(Stdio::from(log_file))
            .stderr(Stdio::from(err_file))
            .spawn()
    }
    #[cfg(not(target_os = "windows"))]
    {
        Command::new(exe_path)
            .stdout(Stdio::from(log_file))
            .stderr(Stdio::from(err_file))
            .spawn()
    }
}

fn cleanup_backend(exe_path: &PathBuf) {
    let _ = fs::remove_file(exe_path);
}

fn percent_encode(s: &str) -> String {
    let bytes = s.as_bytes();
    let mut out = String::with_capacity(bytes.len() * 2);
    for &b in bytes {
        match b {
            b'%' => out.push_str("%25"),
            b'#' => out.push_str("%23"),
            b'\n' => out.push_str("%0A"),
            b'\r' => out.push_str("%0D"),
            b' '..=b'~' => out.push(b as char),
            _ => {
                use std::fmt::Write;
                let _ = write!(out, "%{:02X}", b);
            }
        }
    }
    out
}

/// 启动前清理 18888 端口残留进程
fn free_port_18888() {
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        let output = std::process::Command::new("netstat")
            .args(["-ano"])
            .creation_flags(0x08000000)
            .output();
        if let Ok(out) = output {
            let text = String::from_utf8_lossy(&out.stdout);
            for line in text.lines() {
                if line.contains(":18888") && line.contains("LISTENING") {
                    let parts: Vec<&str> = line.split_whitespace().collect();
                    if let Some(pid) = parts.last() {
                        let _ = std::process::Command::new("taskkill")
                            .args(["/F", "/PID", pid])
                            .creation_flags(0x08000000)
                            .output();
                        std::thread::sleep(std::time::Duration::from_millis(500));
                    }
                }
            }
        }
    }
    #[cfg(not(target_os = "windows"))]
    {
        let _ = std::process::Command::new("fuser")
            .args(["-k", "18888/tcp"])
            .output();
    }
}

fn main() {
    free_port_18888();
    let backend_path = extract_backend();
    let log_path = backend_path.parent().unwrap().join("orbit_runtime.log");
    println!("Orbit — 启动后端...");
    let mut backend = start_backend(&backend_path, &log_path).unwrap_or_else(|e| {
        let msg = format!("Failed to start backend: {}", e);
        let _ = fs::write(backend_path.parent().unwrap().join("orbit_error.log"), &msg);
        panic!("{}", msg)
    });

    let boot_url = format!(
        "data:text/html;charset=utf-8,{}",
        percent_encode(BOOT_HTML)
    );

    tauri::Builder::default()
        .setup(move |app| {
            use tauri::WebviewUrl;
            use tauri::WebviewWindowBuilder;
            let _window = WebviewWindowBuilder::new(
                app, "main",
                WebviewUrl::External(boot_url.parse().unwrap()),
            )
            .title("Orbit")
            .inner_size(1400.0, 900.0)
            .resizable(true)
            .decorations(false)
            .transparent(true)
            .shadow(false)
            .center()
            .focused(true)
            .visible(true)
            .build()?;
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("Tauri 启动失败")
        .run(move |_app, event| {
            if let tauri::RunEvent::Exit = event {
                kill_existing_backend(&backend_path);
                let _ = backend.kill();
                let _ = backend.wait();
                cleanup_backend(&backend_path);
            }
        });
}
