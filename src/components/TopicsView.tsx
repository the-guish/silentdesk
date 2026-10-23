import { useEffect, useMemo, useRef, useState } from "react";
import { errorMessage, gmailReply, gmailTrash, hasBackend, listTopics } from "../api/backend";
import type { Topic } from "../types";
import { TopicItem } from "./TopicItem";

/** Rows rendered at first, and added each time the list is scrolled to the end. */
const PAGE = 200;

interface Props {
  onOpenSettings: () => void;
}

export function TopicsView({ onOpenSettings }: Props) {
  const desktop = hasBackend();
  const [topics, setTopics] = useState<Topic[]>([]);
  const [query, setQuery] = useState("");
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (!desktop) return;
    listTopics()
      .then(setTopics)
      .catch((e) => setLoadError(errorMessage(e)));
  }, [desktop]);

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
  }, [more, shown]);

  return (
    <>
      <div className="toolbar">
        <form className="search" role="search" onSubmit={(e) => e.preventDefault()}>
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search topics"
            aria-label="Search topics"
          />
        </form>
        {loadError && (
          <p className="notice notice--error" role="alert">
            {loadError}
          </p>
        )}
      </div>

      <main className="content">
        {visible.length > 0 ? (
          <>
            <ul className="list">
              {visible.map((topic) => (
                <TopicItem
                  key={topic.id}
                  topic={topic}
                  onTrash={async (email) => setTopics(await gmailTrash(email.messageId))}
                  onReply={(email, body) => gmailReply(email.messageId, body)}
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
              No topics yet. Connect Gmail or Slack and sync them in{" "}
              <button type="button" className="link" onClick={onOpenSettings}>
                Settings
              </button>
              .
            </p>
          )
        )}
      </main>

      <footer className="footer">
        <span className="footer__count">
          {query.trim()
            ? `${matches.length.toLocaleString()} of ${topics.length.toLocaleString()} topics`
            : `${topics.length.toLocaleString()} ${topics.length === 1 ? "topic" : "topics"}`}
        </span>
      </footer>
    </>
  );
}

/** Everything a search matches against, lowercased. */
function searchText(topic: Topic): string {
  return [
    topic.title,
    ...topic.emails.flatMap((e) => [e.subject, e.from, e.to]),
    ...topic.slackMessages.flatMap((m) => [m.author, m.counterpart]),
  ]
    .join("\n")
    .toLowerCase();
}
