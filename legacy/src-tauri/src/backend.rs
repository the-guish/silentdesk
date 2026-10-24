//! The Python backend: a child process that runs every source and the sync
//! logic. Rust starts it, hands it the stored secrets and settings, relays
//! the UI's calls to it, answers its storage requests, and restarts it if it
//! exits. See docs/specs/backend.md.
//!
//! Messages are JSON, one per line, over the child's stdin and stdout. Both
//! sides send requests and match responses by id; a message without a
//! `method` is a response.

use std::collections::HashMap;
use std::path::PathBuf;
use std::process::Stdio;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex as SyncMutex};
use std::time::{Duration, Instant};

use serde_json::{Map, Value, json};
use tauri::{AppHandle, Manager};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::process::{ChildStdin, ChildStdout, Command};
use tokio::sync::{mpsc, oneshot, watch};

use crate::config::Config;
use crate::error::{Error, Result};
use crate::host;
use crate::secrets::{self, BACKEND_SECRETS};

/// How long a call waits for the backend to start or restart.
const START_WAIT: Duration = Duration::from_secs(20);
/// Restarts back off from the first delay to the last, and reset once the
/// backend has stayed up for `STABLE`.
const FIRST_RESTART_DELAY: Duration = Duration::from_secs(1);
const LAST_RESTART_DELAY: Duration = Duration::from_secs(60);
const STABLE: Duration = Duration::from_secs(60);

/// The error message, already worded for the user.
type Reply = std::result::Result<Value, String>;

/// One running backend process.
struct Connection {
    outgoing: mpsc::UnboundedSender<String>,
    pending: SyncMutex<HashMap<u64, oneshot::Sender<Reply>>>,
    next_id: AtomicU64,
    closed: AtomicBool,
}

impl Connection {
    fn send(&self, message: Value) {
        let _ = self.outgoing.send(message.to_string());
    }

    async fn request(&self, method: &str, params: Value) -> Result<Value> {
        let id = self.next_id.fetch_add(1, Ordering::Relaxed);
        let (tx, rx) = oneshot::channel();
        self.pending.lock().unwrap().insert(id, tx);
        // `close` sets the flag before failing what is pending, so a request
        // added after that sees the flag.
        if self.closed.load(Ordering::SeqCst) {
            self.pending.lock().unwrap().remove(&id);
            return Err(Error::BackendDown("it stopped.".into()));
        }
        self.send(json!({"id": id, "method": method, "params": params}));
        match rx.await {
            Ok(Ok(result)) => Ok(result),
            Ok(Err(message)) => Err(Error::Backend(message)),
            Err(_) => Err(Error::BackendDown("it stopped while answering.".into())),
        }
    }

    fn resolve(&self, message: &Map<String, Value>) {
        let Some(id) = message.get("id").and_then(Value::as_u64) else {
            return;
        };
        let Some(tx) = self.pending.lock().unwrap().remove(&id) else {
            return;
        };
        let reply = match message.get("error") {
            Some(error) => Err(error
                .get("message")
                .and_then(Value::as_str)
                .unwrap_or("Something went wrong.")
                .to_owned()),
            None => Ok(message.get("result").cloned().unwrap_or(Value::Null)),
        };
        let _ = tx.send(reply);
    }

    /// Fails every request still waiting for an answer.
    fn close(&self) {
        self.closed.store(true, Ordering::SeqCst);
        self.pending.lock().unwrap().clear();
    }
}

/// The current backend process, if one is running and initialized.
pub struct Backend {
    current: watch::Sender<Option<Arc<Connection>>>,
}

impl Backend {
    pub fn new() -> Self {
        Self {
            current: watch::Sender::new(None),
        }
    }

    /// Calls `method` on the backend, waiting for it to start if needed.
    pub async fn call(&self, method: &str, params: Value) -> Result<Value> {
        let mut current = self.current.subscribe();
        let connection = tokio::time::timeout(START_WAIT, current.wait_for(Option::is_some))
            .await
            .map_err(|_| Error::BackendDown("it did not start. See the log for details.".into()))?
            .map_err(|_| Error::BackendDown("the app is closing.".into()))?
            .clone()
            .expect("waited for a connection");
        connection.request(method, params).await
    }

    /// Starts the backend, and starts it again whenever it exits. Runs for
    /// the life of the app.
    pub async fn supervise(app: AppHandle) {
        let backend = app.state::<Backend>();
        let mut delay = FIRST_RESTART_DELAY;
        loop {
            let started = Instant::now();
            match run(&app, &backend).await {
                Ok(()) => eprintln!("silentdesk: the backend exited; restarting"),
                Err(e) => eprintln!("silentdesk: the backend failed: {e}"),
            }
            backend.current.send_replace(None);
            if started.elapsed() >= STABLE {
                delay = FIRST_RESTART_DELAY;
            }
            tokio::time::sleep(delay).await;
            delay = (delay * 2).min(LAST_RESTART_DELAY);
        }
    }
}

