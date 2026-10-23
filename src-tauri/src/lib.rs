mod commands;
mod error;
mod gmail;
mod model;
mod secrets;
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
            app.manage(commands::AppState::new(dir.join("vault.bin"))?);
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::gmail_status,
            commands::gmail_connect,
            commands::gmail_sync,
            commands::gmail_disconnect,
            commands::list_topics,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
