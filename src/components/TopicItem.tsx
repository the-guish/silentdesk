import type { Topic } from "../types";

interface Props {
  topic: Topic;
}

export function TopicItem({ topic }: Props) {
  const email = topic.emails[0];
  const outbound = email?.direction === "outbound";

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
        {email && (
          <span className="topic__meta">
            {outbound ? `To ${formatAddresses(email.to)}` : formatAddresses(email.from)}
          </span>
        )}
      </div>
      {email && (
        <time className="topic__date" dateTime={email.date}>
          {formatDate(email.date)}
        </time>
      )}
    </li>
  );
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
