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

export interface Topic {
  id: string;
  title: string;
  /** ISO 8601 timestamp. */
  createdAt: string;
  emails: GmailEmail[];
}

export interface GmailStatus {
  /** An OAuth client ID is available to the app. */
  configured: boolean;
  connected: boolean;
  email: string | null;
}
