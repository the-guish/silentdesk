import { invoke, isTauri } from "@tauri-apps/api/core";
import type { InvokeArgs } from "@tauri-apps/api/core";
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

/** Backend errors arrive as plain strings. */
export function errorMessage(err: unknown): string {
  if (typeof err === "string") return err;
  if (err instanceof Error) return err.message;
  return "Something went wrong.";
}
