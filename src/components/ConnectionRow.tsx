import type { Service, ServiceStatus } from "../types";

export type Busy = "connect" | "sync" | "disconnect" | null;

const INFO: Record<Service, { name: string; envVar: string; doc: string; pitch: string }> = {
  gmail: {
    name: "Gmail",
    envVar: "SILENTDESK_GOOGLE_CLIENT_ID",
    doc: "docs/setup/gmail.md",
    pitch:
      "Pull your last 10 emails as topics. Reads sender, recipients, subject and date only, never message bodies.",
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
  onConnect: () => void;
  onSync: () => void;
  onDisconnect: () => void;
}

export function ConnectionRow({
  service,
  status,
  busy,
  error,
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
                {busy === "sync" ? "Syncing…" : "Sync"}
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
              {busy === "connect" ? "Waiting…" : busy === "sync" ? "Syncing…" : "Connect"}
            </button>
          )}
        </div>
      )}
    </section>
  );
}
