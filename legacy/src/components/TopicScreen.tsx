import { type ReactNode, useEffect, useState } from "react";
import { errorMessage, slackHistory } from "../api/backend";
import type { ConversationMessage, Topic } from "../types";
import { DirectionIcon, describeItems, formatDate } from "./TopicItem";

interface Props {
  /** `null` once a sync removed the topic. */
  topic: Topic | null;
  /** Shown first in the footer: the Settings button. */
  footer: ReactNode;
  onBack: () => void;
}

type History =
  | { state: "loading" }
  | { state: "loaded"; messages: ConversationMessage[] }
  | { state: "failed"; error: string };

/** One topic: its messages, then its other source items. */
export function TopicScreen({ topic, footer, onBack }: Props) {
  const slack = topic?.slackMessages ?? [];
  const [history, setHistory] = useState<History>({ state: "loading" });

  // Read again when a sync brings a newer message into the conversation.
  const newest = slack[0]?.ts ?? null;
  const topicId = topic?.id ?? null;
  useEffect(() => {
    if (topicId === null || newest === null) return;
    let current = true;
    setHistory((h) => (h.state === "loaded" ? h : { state: "loading" }));
    slackHistory(topicId)
      .then((messages) => current && setHistory({ state: "loaded", messages }))
      .catch((e) => current && setHistory({ state: "failed", error: errorMessage(e) }));
    return () => {
      current = false;
    };
  }, [topicId, newest]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onBack();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onBack]);

  const items = topic ? describeItems(topic) : [];
  // Slack messages show as the conversation, unless it could not be read.
  const rows = history.state === "failed" ? items : items.filter((i) => i.name !== "Slack");

  return (
    <>
      <div className="toolbar topic-screen__bar">
        <button type="button" className="button" onClick={onBack} title="Back (Esc)">
          ← Topics
        </button>
        <h1 className="topic-screen__title">{topic?.title ?? "Topic removed"}</h1>
      </div>

      <main className="content">
        {topic === null ? (
          <p className="empty">A sync removed this topic.</p>
        ) : (
          <>
            {slack.length > 0 && (
              <section className="conversation" aria-label="Slack conversation">
                {history.state === "loading" && <p className="empty">Loading messages…</p>}
                {history.state === "failed" && (
                  <p className="notice notice--error" role="alert">
                    {history.error}
                  </p>
                )}
                {history.state === "loaded" &&
                  (history.messages.length === 0 ? (
                    <p className="empty">No messages in this conversation.</p>
                  ) : (
                    <ol className="list">
                      {history.messages.map((m) => (
                        <li
                          key={m.ts}
                          className={`message${m.direction === "outbound" ? " message--out" : ""}`}
                        >
                          <div className="message__head">
                            <span className="message__author">{m.author}</span>
                            <time className="topic__date" dateTime={m.date}>
                              {formatDate(m.date)}
                            </time>
                          </div>
                          <p className="message__text">{m.text || "(empty message)"}</p>
                        </li>
                      ))}
                    </ol>
                  ))}
              </section>
            )}

            {rows.length > 0 && (
              <ul className="list">
                {rows.map((item) => (
                  <li key={item.key} className="topic">
                    <DirectionIcon direction={item.direction} />
                    <span className="topic__main">
                      <span className="topic__title">{item.name}</span>
                      {item.who && <span className="topic__meta">{item.who}</span>}
                    </span>
                    <time className="topic__date" dateTime={item.date}>
                      {formatDate(item.date)}
                    </time>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </main>

      <footer className="footer">
        {footer}
        <span className="footer__count">
          {slack.length > 0 && history.state === "loaded"
            ? `${history.messages.length} ${history.messages.length === 1 ? "message" : "messages"}`
            : null}
        </span>
      </footer>
    </>
  );
}
