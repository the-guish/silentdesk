export interface Task {
  id: string;
  title: string;
  done: boolean;
  /** ISO 8601 timestamp. */
  createdAt: string;
}

export type TaskFilter = "all" | "active" | "done";
