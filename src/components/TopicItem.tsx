import type { Topic } from "../types";

interface Props {
  topic: Topic;
}

export function TopicItem({ topic }: Props) {
  const source = describe(topic);
  const outbound = source?.direction === "outbound";

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
            <span className="topic__source">{source.name}</span> · {source.who}
          </span>
        )}
      </div>
      {source && (
        <time className="topic__date" dateTime={source.date}>
          {formatDate(source.date)}
        </time>
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
    return {
      name: "Gmail",
      direction: email.direction,
      who: outbound ? `To ${formatAddresses(email.to)}` : formatAddresses(email.from),
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
