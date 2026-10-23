import { useCallback, useEffect, useState } from "react";
import {
  errorMessage,
  hasBackend,
  listTopics,
  serviceConnect,
  serviceDisconnect,
  serviceStatus,
  serviceSync,
} from "../api/backend";
import type { JiraConnectArgs, Service, ServiceStatus, Topic } from "../types";
import { ConnectionRow, type Busy } from "./ConnectionRow";
import { JiraConnectForm } from "./JiraConnectForm";
import { TopicItem } from "./TopicItem";

const SERVICES: Service[] = ["gmail", "slack", "jira"];

type PerService<T> = Record<Service, T>;

export function TopicsView() {
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
  const [jiraFormOpen, setJiraFormOpen] = useState(false);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  const setStatus = (s: Service, status: ServiceStatus) =>
    setStatuses((prev) => ({ ...prev, [s]: status }));

  const refresh = useCallback(async () => {
    const [gmail, slack, jira, t] = await Promise.all([
      serviceStatus("gmail"),
      serviceStatus("slack"),
      serviceStatus("jira"),
      listTopics(),
    ]);
    setStatuses({ gmail, slack, jira });
    setTopics(t);
  }, []);

  useEffect(() => {
    if (!desktop) return;
    refresh().catch((e) => setLoadError(errorMessage(e)));
  }, [desktop, refresh]);

  async function run(s: Service, kind: Exclude<Busy, null>, action: () => Promise<void>) {
    setBusy((prev) => ({ ...prev, [s]: kind }));
    setErrors((prev) => ({ ...prev, [s]: null }));
    try {
      await action();
    } catch (e) {
      setErrors((prev) => ({ ...prev, [s]: errorMessage(e) }));
      await refresh().catch(() => {});
    } finally {
      setBusy((prev) => ({ ...prev, [s]: null }));
    }
  }

  const connect = (s: Service, args?: JiraConnectArgs) =>
    run(s, "connect", async () => {
      setStatus(s, await serviceConnect(s, args));
      if (s === "jira") setJiraFormOpen(false);
      setBusy((prev) => ({ ...prev, [s]: "sync" }));
      setTopics(await serviceSync(s));
    });

  const sync = (s: Service) =>
    run(s, "sync", async () => {
      setTopics(await serviceSync(s));
    });

  const disconnect = (s: Service) =>
    run(s, "disconnect", async () => {
      setStatus(s, await serviceDisconnect(s));
      setTopics(await listTopics());
    });

  const anyConnected = SERVICES.some((s) => statuses[s]?.connected);

  return (
    <>
      <div className="toolbar">
        {!desktop ? (
          <section className="connection">
            <p className="connection__text">
              Connections are only available in the desktop app. Start it with{" "}
              <code>./dev.sh</code>.
            </p>
          </section>
        ) : (
          <div className="connections">
            {SERVICES.map((s) => (
              <ConnectionRow
                key={s}
                service={s}
                status={statuses[s]}
                busy={busy[s]}
                error={errors[s]}
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
            ))}
          </div>
        )}
        {loadError && (
          <p className="notice notice--error" role="alert">
            {loadError}
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
          anyConnected && (
            <p className="empty">No topics yet. Select Sync to pull your recent messages.</p>
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
