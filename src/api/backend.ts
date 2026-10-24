import { invoke, isTauri } from "@tauri-apps/api/core";
import type { InvokeArgs } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import type { Service, ServiceStatus, Topic } from "../types";

/**
 * Calls into the Rust backend. Tokens and keys stay on the Rust side; the UI
 * only ever sees account status and topic data.
 */

/** False when the UI runs in a plain browser (`pnpm dev`). */
export const hasBackend = isTauri;

export const serviceStatus = (s: Service) => invoke<ServiceStatus>(`${s}_status`);
/** Gmail and Slack sign in through the browser; Jira takes a token in `args`. */
export const serviceConnect = (s: Service, args?: InvokeArgs) =>
  invoke<ServiceStatus>(`${s}_connect`, args);
export const serviceSync = (s: Service) => invoke<Topic[]>(`${s}_sync`);
export const serviceDisconnect = (s: Service) => invoke<ServiceStatus>(`${s}_disconnect`);
export const listTopics = () => invoke<Topic[]>("list_topics");
/** Messages read so far by a running Gmail sync. */
export interface SyncProgress {
  done: number;
  total: number;
}

export const onGmailSyncProgress = (handler: (p: SyncProgress) => void): Promise<UnlistenFn> =>
  listen<SyncProgress>("gmail-sync-progress", (e) => handler(e.payload));
/** Asks the backend for an automatic sync round now, unless one just ran. */
export const syncSoon = () => invoke<void>("sync_soon");
/** Syncs every connected service now, unless a round is running. */
export const refresh = () => invoke<void>("refresh");
/** Whether a sync round is running now. */
export const syncRunning = () => invoke<boolean>("sync_running");
/** A sync round started (`true`) or ended (`false`). */
export const onSyncRound = (handler: (running: boolean) => void): Promise<UnlistenFn> =>
  listen<{ running: boolean }>("sync-round", (e) => handler(e.payload.running));
/** When the last automatic round finished (RFC 3339), if one has. */
export const lastSynced = () => invoke<string | null>("last_synced");
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

export const gmailTrash = (messageId: string) => invoke<Topic[]>("gmail_trash", { messageId });
export const gmailReply = (messageId: string, body: string) =>
  invoke<void>("gmail_reply", { messageId, body });

/** Backend errors arrive as plain strings. */
export function errorMessage(err: unknown): string {
  if (typeof err === "string") return err;
  if (err instanceof Error) return err.message;
  return "Something went wrong.";
}
