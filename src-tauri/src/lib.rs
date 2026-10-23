mod commands;
mod error;
mod gmail;
mod jira;
mod model;
mod oauth;
mod secrets;
mod slack;
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
            commands::list_topics,
            commands::gmail::gmail_status,
            commands::gmail::gmail_connect,
            commands::gmail::gmail_sync,
            commands::gmail::gmail_disconnect,
            commands::slack::slack_status,
            commands::slack::slack_connect,
            commands::slack::slack_sync,
            commands::slack::slack_disconnect,
            commands::jira::jira_status,
            commands::jira::jira_connect,
            commands::jira::jira_sync,
            commands::jira::jira_disconnect,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
