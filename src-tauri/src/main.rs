#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::{BufRead, BufReader};
use std::process::{Child, Command, Stdio};
use std::sync::mpsc;
use std::sync::Mutex;

use tauri::menu::{AboutMetadataBuilder, MenuBuilder, PredefinedMenuItem, SubmenuBuilder};
use std::sync::atomic::{AtomicBool, AtomicU16, Ordering};

use tauri::image::Image;
use tauri::tray::{TrayIcon, TrayIconBuilder};
use tauri::{Manager, RunEvent, WebviewUrl, WebviewWindowBuilder, WindowEvent};
use tauri_plugin_dialog::FilePath;
use tauri_plugin_dialog::DialogExt;

struct Backend(Mutex<Option<Child>>);
struct Tray(Mutex<Option<TrayIcon>>);
static TRAY_ENABLED: AtomicBool = AtomicBool::new(false);
static ENGINE_PORT: AtomicU16 = AtomicU16::new(0);

const MEDIA_EXTS: &[&str] = &[
    "jpg", "jpeg", "png", "heic", "heif", "gif", "webp", "tif", "tiff", "bmp",
    "dng", "mov", "mp4", "m4v", "webm", "mkv", "3gp", "avi", "avif", "mts",
    "cr2", "cr3", "crw", "nef", "nrw", "arw", "srf", "sr2", "raf", "orf", "rw2", "rwl", "pef",
    "srw", "x3f", "3fr", "iiq", "erf", "kdc", "dcr", "mos", "mrw",
];

fn paths_to_strings(paths: Vec<FilePath>) -> Vec<String> {
    paths
        .into_iter()
        .filter_map(|p| p.into_path().ok())
        .map(|p| p.to_string_lossy().to_string())
        .collect()
}

fn post_import(paths: Vec<String>) {
    let port = ENGINE_PORT.load(Ordering::Relaxed);
    if port == 0 || paths.is_empty() {
        return;
    }
    engine_post(
        port,
        "/api/import",
        serde_json::json!({ "path": paths[0], "paths": paths }),
    );
}

fn set_tray(handle: &tauri::AppHandle, enabled: bool) {
    TRAY_ENABLED.store(enabled, Ordering::Relaxed);
    let slot = handle.state::<Tray>();
    let mut guard = slot.0.lock().unwrap();
    if !enabled {
        if let Some(tray) = guard.take() {
            let _ = tray.set_visible(false);
        }
        return;
    }
    if guard.is_some() {
        return;
    }
    let build = || -> tauri::Result<TrayIcon> {
        let icon = Image::from_bytes(include_bytes!("../icons/menubar/trayTemplate@2x.png"))?;
        let menu = MenuBuilder::new(handle)
            .text("tray-open", "Open DAM")
            .separator()
            .text("tray-import-files", "Import Photos & Videos...")
            .text("tray-import-folder", "Import Folder...")
            .separator()
            .text("tray-quit", "Quit DAM")
            .build()?;
        TrayIconBuilder::with_id("dam-tray")
            .icon(icon)
            .icon_as_template(true)
            .menu(&menu)
            .on_menu_event(|app, event| {
                use tauri_plugin_dialog::DialogExt;
                match event.id().as_ref() {
                    "tray-open" => {
                        if let Some(win) = app.get_webview_window("main") {
                            let _ = win.show();
                            let _ = win.unminimize();
                            let _ = win.set_focus();
                        }
                    }
                    "tray-import-files" => {
                        let mut dialog = app.dialog().file();
                        dialog = dialog.add_filter("Photos & Videos", MEDIA_EXTS);
                        dialog.pick_files(|paths| {
                            if let Some(list) = paths {
                                post_import(paths_to_strings(list));
                            }
                        });
                    }
                    "tray-import-folder" => {
                        app.dialog().file().pick_folder(|folder| {
                            if let Some(path) = folder {
                                post_import(paths_to_strings(vec![path]));
                            }
                        });
                    }
                    "tray-quit" => {
                        kill_backend(app);
                        std::process::exit(0);
                    }
                    _ => {}
                }
            })
            .build(handle)
    };
    match build() {
        Ok(tray) => {
            guard.replace(tray);
        }
        Err(_) => {
            TRAY_ENABLED.store(false, Ordering::Relaxed);
        }
    }
}

const AIR_FALLBACK: (f64, f64) = (1323.0, 860.0);

fn kill_backend(handle: &tauri::AppHandle) {
    if let Some(mut child) = handle.state::<Backend>().0.lock().unwrap().take() {
        let _ = child.kill();
        let _ = child.wait();
    }
}

