mod backend;
mod commands;
mod config;
mod error;
mod host;
mod model;
mod secrets;
mod store;
mod vault;

use tauri::Manager;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            let dir = app.path().app_data_dir()?;
            std::fs::create_dir_all(&dir)?;
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                std::fs::set_permissions(&dir, std::fs::Permissions::from_mode(0o700))?;
            }
            app.manage(store::Store::new(dir.join("vault.bin")));
            app.manage(backend::Backend::new());
            tauri::async_runtime::spawn(backend::Backend::supervise(app.handle().clone()));
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![commands::call])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
