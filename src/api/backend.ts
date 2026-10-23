import { invoke, isTauri } from "@tauri-apps/api/core";
import type { GmailStatus, Topic } from "../types";

/**
 * Calls into the Rust backend. Tokens and keys stay on the Rust side; the UI
 * only ever sees account status and topic data.
 */

/** False when the UI runs in a plain browser (`pnpm dev`). */
export const hasBackend = isTauri;

export const gmailStatus = () => invoke<GmailStatus>("gmail_status");
export const gmailConnect = () => invoke<GmailStatus>("gmail_connect");
export const gmailSync = () => invoke<Topic[]>("gmail_sync");
export const gmailDisconnect = () => invoke<GmailStatus>("gmail_disconnect");
export const listTopics = () => invoke<Topic[]>("list_topics");

/** Backend errors arrive as plain strings. */
export function errorMessage(err: unknown): string {
  if (typeof err === "string") return err;
  if (err instanceof Error) return err.message;
  return "Something went wrong.";
}
