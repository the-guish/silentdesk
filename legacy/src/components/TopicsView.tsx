import { type ReactNode, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  errorMessage,
  gmailReply,
  gmailTrash,
  hasBackend,
  lastSynced,
  listTopics,
  onSyncRound,
  onTopicsUpdated,
  refresh,
  subscribe,
  syncRunning,
} from "../api/backend";
import type { Topic } from "../types";
import { TopicItem } from "./TopicItem";
import { TopicScreen } from "./TopicScreen";

/** Rows rendered at first, and added each time the list is scrolled to the end. */
const PAGE = 200;

interface Props {
  /** Shown first in the footer: the Settings button. */
  footer: ReactNode;
  onOpenSettings: () => void;
}

export function TopicsView({ footer, onOpenSettings }: Props) {
  const desktop = hasBackend();
  const [topics, setTopics] = useState<Topic[]>([]);
  const [query, setQuery] = useState("");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);

  useEffect(() => {
    if (!desktop) return;
    listTopics()
      .then(setTopics)
      .catch((e) => setLoadError(errorMessage(e)));
    lastSynced()
      .then((at) => setUpdatedAt((prev) => prev ?? at))
      .catch(() => {});
    return subscribe(
      onTopicsUpdated((at) => {
        setUpdatedAt(at);
        listTopics()
          .then(setTopics)
          .catch(() => {});
      }),
    );
  }, [desktop]);

  const [refreshing, setRefreshing] = useState(false);
  useEffect(() => {
    if (!desktop) return;
    syncRunning()
      .then(setRefreshing)
      .catch(() => {});
    return subscribe(onSyncRound(setRefreshing));
  }, [desktop]);

  function startRefresh() {
    setRefreshing(true);
    refresh().catch(() => setRefreshing(false));
  }

  // Re-render the "Updated … ago" label every 30 seconds.
  const [, setTick] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setTick((n) => n + 1), 30_000);
    return () => clearInterval(timer);
  }, []);

  const matches = useMemo(() => {
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    if (words.length === 0) return topics;
    return topics.filter((t) => {
      const text = searchText(t);
      return words.every((w) => text.includes(w));
    });
  }, [topics, query]);

  const [shown, setShown] = useState(PAGE);
  useEffect(() => setShown(PAGE), [query]);
  const visible = matches.slice(0, shown);

  // The open topic's screen replaces the list; the list keeps its place.
  const [openId, setOpenId] = useState<string | null>(null);
  const list = useRef<HTMLElement>(null);
  const scroll = useRef(0);
  function openTopic(id: string) {
    scroll.current = list.current?.scrollTop ?? 0;
    setOpenId(id);
  }
  useLayoutEffect(() => {
    if (openId === null && list.current) list.current.scrollTop = scroll.current;
  }, [openId]);

  const end = useRef<HTMLDivElement>(null);
  const more = matches.length > shown;
  useEffect(() => {
    if (!more || !end.current) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) setShown((n) => n + PAGE);
      },
      { rootMargin: "400px" },
    );
    observer.observe(end.current);
    return () => observer.disconnect();
  }, [more, shown, openId]);

  if (openId !== null) {
    return (
      <TopicScreen
        key={openId}
        topic={topics.find((t) => t.id === openId) ?? null}
        footer={footer}
        onBack={() => setOpenId(null)}
      />
    );
  }

  return (
    <>
      <div className="toolbar">
        <div className="search-row">
          <form className="search" role="search" onSubmit={(e) => e.preventDefault()}>
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search topics"
              aria-label="Search topics"
            />
          </form>
          {desktop && (
            <button
              type="button"
              className="button search-row__refresh"
              onClick={startRefresh}
              disabled={refreshing}
            >
              {refreshing ? "Refreshing…" : "Refresh"}
            </button>
          )}
        </div>
        {loadError && (
          <p className="notice notice--error" role="alert">
            {loadError}
          </p>
        )}
      </div>

      <main className="content" ref={list}>
        {visible.length > 0 ? (
          <>
            <ul className="list">
              {visible.map((topic) => (
                <TopicItem
                  key={topic.id}
                  topic={topic}
                  onTrash={async (email) => setTopics(await gmailTrash(email.messageId))}
                  onReply={(email, body) => gmailReply(email.messageId, body)}
                  onOpen={() => openTopic(topic.id)}
                />
              ))}
            </ul>
            {more && <div ref={end} className="list__more" aria-hidden="true" />}
          </>
        ) : topics.length > 0 ? (
          <p className="empty">No topics match your search.</p>
        ) : (
          desktop && (
            <p className="empty">
              No topics yet. Connect Gmail, Google Tasks, Slack, Jira or GitHub and sync them in{" "}
              <button type="button" className="link" onClick={onOpenSettings}>
                Settings
              </button>
              .
            </p>
          )
        )}
      </main>

      <footer className="footer">
        {footer}
        <span className="footer__count">
          {query.trim()
            ? `${matches.length.toLocaleString()} of ${topics.length.toLocaleString()} topics`
            : `${topics.length.toLocaleString()} ${topics.length === 1 ? "topic" : "topics"}`}
        </span>
        {updatedAt && <span className="footer__updated">Updated {ago(updatedAt)}</span>}
      </footer>
    </>
  );
}

/** `"just now"`, `"5 min ago"`, `"2 h ago"`. */
function ago(iso: string): string {
  const minutes = Math.floor((Date.now() - new Date(iso).getTime()) / 60_000);
  if (Number.isNaN(minutes) || minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  return `${Math.floor(minutes / 60)} h ago`;
}

/** Everything a search matches against, lowercased. */
function searchText(topic: Topic): string {
  return [
    topic.title,
    ...topic.emails.flatMap((e) => [e.subject, e.from, e.to]),
    ...topic.slackMessages.flatMap((m) => [m.author, m.counterpart]),
    ...topic.jiraIssues.flatMap((i) => [i.key, i.status, i.assignee, i.reporter]),
    ...topic.pullRequests.flatMap((p) => [`${p.repo}#${p.number}`, p.author]),
    ...topic.googleTasks.flatMap((t) => [t.listTitle, t.origin ?? ""]),
  ]
    .join("\n")
    .toLowerCase();
}
