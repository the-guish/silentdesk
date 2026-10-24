import { type ReactNode, useCallback, useEffect, useState } from "react";
import {
  errorMessage,
  hasBackend,
  onGmailSyncProgress,
  onSyncFinished,
  serviceConnect,
  serviceDisconnect,
  serviceStatus,
  serviceSync,
  subscribe,
} from "../api/backend";
import type { SyncProgress } from "../api/backend";
import type { Service, ServiceStatus, Topic } from "../types";
import { ConnectionRow, type Busy } from "./ConnectionRow";
import { TOKEN_FORMS, TokenConnectForm, type TokenService } from "./TokenConnectForm";

const SERVICES: Service[] = ["gmail", "tasks", "slack", "jira", "github"];

type PerService<T> = Record<Service, T>;

function perService<T>(value: T): PerService<T> {
  return Object.fromEntries(SERVICES.map((s) => [s, value])) as PerService<T>;
}

/** Whether a topic came from service `s`. */
const FROM: Record<Service, (t: Topic) => boolean> = {
  gmail: (t) => t.emails.length > 0,
  slack: (t) => t.slackMessages.length > 0,
  jira: (t) => t.jiraIssues.length > 0,
  github: (t) => t.pullRequests.length > 0,
  tasks: (t) => t.googleTasks.length > 0,
};

const isTokenService = (s: Service): s is TokenService => s in TOKEN_FORMS;

interface Props {
  /** Shown first in the footer: the Settings button. */
  footer: ReactNode;
}

export function SettingsView({ footer }: Props) {
  const desktop = hasBackend();
  const [statuses, setStatuses] = useState(perService<ServiceStatus | null>(null));
  const [busy, setBusy] = useState(perService<Busy>(null));
  const [errors, setErrors] = useState(perService<string | null>(null));
  const [loadError, setLoadError] = useState<string | null>(null);
  const [synced, setSynced] = useState(perService<number | null>(null));
  /** The token service whose sign-in form is open, if any. */
  const [form, setForm] = useState<TokenService | null>(null);

  const setStatus = (s: Service, status: ServiceStatus) =>
    setStatuses((prev) => ({ ...prev, [s]: status }));

  const refresh = useCallback(async () => {
    const all = await Promise.all(SERVICES.map(serviceStatus));
    setStatuses(Object.fromEntries(SERVICES.map((s, i) => [s, all[i]])) as PerService<ServiceStatus>);
  }, []);

  useEffect(() => {
    if (!desktop) return;
    refresh().catch((e) => setLoadError(errorMessage(e)));
  }, [desktop, refresh]);

  const [gmailProgress, setGmailProgress] = useState<SyncProgress | null>(null);
  useEffect(() => {
    if (!desktop) return;
    return subscribe(onGmailSyncProgress(setGmailProgress));
  }, [desktop]);

  // Automatic syncs report here, and their errors show on the service's row.
  useEffect(() => {
    if (!desktop) return;
    return subscribe(
      onSyncFinished((s, error) => {
        setErrors((prev) => ({ ...prev, [s]: error }));
        if (s === "gmail") setGmailProgress(null);
        if (error) refresh().catch(() => {});
      }),
    );
  }, [desktop, refresh]);

  /** A Gmail sync is reading messages, started by the user or automatically. */
  const gmailReading =
    gmailProgress !== null && gmailProgress.total > 0 && gmailProgress.done < gmailProgress.total;

  async function run(s: Service, kind: Exclude<Busy, null>, action: () => Promise<void>) {
    setBusy((prev) => ({ ...prev, [s]: kind }));
    setErrors((prev) => ({ ...prev, [s]: null }));
    setSynced((prev) => ({ ...prev, [s]: null }));
    try {
      await action();
    } catch (e) {
      setErrors((prev) => ({ ...prev, [s]: errorMessage(e) }));
      await refresh().catch(() => {});
    } finally {
      setBusy((prev) => ({ ...prev, [s]: null }));
      if (s === "gmail") setGmailProgress(null);
    }
  }

  async function pull(s: Service) {
    const topics = await serviceSync(s);
    const count = topics.filter(FROM[s]).length;
    setSynced((prev) => ({ ...prev, [s]: count }));
  }

  const connect = (s: Service, args?: Record<string, string | null>) =>
    run(s, "connect", async () => {
      setStatus(s, await serviceConnect(s, args));
      if (form === s) setForm(null);
      setBusy((prev) => ({ ...prev, [s]: "sync" }));
      await pull(s);
    });

  const sync = (s: Service) => run(s, "sync", () => pull(s));

  const disconnect = (s: Service) =>
    run(s, "disconnect", async () => {
      setStatus(s, await serviceDisconnect(s));
    });

  return (
    <>
      <main className="content settings">
        <h2 className="settings__heading">Connections</h2>
        {!desktop ? (
          <p className="connection__text">
            Connections are only available in the desktop app. Start it with <code>./dev.sh</code>.
          </p>
        ) : (
          <div className="connections">
            {SERVICES.map((s) => (
              <div key={s}>
                <ConnectionRow
                  service={s}
                  status={statuses[s]}
                  busy={busy[s] ?? (s === "gmail" && gmailReading ? "sync" : null)}
                  error={errors[s]}
                  progress={
                    s === "gmail" && gmailReading
                      ? `${gmailProgress.done.toLocaleString()} of ${gmailProgress.total.toLocaleString()}`
                      : null
                  }
                  onConnect={() => (isTokenService(s) ? setForm(s) : connect(s))}
                  onSync={() => sync(s)}
                  onDisconnect={() => disconnect(s)}
                >
                  {isTokenService(s) && form === s && !statuses[s]?.connected && (
                    <TokenConnectForm
                      {...TOKEN_FORMS[s]}
                      busy={busy[s] !== null}
                      onSubmit={(values) => connect(s, values)}
                      onCancel={() => setForm(null)}
                    />
                  )}
                </ConnectionRow>
                {synced[s] !== null && (
                  <p className="notice settings__synced" role="status">
                    Synced. {synced[s]} {synced[s] === 1 ? "topic" : "topics"} in Topics.
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
        {loadError && (
          <p className="notice notice--error" role="alert">
            {loadError}
          </p>
        )}
      </main>
      <footer className="footer">{footer}</footer>
    </>
  );
}
