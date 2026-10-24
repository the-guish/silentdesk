import { invoke, isTauri } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import type { ConversationMessage, Service, ServiceStatus, Topic } from "../types";

/**
 * Calls into the backend: Rust relays each call to the Python backend, which
 * runs the sources. Tokens and keys never reach the UI; it only ever sees
 * account status and topic data.
 */

/** False when the UI runs in a plain browser (`pnpm dev`). */
export const hasBackend = isTauri;

type Params = Record<string, unknown>;

/** Calls `method` (e.g. `jira.sync`) on the backend. */
const call = <T>(method: string, params?: Params) => invoke<T>("call", { method, params });

export const serviceStatus = (s: Service) => call<ServiceStatus>(`${s}.status`);
/** Gmail and Slack sign in through the browser; Jira takes a token in `params`. */
export const serviceConnect = (s: Service, params?: Params) =>
  call<ServiceStatus>(`${s}.connect`, params);
export const serviceSync = (s: Service) => call<Topic[]>(`${s}.sync`);
export const serviceDisconnect = (s: Service) => call<ServiceStatus>(`${s}.disconnect`);
export const listTopics = () => call<Topic[]>("topics.list");
/** Messages read so far by a running Gmail sync. */
export interface SyncProgress {
  done: number;
  total: number;
}

export const onGmailSyncProgress = (handler: (p: SyncProgress) => void): Promise<UnlistenFn> =>
  listen<SyncProgress>("gmail-sync-progress", (e) => handler(e.payload));
/** Asks the backend for an automatic sync round now, unless one just ran. */
export const syncSoon = () => call<void>("sync.soon");
/** Syncs every connected service now, unless a round is running. */
export const refresh = () => call<void>("sync.refresh");
/** Whether a sync round is running now. */
export const syncRunning = () => call<boolean>("sync.running");
/** A sync round started (`true`) or ended (`false`). */
export const onSyncRound = (handler: (running: boolean) => void): Promise<UnlistenFn> =>
  listen<{ running: boolean }>("sync-round", (e) => handler(e.payload.running));
/** When the last automatic round finished (RFC 3339), if one has. */
export const lastSynced = () => call<string | null>("sync.lastSynced");
/** An automatic sync changed topics; `at` is when (RFC 3339). */
export const onTopicsUpdated = (handler: (at: string) => void): Promise<UnlistenFn> =>
  listen<{ at: string }>("topics-updated", (e) => handler(e.payload.at));
/** An automatic sync of `service` finished; `error` is null on success. */
export const onSyncFinished = (
  handler: (service: Service, error: string | null) => void,
): Promise<UnlistenFn> =>
  listen<{ service: Service; error: string | null }>("sync-finished", (e) =>
    handler(e.payload.service, e.payload.error),
  );

/** Subscribes in an effect; returns the cleanup. */
export function subscribe(listening: Promise<UnlistenFn>): () => void {
  return () => {
    listening.then((stop) => stop());
  };
}

export const gmailTrash = (messageId: string) => call<Topic[]>("gmail.trash", { messageId });
export const gmailReply = (messageId: string, body: string) =>
  call<void>("gmail.reply", { messageId, body });

/** The recent messages of a topic's Slack conversation, oldest first, read live from Slack. */
export const slackHistory = (topicId: string) =>
  call<ConversationMessage[]>("slack.history", { topicId });

/** Backend errors arrive as plain strings. */
export function errorMessage(err: unknown): string {
  if (typeof err === "string") return err;
  if (err instanceof Error) return err.message;
  return "Something went wrong.";
}