const KC_SERVICE: &str = "ai.nodemode.dam.vault";
const KC_ACCOUNT: &str = "dam";
const KC_LEGACY: (&str, &str) = ("ai.nodemode.damp.vault", "damp");

#[cfg(target_os = "macos")]
fn bio_available() -> bool {
    use objc2_local_authentication::{LAContext, LAPolicy};
    let ctx = unsafe { LAContext::new() };
    unsafe {
        ctx.canEvaluatePolicy_error(LAPolicy::DeviceOwnerAuthenticationWithBiometrics)
            .is_ok()
    }
}

#[cfg(not(target_os = "macos"))]
fn bio_available() -> bool {
    false
}

#[cfg(target_os = "macos")]
fn bio_evaluate(reason: &str) -> bool {
    use block2::RcBlock;
    use objc2_foundation::NSString;
    use objc2_local_authentication::{LAContext, LAPolicy};

    let ctx = unsafe { LAContext::new() };
    if unsafe {
        ctx.canEvaluatePolicy_error(LAPolicy::DeviceOwnerAuthenticationWithBiometrics)
            .is_err()
    } {
        return false;
    }
    let (tx, rx) = mpsc::channel::<bool>();
    let block = RcBlock::new(
        move |success: objc2::runtime::Bool, _err: *mut objc2_foundation::NSError| {
            let _ = tx.send(success.as_bool());
        },
    );
    let ns_reason = NSString::from_str(reason);
    unsafe {
        ctx.evaluatePolicy_localizedReason_reply(
            LAPolicy::DeviceOwnerAuthenticationWithBiometrics,
            &ns_reason,
            &block,
        );
    }
    let outcome = rx
        .recv_timeout(std::time::Duration::from_secs(120))
        .unwrap_or(false);
    drop(ctx);
    outcome
}

#[cfg(not(target_os = "macos"))]
fn bio_evaluate(_reason: &str) -> bool {
    false
}

#[cfg(target_os = "macos")]
fn kc_present() -> bool {
    use security_framework::item::{ItemClass, ItemSearchOptions};
    [(KC_SERVICE, KC_ACCOUNT), KC_LEGACY].iter().any(|(service, account)| {
        ItemSearchOptions::new()
            .class(ItemClass::generic_password())
            .service(service)
            .account(account)
            .load_attributes(true)
            .limit(1)
            .search()
            .map(|found| !found.is_empty())
            .unwrap_or(false)
    })
}

#[cfg(not(target_os = "macos"))]
fn kc_present() -> bool {
    false
}

#[cfg(target_os = "macos")]
fn kc_read() -> Option<String> {
    let read = |service: &str, account: &str| {
        security_framework::passwords::get_generic_password(service, account)
            .ok()
            .and_then(|bytes| String::from_utf8(bytes).ok())
    };
    if let Some(found) = read(KC_SERVICE, KC_ACCOUNT) {
        return Some(found);
    }
    let legacy = read(KC_LEGACY.0, KC_LEGACY.1)?;
    if kc_write(&legacy) {
        let _ = security_framework::passwords::delete_generic_password(KC_LEGACY.0, KC_LEGACY.1);
    }
    Some(legacy)
}

#[cfg(not(target_os = "macos"))]
fn kc_read() -> Option<String> {
    None
}

#[cfg(target_os = "macos")]
fn kc_write(passkey: &str) -> bool {
    security_framework::passwords::set_generic_password(KC_SERVICE, KC_ACCOUNT, passkey.as_bytes())
        .is_ok()
}

#[cfg(not(target_os = "macos"))]
fn kc_write(_passkey: &str) -> bool {
    false
}

fn engine_post(port: u16, path: &str, body: serde_json::Value) {
    let _ = ureq::post(&format!("http://127.0.0.1:{port}{path}"))
        .set("x-dam-local", "1")
        .timeout(std::time::Duration::from_secs(10))
        .send_json(body);
}

fn engine_get(port: u16, path: &str) -> Option<serde_json::Value> {
    ureq::get(&format!("http://127.0.0.1:{port}{path}"))
        .set("x-dam-local", "1")
        .timeout(std::time::Duration::from_secs(10))
        .call()
        .ok()
        .and_then(|res| res.into_json::<serde_json::Value>().ok())
}

