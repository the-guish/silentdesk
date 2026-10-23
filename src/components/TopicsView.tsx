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
import type { Service, ServiceStatus, Topic } from "../types";
import { ConnectionRow, type Busy } from "./ConnectionRow";
import { TopicItem } from "./TopicItem";

const SERVICES: Service[] = ["gmail", "slack"];

type PerService<T> = Record<Service, T>;

export function TopicsView() {
  const desktop = hasBackend();
  const [statuses, setStatuses] = useState<PerService<ServiceStatus | null>>({
    gmail: null,
    slack: null,
  });
  const [busy, setBusy] = useState<PerService<Busy>>({ gmail: null, slack: null });
  const [errors, setErrors] = useState<PerService<string | null>>({
    gmail: null,
    slack: null,
  });
  const [topics, setTopics] = useState<Topic[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  const setStatus = (s: Service, status: ServiceStatus) =>
    setStatuses((prev) => ({ ...prev, [s]: status }));

  const refresh = useCallback(async () => {
    const [gmail, slack, t] = await Promise.all([
      serviceStatus("gmail"),
      serviceStatus("slack"),
      listTopics(),
    ]);
    setStatuses({ gmail, slack });
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

  const connect = (s: Service) =>
    run(s, "connect", async () => {
      setStatus(s, await serviceConnect(s));
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
                onConnect={() => connect(s)}
                onSync={() => sync(s)}
                onDisconnect={() => disconnect(s)}
              />
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
