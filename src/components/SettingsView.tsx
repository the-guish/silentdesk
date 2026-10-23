import { useCallback, useEffect, useState } from "react";
import {
  errorMessage,
  hasBackend,
  onGmailSyncProgress,
  serviceConnect,
  serviceDisconnect,
  serviceStatus,
  serviceSync,
} from "../api/backend";
import type { SyncProgress } from "../api/backend";
import type { JiraConnectArgs, Service, ServiceStatus } from "../types";
import { ConnectionRow, type Busy } from "./ConnectionRow";
import { JiraConnectForm } from "./JiraConnectForm";

const SERVICES: Service[] = ["gmail", "slack", "jira"];

type PerService<T> = Record<Service, T>;

export function SettingsView() {
  const desktop = hasBackend();
  const [statuses, setStatuses] = useState<PerService<ServiceStatus | null>>({
    gmail: null,
    slack: null,
    jira: null,
  });
  const [busy, setBusy] = useState<PerService<Busy>>({ gmail: null, slack: null, jira: null });
  const [errors, setErrors] = useState<PerService<string | null>>({
    gmail: null,
    slack: null,
    jira: null,
  });
  const [loadError, setLoadError] = useState<string | null>(null);
  const [synced, setSynced] = useState<PerService<number | null>>({
    gmail: null,
    slack: null,
    jira: null,
  });
  const [jiraFormOpen, setJiraFormOpen] = useState(false);

  const setStatus = (s: Service, status: ServiceStatus) =>
    setStatuses((prev) => ({ ...prev, [s]: status }));

  const refresh = useCallback(async () => {
    const [gmail, slack, jira] = await Promise.all([
      serviceStatus("gmail"),
      serviceStatus("slack"),
      serviceStatus("jira"),
    ]);
    setStatuses({ gmail, slack, jira });
  }, []);

  useEffect(() => {
    if (!desktop) return;
    refresh().catch((e) => setLoadError(errorMessage(e)));
  }, [desktop, refresh]);

  const [gmailProgress, setGmailProgress] = useState<SyncProgress | null>(null);
  useEffect(() => {
    if (!desktop) return;
    const unlisten = onGmailSyncProgress(setGmailProgress);
    return () => {
      unlisten.then((stop) => stop());
    };
  }, [desktop]);

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
    const count = topics.filter((t) =>
      s === "gmail"
        ? t.emails.length > 0
        : s === "slack"
          ? t.slackMessages.length > 0
          : t.jiraIssues.length > 0,
    ).length;
    setSynced((prev) => ({ ...prev, [s]: count }));
  }

  const connect = (s: Service, args?: JiraConnectArgs) =>
    run(s, "connect", async () => {
      setStatus(s, await serviceConnect(s, args));
      if (s === "jira") setJiraFormOpen(false);
      setBusy((prev) => ({ ...prev, [s]: "sync" }));
      await pull(s);
    });

  const sync = (s: Service) => run(s, "sync", () => pull(s));

  const disconnect = (s: Service) =>
    run(s, "disconnect", async () => {
      setStatus(s, await serviceDisconnect(s));
    });

  return (
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
                busy={busy[s]}
                error={errors[s]}
                progress={
                  s === "gmail" && busy.gmail === "sync" && gmailProgress && gmailProgress.total > 0
                    ? `${gmailProgress.done.toLocaleString()} of ${gmailProgress.total.toLocaleString()}`
                    : null
                }
                onConnect={() => (s === "jira" ? setJiraFormOpen(true) : connect(s))}
                onSync={() => sync(s)}
                onDisconnect={() => disconnect(s)}
              >
                {s === "jira" && jiraFormOpen && !statuses.jira?.connected && (
                  <JiraConnectForm
                    busy={busy.jira !== null}
                    onSubmit={(args) => connect("jira", args)}
                    onCancel={() => setJiraFormOpen(false)}
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
  );
}