static SHOWN: AtomicBool = AtomicBool::new(false);
static DIAG_OPAQUE: AtomicBool = AtomicBool::new(true);
static DIAG_WV: AtomicBool = AtomicBool::new(false);
static DIAG_KVC: AtomicBool = AtomicBool::new(false);
static DIAG_UNDER: AtomicBool = AtomicBool::new(false);

#[cfg(target_os = "macos")]
fn clear_webview_backdrop(handle: &tauri::AppHandle) {
    use objc2::msg_send;
    use objc2::runtime::AnyObject;
    let Some(win) = handle.get_webview_window("main") else { return };
    if let Ok(ptr) = win.ns_window() {
        let ns = unsafe { &*(ptr as *const objc2_app_kit::NSWindow) };
        let clear = objc2_app_kit::NSColor::clearColor();
        ns.setOpaque(false);
        ns.setBackgroundColor(Some(&clear));
        DIAG_OPAQUE.store(ns.isOpaque(), Ordering::Relaxed);
        ns.setAlphaValue(1.0);
        ns.setHasShadow(false);
    }
    let _ = win.with_webview(|webview| {
        let wk: *mut AnyObject = webview.inner().cast();
        if wk.is_null() {
            return;
        }
        DIAG_WV.store(true, Ordering::Relaxed);
        let wk = unsafe { &*wk };
        unsafe {
            let no = objc2_foundation::NSNumber::new_bool(false);
            let key = objc2_foundation::NSString::from_str("drawsBackground");
            let _: () = msg_send![wk, setValue: &*no, forKey: &*key];
            let read: *mut AnyObject = msg_send![wk, valueForKey: &*key];
            let draws: bool = if read.is_null() { false } else { msg_send![&*read, boolValue] };
            DIAG_KVC.store(!draws, Ordering::Relaxed);
            let sel = objc2::sel!(setUnderPageBackgroundColor:);
            let responds: bool = msg_send![wk, respondsToSelector: sel];
            if responds {
                let clear = objc2_app_kit::NSColor::clearColor();
                let _: () = msg_send![wk, setUnderPageBackgroundColor: &*clear];
            }
            DIAG_UNDER.store(responds, Ordering::Relaxed);
        }
    });
}

#[cfg(not(target_os = "macos"))]
fn clear_webview_backdrop(_handle: &tauri::AppHandle) {}

fn glass_diag() -> String {
    format!(
        "win_opaque={} webviews={} kvc_bg={} underpage={}",
        u8::from(DIAG_OPAQUE.load(Ordering::Relaxed)),
        u8::from(DIAG_WV.load(Ordering::Relaxed)),
        u8::from(DIAG_KVC.load(Ordering::Relaxed)),
        u8::from(DIAG_UNDER.load(Ordering::Relaxed)),
    )
}

#[cfg(target_os = "macos")]
fn set_window_blur(handle: &tauri::AppHandle, radius: i32) {
    // Shaped desktop blur: the system effect view is the ONE blur macOS can
    // clip to rounded corners (CGS blur is bound to the square window bounds
    // & showed as a ghost square corner). UnderWindowBackground blurs the
    // desktop behind the window; radius matches --win-radius; state Active
    // keeps it while unfocused. Backdrop re-cleared after, per the round-32
    // ordering lesson.
    let Some(win) = handle.get_webview_window("main") else { return };
    if radius > 0 {
        let effects = tauri::window::EffectsBuilder::new()
            .effect(tauri::window::Effect::UnderWindowBackground)
            .state(tauri::window::EffectState::Active)
            .radius(12.0)
            .build();
        let _ = win.set_effects(effects);
    } else {
        let _ = win.set_effects(None);
    }
    clear_webview_backdrop(handle);
}

#[cfg(not(target_os = "macos"))]
fn set_window_blur(_handle: &tauri::AppHandle, _radius: i32) {}

