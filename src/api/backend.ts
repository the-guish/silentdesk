import { invoke, isTauri } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import type { Service, ServiceStatus, Topic } from "../types";

/**
 * Calls into the Rust backend. Tokens and keys stay on the Rust side; the UI
 * only ever sees account status and topic data.
 */

/** False when the UI runs in a plain browser (`pnpm dev`). */
export const hasBackend = isTauri;

export const serviceStatus = (s: Service) => invoke<ServiceStatus>(`${s}_status`);
export const serviceConnect = (s: Service) => invoke<ServiceStatus>(`${s}_connect`);
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
export const gmailTrash = (messageId: string) => invoke<Topic[]>("gmail_trash", { messageId });
export const gmailReply = (messageId: string, body: string) =>
  invoke<void>("gmail_reply", { messageId, body });

/** Backend errors arrive as plain strings. */
export function errorMessage(err: unknown): string {
  if (typeof err === "string") return err;
  if (err instanceof Error) return err.message;
  return "Something went wrong.";
}
