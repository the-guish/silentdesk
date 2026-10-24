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

/** One Jira issue, as stored by the backend. No description or comments. */
export interface JiraIssue {
  issueId: string;
  key: string;
  topicId: string;
  /** Inbound when assigned to the user; outbound when the user reported it. */
  direction: Direction;
  status: string;
  project: string;
  assignee: string;
  reporter: string;
  url: string;
  /** ISO 8601 timestamp of the last update. */
  date: string;
}

/** One GitHub pull request, as stored by the backend. No description or diff. */
export interface PullRequest {
  prId: number;
  /** `owner/name`. */
  repo: string;
  number: number;
  topicId: string;
  reason: "reviewRequested" | "assigned" | "authored";
  /** Inbound when the user's review or work is asked for; outbound when they opened it. */
  direction: Direction;
  draft: boolean;
  author: string;
  url: string;
  /** ISO 8601 timestamp of the last update. */
  date: string;
}

export interface Topic {
  id: string;
  title: string;
  /** ISO 8601 timestamp. */
  createdAt: string;
  emails: GmailEmail[];
  slackMessages: SlackMessage[];
  jiraIssues: JiraIssue[];
  pullRequests: PullRequest[];
}

export type Service = "gmail" | "slack" | "jira" | "github";

export interface ServiceStatus {
  /** The app has the client ID it needs to sign in. */
  configured: boolean;
  connected: boolean;
  /** The account as shown to the user. */
  account: string | null;
}
