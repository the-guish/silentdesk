import { useCallback, useEffect, useState } from "react";
import {
  errorMessage,
  gmailConnect,
  gmailDisconnect,
  gmailStatus,
  gmailSync,
  hasBackend,
  listTopics,
} from "../api/backend";
import type { GmailStatus, Topic } from "../types";
import { TopicItem } from "./TopicItem";

type Busy = "connect" | "sync" | "disconnect" | null;

export function TopicsView() {
  const desktop = hasBackend();
  const [status, setStatus] = useState<GmailStatus | null>(null);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [busy, setBusy] = useState<Busy>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [s, t] = await Promise.all([gmailStatus(), listTopics()]);
    setStatus(s);
    setTopics(t);
  }, []);

  useEffect(() => {
    if (!desktop) return;
    refresh().catch((e) => setError(errorMessage(e)));
  }, [desktop, refresh]);

  async function run(kind: Exclude<Busy, null>, action: () => Promise<void>) {
    setBusy(kind);
    setError(null);
    try {
      await action();
    } catch (e) {
      setError(errorMessage(e));
      await refresh().catch(() => {});
    } finally {
      setBusy(null);
    }
  }

  const connect = () =>
    run("connect", async () => {
      setStatus(await gmailConnect());
      setBusy("sync");
      setTopics(await gmailSync());
    });

  const sync = () =>
    run("sync", async () => {
      setTopics(await gmailSync());
    });

  const disconnect = () =>
    run("disconnect", async () => {
      setStatus(await gmailDisconnect());
      setTopics(await listTopics());
    });

  return (
    <>
      <div className="toolbar">
        <section className="connection" aria-label="Gmail connection">
          {!desktop ? (
            <p className="connection__text">
              Gmail is only available in the desktop app. Start it with{" "}
              <code>pnpm tauri dev</code>.
            </p>
          ) : status === null ? (
            <p className="connection__text">Loading…</p>
          ) : !status.configured ? (
            <p className="connection__text">
              Gmail is not set up. Set <code>SILENTDESK_GOOGLE_CLIENT_ID</code> and
              restart. See <code>docs/setup/gmail.md</code>.
            </p>
          ) : status.connected ? (
            <>
              <p className="connection__text">
                <strong>Gmail</strong> · {status.email}
              </p>
              <div className="connection__actions">
                <button
                  type="button"
                  className="button button--primary"
                  onClick={sync}
                  disabled={busy !== null}
                >
                  {busy === "sync" ? "Syncing…" : "Sync"}
                </button>
                <button
                  type="button"
                  className="button"
                  onClick={disconnect}
                  disabled={busy !== null}
                >
                  {busy === "disconnect" ? "Disconnecting…" : "Disconnect"}
                </button>
              </div>
            </>
          ) : (
            <>
              <p className="connection__text">
                {busy === "connect"
                  ? "Finish signing in in your browser…"
                  : "Connect Gmail to pull your recent emails as topics. SilentDesk reads sender, recipients, subject and date only, never message bodies."}
              </p>
              <div className="connection__actions">
                <button
                  type="button"
                  className="button button--primary"
                  onClick={connect}
                  disabled={busy !== null}
                >
                  {busy === "connect"
                    ? "Waiting…"
                    : busy === "sync"
                      ? "Syncing…"
                      : "Connect Gmail"}
                </button>
              </div>
            </>
          )}
        </section>
        {error && (
          <p className="notice notice--error" role="alert">
            {error}
          </p>
        )}
      </div>

      <main className="content">
        {topics.length > 0 ? (
          <ul className="list">
            {topics.map((topic) => (
              <TopicItem key={topic.id} topic={topic} />
            ))}
          </ul>
        ) : (
          desktop &&
          status?.connected && (
            <p className="empty">No topics yet. Select Sync to pull your last 10 emails.</p>
          )
        )}
      </main>

      <footer className="footer">
        <span className="footer__count">
          {topics.length} {topics.length === 1 ? "topic" : "topics"}
        </span>
      </footer>
    </>
  );
}
