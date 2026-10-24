import { type FormEvent, type ReactNode, useEffect, useState } from "react";
import { errorMessage, gmailReply, gmailThread, slackHistory } from "../api/backend";
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

/** Sources whose messages the screen reads live, named as in `describeItems`. */
type Name = "Slack" | "Gmail";
const NAMES: Name[] = ["Slack", "Gmail"];

/**
 * Reads one source's messages for the topic, and reads them again when
 * `version` changes, i.e. when a sync brings a newer message. `null` when
 * the topic has nothing from that source.
 */
function useConversation(
  topicId: string | null,
  version: string | null,
  load: (topicId: string) => Promise<ConversationMessage[]>,
): History | null {
  const [history, setHistory] = useState<History>({ state: "loading" });
  useEffect(() => {
    if (topicId === null || version === null) return;
    let current = true;
    setHistory((h) => (h.state === "loaded" ? h : { state: "loading" }));
    load(topicId)
      .then((messages) => current && setHistory({ state: "loaded", messages }))
      .catch((e) => current && setHistory({ state: "failed", error: errorMessage(e) }));
    return () => {
      current = false;
    };
  }, [topicId, version, load]);
  return version === null ? null : history;
}

/** One topic: its messages, then its other source items. */
export function TopicScreen({ topic, footer, onBack }: Props) {
  const topicId = topic?.id ?? null;
  const slack = topic?.slackMessages ?? [];
  const emails = topic?.emails ?? [];
  // Counts sent replies, so the thread is read again with them in it.
  const [replies, setReplies] = useState(0);
  const histories: Record<Name, History | null> = {
    Slack: useConversation(topicId, slack.length ? `${slack.length}:${slack[0].ts}` : null, slackHistory),
    Gmail: useConversation(
      topicId,
      emails.length ? `${emails.length}:${emails[0].messageId}:${replies}` : null,
      gmailThread,
    ),
  };

  // Replies answer the thread's newest email.
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [replyError, setReplyError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  async function send(e: FormEvent) {
    e.preventDefault();
    if (!draft.trim() || emails.length === 0) return;
    setSending(true);
    setReplyError(null);
    setSent(false);
    try {
      await gmailReply(emails[0].messageId, draft);
      setDraft("");
      setSent(true);
      setReplies((n) => n + 1);
    } catch (err) {
      setReplyError(errorMessage(err));
    } finally {
      setSending(false);
    }
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // Esc in the reply box keeps the draft.
      if (e.key === "Escape" && !(e.target instanceof HTMLTextAreaElement)) onBack();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onBack]);

  const active = NAMES.filter((n) => histories[n] !== null);
  const loading = active.some((n) => histories[n]?.state === "loading");
  const failures: { name: Name; error: string }[] = [];
  const messages: (ConversationMessage & { key: string })[] = [];
  for (const name of active) {
    const h = histories[name];
    if (h?.state === "failed") failures.push({ name, error: h.error });
    if (h?.state === "loaded") messages.push(...h.messages.map((m) => ({ ...m, key: `${name}:${m.id}` })));
  }
  messages.sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));

  // Messages show as the conversation, unless it could not be read.
  const read = new Set<string>(active.filter((n) => histories[n]?.state !== "failed"));
  const rows = topic ? describeItems(topic).filter((i) => !read.has(i.name)) : [];
  const gmail = histories.Gmail;
  const sender =
    gmail?.state === "loaded"
      ? [...gmail.messages].reverse().find((m) => m.direction === "inbound")?.author
      : undefined;

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
            {active.length > 0 && (
              <section className="conversation" aria-label="Messages">
                {failures.map((f) => (
                  <p key={f.name} className="notice notice--error" role="alert">
                    {f.error}
                  </p>
                ))}
                {messages.length > 0 ? (
                  <ol className="list">
                    {messages.map((m) => (
                      <li key={m.key} className={`message${m.direction === "outbound" ? " message--out" : ""}`}>
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
                ) : loading ? (
                  <p className="empty">Loading messages…</p>
                ) : (
                  failures.length === 0 && <p className="empty">No messages in this conversation.</p>
                )}
              </section>
            )}

            {emails.length > 0 && (
              <form className="reply-box" onSubmit={send}>
                <textarea
                  value={draft}
                  onChange={(e) => {
                    setDraft(e.target.value);
                    setSent(false);
                  }}
                  placeholder={sender ? `Reply to ${sender}` : "Reply"}
                  aria-label="Reply"
                  rows={4}
                  disabled={sending}
                />
                <div className="reply-box__actions">
                  {replyError && (
                    <p className="notice notice--error" role="alert">
                      {replyError}
                    </p>
                  )}
                  {sent && (
                    <p className="notice" role="status">
                      Reply sent.
                    </p>
                  )}
                  <button type="submit" className="button button--primary" disabled={sending || !draft.trim()}>
                    {sending ? "Sending…" : "Send"}
                  </button>
                </div>
              </form>
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
          {messages.length > 0 && `${messages.length} ${messages.length === 1 ? "message" : "messages"}`}
        </span>
      </footer>
    </>
  );
}