fn handle_ctrl_line(port: u16, line: &str) {
    let mut parts = line.split_whitespace();
    let _tag = parts.next();
    let kind = parts.next().unwrap_or("");
    let nonce = parts.next().unwrap_or("").to_string();
    if nonce.is_empty() {
        return;
    }
    match kind {
        "BIOUNLOCK" => {
            let ok = bio_evaluate("unlock DAM private items");
            let passkey = if ok { kc_read() } else { None };
            engine_post(
                port,
                "/api/internal/bio/result",
                serde_json::json!({
                    "nonce": nonce,
                    "ok": ok && passkey.is_some(),
                    "passkey": passkey,
                    "stored": kc_present(),
                }),
            );
        }
        "WINSHOW" => {
            let _ = HANDLE.get().map(|h| {
                let h2 = h.clone();
                h.run_on_main_thread(move || {
                    clear_webview_backdrop(&h2);
                    if let Some(win) = h2.get_webview_window("main") {
                        let _ = win.show();
                        let _ = win.set_focus();
                    }
                    SHOWN.store(true, Ordering::Relaxed);
                })
            });
        }
        "WINCLEAR" => {
            let _ = HANDLE.get().map(|h| {
                let h2 = h.clone();
                h.run_on_main_thread(move || clear_webview_backdrop(&h2))
            });
        }
        "WINBLUR" => {
            if let Ok(radius) = nonce.parse::<i32>() {
                let _ = HANDLE.get().map(|h| {
                    let h2 = h.clone();
                    h.run_on_main_thread(move || set_window_blur(&h2, radius))
                });
            }
        }
        "TRAYSET" => {
            let enabled = nonce == "1";
            let _ = HANDLE.get().map(|h| {
                let h2 = h.clone();
                h.run_on_main_thread(move || set_tray(&h2, enabled))
            });
        }
        "KCSTORE" => {
            let passkey = engine_get(port, &format!("/api/internal/bio/pending/{nonce}"))
                .and_then(|v| v.get("passkey").and_then(|p| p.as_str().map(str::to_string)));
            let ok = passkey.as_deref().map(kc_write).unwrap_or(false);
            engine_post(
                port,
                "/api/internal/bio/result",
                serde_json::json!({ "nonce": nonce, "ok": ok, "stored": kc_present() }),
            );
        }
        _ => {}
    }
}

fn backend_command(handle: &tauri::AppHandle) -> Result<Command, String> {
    let resources = handle
        .path()
        .resource_dir()
        .map_err(|e| format!("no resource dir: {e}"))?;
    let dir = resources.join("dam-backend");
    let bin = dir.join("dam-backend");
    let mut cmd = Command::new(&bin);
    cmd.current_dir(&dir)
        .env("DAM_PORT", "0")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    Ok(cmd)
}

static HANDLE: std::sync::OnceLock<tauri::AppHandle> = std::sync::OnceLock::new();