/// Runs one backend process until it exits.
async fn run(app: &AppHandle, backend: &Backend) -> Result<()> {
    let mut child = command(app)?.spawn()?;
    let stdin = child.stdin.take().expect("stdin is piped");
    let stdout = child.stdout.take().expect("stdout is piped");

    let (outgoing, lines) = mpsc::unbounded_channel();
    let connection = Arc::new(Connection {
        outgoing,
        pending: SyncMutex::new(HashMap::new()),
        next_id: AtomicU64::new(1),
        closed: AtomicBool::new(false),
    });
    let writer = tokio::spawn(write_lines(stdin, lines));
    let reader = read_messages(app.clone(), connection.clone(), stdout);
    tokio::pin!(reader);

    // The first request hands over secrets and settings. Calls from the UI
    // wait until it is answered.
    let init = async {
        let params = json!({"secrets": stored_secrets().await?, "config": Config::from_env()});
        connection.request("init", params).await
    };
    let started = tokio::select! {
        result = init => result.map(|_| ()),
        () = &mut reader => Err(Error::BackendDown("it exited while starting.".into())),
    };
    if started.is_ok() {
        backend.current.send_replace(Some(connection.clone()));
        reader.await;
    }

    connection.close();
    writer.abort();
    // Dropping the child would kill it; wait for it to finish exiting.
    let _ = child.start_kill();
    let status = child.wait().await?;
    started?;
    eprintln!("silentdesk: the backend exited with {status}");
    Ok(())
}

async fn write_lines(mut stdin: ChildStdin, mut lines: mpsc::UnboundedReceiver<String>) {
    while let Some(line) = lines.recv().await {
        let written = async {
            stdin.write_all(line.as_bytes()).await?;
            stdin.write_all(b"\n").await?;
            stdin.flush().await
        };
        if written.await.is_err() {
            return;
        }
    }
}

/// Reads messages until the backend closes stdout.
async fn read_messages(app: AppHandle, connection: Arc<Connection>, stdout: ChildStdout) {
    let mut lines = BufReader::new(stdout).lines();
    while let Ok(Some(line)) = lines.next_line().await {
        let Ok(Value::Object(message)) = serde_json::from_str::<Value>(&line) else {
            eprintln!("silentdesk: ignoring a malformed message from the backend");
            continue;
        };
        let method = message
            .get("method")
            .and_then(Value::as_str)
            .map(str::to_owned);
        let params = message.get("params").cloned().unwrap_or(Value::Null);
        match (method, message.get("id").cloned()) {
            (None, _) => connection.resolve(&message),
            (Some(method), None) => host::notify(&app, &method, params),
            (Some(method), Some(id)) => {
                let app = app.clone();
                let connection = connection.clone();
                tokio::spawn(async move {
                    let response = match host::handle(&app, &method, params).await {
                        Ok(result) => json!({"id": id, "result": result}),
                        Err(e) => json!({
                            "id": id,
                            "error": {"kind": e.kind(), "message": e.to_string()},
                        }),
                    };
                    connection.send(response);
                });
            }
        }
    }
}

/// Every source token in the credential store, by name. They are read once
/// per start; Python asks Rust to save any change.
async fn stored_secrets() -> Result<Map<String, Value>> {
    let mut out = Map::new();
    for name in BACKEND_SECRETS {
        if let Some(value) = secrets::get(name).await?
            && let Ok(value) = String::from_utf8(value)
        {
            out.insert(name.into(), Value::String(value));
        }
    }
    Ok(out)
}

/// `python -m silentdesk`, run from the folder that holds the `silentdesk`
/// package:
///
/// - `SILENTDESK_BACKEND_DIR` and `SILENTDESK_PYTHON` override both;
/// - a release bundle ships them as the `backend` resource, with its own
///   Python in `backend/python`;
/// - a debug build uses `backend/` in the source tree and its `uv` virtual
///   environment.
fn command(app: &AppHandle) -> Result<Command> {
    let dir = backend_dir(app)?;
    let python = std::env::var_os("SILENTDESK_PYTHON")
        .map(PathBuf::from)
        .or_else(|| {
            let candidates = if cfg!(windows) {
                ["python/python.exe", ".venv/Scripts/python.exe"]
            } else {
                ["python/bin/python3", ".venv/bin/python"]
            };
            candidates.iter().map(|c| dir.join(c)).find(|p| p.is_file())
        })
        .unwrap_or_else(|| PathBuf::from("python3"));

    let mut command = Command::new(python);
    // -E and -s: ignore PYTHON* variables and the user's site-packages, so
    // only the bundled code runs. -u: unbuffered, so logs arrive in order.
    command
        .args(["-E", "-s", "-u", "-m", "silentdesk"])
        .current_dir(&dir)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::inherit())
        .kill_on_drop(true);
    Ok(command)
}

fn backend_dir(app: &AppHandle) -> Result<PathBuf> {
    let has_package = |dir: &PathBuf| dir.join("silentdesk").join("__main__.py").is_file();
    if let Some(dir) = std::env::var_os("SILENTDESK_BACKEND_DIR") {
        return Ok(PathBuf::from(dir));
    }
    if let Ok(resources) = app.path().resource_dir() {
        let dir = resources.join("backend");
        if has_package(&dir) {
            return Ok(dir);
        }
    }
    #[cfg(debug_assertions)]
    {
        let dir = PathBuf::from(concat!(env!("CARGO_MANIFEST_DIR"), "/../backend"));
        if has_package(&dir) {
            return Ok(dir);
        }
    }
    Err(Error::BackendDown(
        "its files are missing from this installation.".into(),
    ))
}
