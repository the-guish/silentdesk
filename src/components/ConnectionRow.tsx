import type { Service, ServiceStatus } from "../types";

export type Busy = "connect" | "sync" | "disconnect" | null;

const INFO: Record<Service, { name: string; envVar: string; doc: string; pitch: string }> = {
  gmail: {
    name: "Gmail",
    envVar: "SILENTDESK_GOOGLE_CLIENT_ID",
    doc: "docs/setup/gmail.md",
    pitch:
      "Pull the subject of every email in your Inbox as a topic, reply to them and move them to the trash. Keeps the subject and date only.",
  },
  slack: {
    name: "Slack",
    envVar: "SILENTDESK_SLACK_CLIENT_ID",
    doc: "docs/setup/slack.md",
    pitch:
      "Pull your last 10 direct messages as topics. Keeps sender, time and a short preview only.",
  },
};

interface Props {
  service: Service;
  status: ServiceStatus | null;
  busy: Busy;
  error: string | null;
  /** Shown on the busy button while a sync runs, e.g. "1,200 of 9,800". */
  progress?: string | null;
  onConnect: () => void;
  onSync: () => void;
  onDisconnect: () => void;
}

export function ConnectionRow({
  service,
  status,
  busy,
  error,
  progress,
  onConnect,
  onSync,
  onDisconnect,
}: Props) {
  const info = INFO[service];

  return (
    <section className="connection" aria-label={`${info.name} connection`}>
      <div className="connection__body">
        <p className="connection__text">
          <strong>{info.name}</strong>
          {status === null ? (
            " · Loading…"
          ) : !status.configured ? (
            <>
              {" "}
              · Not set up. Set <code>{info.envVar}</code> in <code>.env</code>; see{" "}
              <code>{info.doc}</code>.
            </>
          ) : status.connected ? (
            <> · {status.account}</>
          ) : busy === "connect" ? (
            " · Finish signing in in your browser…"
          ) : (
            <> · {info.pitch}</>
          )}
        </p>
        {error && (
          <p className="notice notice--error" role="alert">
            {error}
          </p>
        )}
      </div>

      {status?.configured && (
        <div className="connection__actions">
          {status.connected ? (
            <>
              <button
                type="button"
                className="button button--primary"
                onClick={onSync}
                disabled={busy !== null}
              >
                {busy === "sync" ? `Syncing${progress ? ` ${progress}` : ""}…` : "Sync"}
              </button>
              <button
                type="button"
                className="button"
                onClick={onDisconnect}
                disabled={busy !== null}
              >
                {busy === "disconnect" ? "Disconnecting…" : "Disconnect"}
              </button>
            </>
          ) : (
            <button
              type="button"
              className="button button--primary"
              onClick={onConnect}
              disabled={busy !== null}
            >
              {busy === "connect" ? "Waiting…" : busy === "sync" ? `Syncing${progress ? ` ${progress}` : ""}…` : "Connect"}
            </button>
          )}
        </div>
      )}
    </section>
  );
}