fn main() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(Backend(Mutex::new(None)))
        .manage(Tray(Mutex::new(None)))
        .setup(|app| {
            let handle = app.handle().clone();
            let _ = HANDLE.set(handle.clone());

            let about = AboutMetadataBuilder::new()
                .name(Some("DAM"))
                .comments(Some("Local-first digital asset manager for photos & video"))
                .build();
            let app_menu = SubmenuBuilder::new(app, "DAM")
                .about(Some(about))
                .separator()
                .text("open-settings", "Settings...")
                .separator()
                .services()
                .separator()
                .hide()
                .hide_others()
                .show_all()
                .separator()
                .quit()
                .build()?;
            let edit_menu = SubmenuBuilder::new(app, "Edit")
                .undo()
                .redo()
                .separator()
                .cut()
                .copy()
                .paste()
                .select_all()
                .build()?;
            let window_menu = SubmenuBuilder::new(app, "Window")
                .minimize()
                .item(&PredefinedMenuItem::maximize(app, Some("Zoom"))?)
                .separator()
                .close_window()
                .build()?;
            #[cfg(target_os = "macos")]
            window_menu.set_as_windows_menu_for_nsapp()?;
            let menu = MenuBuilder::new(app)
                .items(&[&app_menu, &edit_menu, &window_menu])
                .build()?;
            app.set_menu(menu)?;
            app.on_menu_event(|handle, event| {
                if event.id().as_ref() == "open-settings" {
                    if let Some(win) = handle.get_webview_window("main") {
                        let _ = win.eval(
                            "window.dispatchEvent(new CustomEvent('dam-menu',{detail:'settings'}))",
                        );
                    }
                }
            });

            let (width, height) = handle
                .primary_monitor()
                .ok()
                .flatten()
                .map(|monitor| {
                    let size = monitor.size();
                    let scale = monitor.scale_factor();
                    (
                        (size.width as f64 / scale) * 0.9,
                        (size.height as f64 / scale) * 0.9,
                    )
                })
                .unwrap_or(AIR_FALLBACK);
            let builder = WebviewWindowBuilder::new(
                &handle,
                "main",
                WebviewUrl::App("splash.html".into()),
            )
            .title("DAM")
            .disable_drag_drop_handler()
            .transparent(true)
            .visible(false)
            .on_page_load(|window, payload| {
                // Reveal at the SPLASH's painted load: instant perceived launch
                // w/ the splash animation visible while the engine boots; the
                // splash paints its own opaque background so this stays
                // flash-free. Later navigations no-op via SHOWN.
                if matches!(payload.event(), tauri::webview::PageLoadEvent::Finished)
                    && !SHOWN.load(Ordering::Relaxed)
                {
                    SHOWN.store(true, Ordering::Relaxed);
                    let _ = window.show();
                    let _ = window.set_focus();
                }
            })
            .inner_size(width, height)
            .min_inner_size(980.0, 640.0)
            .center();
            let window = builder.build()?;
            clear_webview_backdrop(&handle);

            let mut child = backend_command(&handle)?
                .spawn()
                .map_err(|e| format!("the DAM engine failed to spawn: {e}"))?;
            let stdout = child.stdout.take();
            let stderr = child.stderr.take();
            handle.state::<Backend>().0.lock().unwrap().replace(child);

            let (tx, rx) = mpsc::channel::<String>();
            for stream in [stdout.map(|s| Box::new(s) as Box<dyn std::io::Read + Send>), stderr.map(|s| Box::new(s) as Box<dyn std::io::Read + Send>)].into_iter().flatten() {
                let tx = tx.clone();
                std::thread::spawn(move || {
                    for line in BufReader::new(stream).lines().map_while(Result::ok) {
                        if tx.send(line).is_err() {
                            break;
                        }
                    }
                });
            }
            drop(tx);

            let handle2 = handle.clone();
            std::thread::spawn(move || {
                let pattern = regex::Regex::new(r"http://127\.0\.0\.1:(\d+)").unwrap();
                let mut port: Option<u16> = None;
                for line in rx.iter() {
                    if let Some(captures) = pattern.captures(&line) {
                        port = captures[1].parse().ok();
                        if port.is_some() {
                            break;
                        }
                    }
                }
                match port {
                    Some(found) => {
                        let url: tauri::Url = format!("http://127.0.0.1:{found}")
                            .parse()
                            .expect("loopback url");
                        let _ = window.navigate(url);
                        let hshow = handle2.clone();
                        std::thread::spawn(move || {
                            std::thread::sleep(std::time::Duration::from_secs(2));
                            if !SHOWN.load(Ordering::Relaxed) {
                                let h6 = hshow.clone();
                                let _ = hshow.run_on_main_thread(move || {
                                    clear_webview_backdrop(&h6);
                                    if let Some(win) = h6.get_webview_window("main") {
                                        let _ = win.show();
                                    }
                                    SHOWN.store(true, Ordering::Relaxed);
                                });
                            }
                        });
                        let h4 = handle2.clone();
                        std::thread::spawn(move || {
                            for ms in [50u64, 250, 700, 1500, 3000] {
                                std::thread::sleep(std::time::Duration::from_millis(ms));
                                let h5 = h4.clone();
                                let _ = h4.run_on_main_thread(move || clear_webview_backdrop(&h5));
                            }
                            engine_post(
                                found,
                                "/api/internal/shell/glass",
                                serde_json::json!({ "diag": glass_diag() }),
                            );
                        });
                        engine_post(
                            found,
                            "/api/internal/shell/hello",
                            serde_json::json!({ "bio": bio_available(), "stored": kc_present() }),
                        );
                        ENGINE_PORT.store(found, Ordering::Relaxed);
                        if let Some(pref) = engine_get(found, "/api/system/menubar") {
                            if pref.get("enabled").and_then(|v| v.as_bool()).unwrap_or(false) {
                                let h3 = handle2.clone();
                                let _ = handle2.run_on_main_thread(move || set_tray(&h3, true));
                            }
                        }
                        for line in rx.iter() {
                            if line.starts_with("DAM-CTRL ") {
                                handle_ctrl_line(found, &line);
                            }
                        }
                    }
                    None => {
                        handle2
                            .dialog()
                            .message("The DAM engine failed to start. Please relaunch the app.")
                            .blocking_show();
                        kill_backend(&handle2);
                        std::process::exit(1);
                    }
                }
            });
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("tauri app should build");

    app.run(|handle, event| match event {
        RunEvent::Exit => kill_backend(handle),
        RunEvent::WindowEvent {
            event: WindowEvent::CloseRequested { api, .. },
            label,
            ..
        } => {
            if TRAY_ENABLED.load(Ordering::Relaxed) {
                api.prevent_close();
                if let Some(win) = handle.get_webview_window(&label) {
                    let _ = win.hide();
                }
            }
        }
        _ => {}
    });
}
