export interface Task {
  id: string;
  title: string;
  done: boolean;
  /** ISO 8601 timestamp. */
  createdAt: string;
}

export type TaskFilter = "all" | "active" | "done";

export type Direction = "inbound" | "outbound";

/** One Gmail message, as stored by the backend. Headers only, no body. */
export interface GmailEmail {
  messageId: string;
  threadId: string;
  topicId: string;
  direction: Direction;
  from: string;
  to: string;
  subject: string;
  /** ISO 8601 timestamp. */
  date: string;
}

/** One Slack direct message, as stored by the backend. No message text. */
export interface SlackMessage {
  channelId: string;
  ts: string;
  topicId: string;
  direction: Direction;
  author: string;
  /** The other person, or "Group DM". */
  counterpart: string;
  permalink: string;
  /** ISO 8601 timestamp. */
  date: string;
}

export interface Topic {
  id: string;
  title: string;
  /** ISO 8601 timestamp. */
  createdAt: string;
  emails: GmailEmail[];
  slackMessages: SlackMessage[];
}

export type Service = "gmail" | "slack";

export interface ServiceStatus {
  /** The app has the client ID it needs to sign in. */
  configured: boolean;
  connected: boolean;
  /** The account as shown to the user. */
  account: string | null;
}
