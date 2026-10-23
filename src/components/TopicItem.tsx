import { useState, type FormEvent } from "react";
import { errorMessage } from "../api/backend";
import type { GmailEmail, Topic } from "../types";

interface Props {
  topic: Topic;
  onTrash: (email: GmailEmail) => Promise<void>;
  onReply: (email: GmailEmail, body: string) => Promise<void>;
}

type Mode = "idle" | "confirm-trash" | "reply";
type Busy = "trash" | "reply" | null;

export function TopicItem({ topic, onTrash, onReply }: Props) {
  const source = describe(topic);
  const outbound = source?.direction === "outbound";
  const email = topic.emails[0];
  const [mode, setMode] = useState<Mode>("idle");
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState<Busy>(null);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  async function act(kind: Exclude<Busy, null>, action: () => Promise<void>) {
    setBusy(kind);
    setError(null);
    try {
      await action();
      return true;
    } catch (e) {
      setError(errorMessage(e));
      return false;
    } finally {
      setBusy(null);
    }
  }

  const trash = () => act("trash", () => onTrash(email));

  async function send(e: FormEvent) {
    e.preventDefault();
    if (!draft.trim()) return;
    if (await act("reply", () => onReply(email, draft))) {
      setDraft("");
      setMode("idle");
      setSent(true);
    }
  }

  function open(next: Mode) {
    setMode(next);
    setError(null);
    setSent(false);
  }

  return (
    <li className="topic">
      <span
        className={`topic__dir${outbound ? " topic__dir--out" : ""}`}
        role="img"
        aria-label={outbound ? "Sent" : "Received"}
        title={outbound ? "Sent" : "Received"}
      >
        <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
          <path
            d={outbound ? "M5 11l6-6M6 5h5v5" : "M11 5l-6 6M10 11H5V6"}
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
            fill="none"
          />
        </svg>
      </span>
      <div className="topic__main">
        <span className="topic__title">{topic.title}</span>
        {source && (
          <span className="topic__meta">
            <span className="topic__source">{source.name}</span>
            {source.who && <> · {source.who}</>}
          </span>
        )}
      </div>
      {source && (
        <time className="topic__date" dateTime={source.date}>
          {formatDate(source.date)}
        </time>
      )}
      {email && (
        <div className="topic__actions">
          {mode === "confirm-trash" ? (
            <>
              <button
                type="button"
                className="button button--danger"
                onClick={trash}
                disabled={busy !== null}
              >
                {busy === "trash" ? "Moving…" : "Move to trash"}
              </button>
              <button
                type="button"
                className="button"
                onClick={() => open("idle")}
                disabled={busy !== null}
              >
                Cancel
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                className="button"
                onClick={() => open(mode === "reply" ? "idle" : "reply")}
                disabled={busy !== null}
                aria-expanded={mode === "reply"}
              >
                Reply
              </button>
              <button
                type="button"
                className="button"
                onClick={() => open("confirm-trash")}
                disabled={busy !== null}
              >
                Trash
              </button>
            </>
          )}
        </div>
      )}
      {email && mode === "reply" && (
        <form className="topic__reply" onSubmit={send}>
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder={source?.who ? `Reply to ${source.who}` : "Reply"}
            aria-label="Reply"
            rows={4}
            autoFocus
            disabled={busy !== null}
          />
          <div className="topic__reply-actions">
            <button
              type="button"
              className="button"
              onClick={() => open("idle")}
              disabled={busy !== null}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="button button--primary"
              disabled={busy !== null || !draft.trim()}
            >
              {busy === "reply" ? "Sending…" : "Send"}
            </button>
          </div>
        </form>
      )}
      {error && (
        <p className="topic__notice notice notice--error" role="alert">
          {error}
        </p>
      )}
      {sent && (
        <p className="topic__notice notice" role="status">
          Reply sent.
        </p>
      )}
    </li>
  );
}

/** The topic's most recent source item, ready to display. */
function describe(topic: Topic) {
  const email = topic.emails[0];
  const slack = topic.slackMessages[0];
  if (email && (!slack || email.date >= slack.date)) {
    const outbound = email.direction === "outbound";
    const address = outbound ? email.to : email.from;
    // Inbox syncs keep the subject only.
    const who = !address ? null : outbound ? `To ${formatAddresses(address)}` : formatAddresses(address);
    return {
      name: "Gmail",
      direction: email.direction,
      who,
      date: email.date,
    };
  }
  if (slack) {
    const outbound = slack.direction === "outbound";
    const group = slack.counterpart === "Group DM";
    const who = outbound
      ? group
        ? "To group DM"
        : `To ${slack.counterpart}`
      : group
        ? `${slack.author} in group DM`
        : slack.author;
    return { name: "Slack", direction: slack.direction, who, date: slack.date };
  }
  return null;
}

/** `"Ana Ruiz" <ana@x.com>, bo@y.com` → `Ana Ruiz +1`. */
function formatAddresses(header: string): string {
  const parts = header.match(/(?:"[^"]*"|<[^>]*>|[^,])+/g)?.map((p) => p.trim()).filter(Boolean) ?? [];
  if (parts.length === 0) return "(unknown)";
  const named = parts[0].match(/^"?([^"<]*?)"?\s*<([^>]+)>$/);
  const first = named ? named[1].trim() || named[2] : parts[0];
  return parts.length > 1 ? `${first} +${parts.length - 1}` : first;
}

function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const now = new Date();
  if (date.toDateString() === now.toDateString()) {
    return date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  }
  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: date.getFullYear() === now.getFullYear() ? undefined : "numeric",
  });
}
