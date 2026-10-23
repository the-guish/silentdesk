import { useCallback, useEffect, useState } from "react";
import type { Task } from "../types";

/**
 * Persistence boundary for tasks.
 *
 * The UI only talks to `useTasks()`, which talks to a `TaskRepository`.
 * Today that is localStorage; a Tauri/SQLite-backed repository can implement
 * the same interface later without touching any component.
 */
export interface TaskRepository {
  load(): Task[];
  save(tasks: Task[]): void;
}

const STORAGE_KEY = "silentdesk.tasks.v1";

function isTask(value: unknown): value is Task {
  if (typeof value !== "object" || value === null) return false;
  const t = value as Record<string, unknown>;
  return (
    typeof t.id === "string" &&
    typeof t.title === "string" &&
    typeof t.done === "boolean" &&
    typeof t.createdAt === "string"
  );
}

export const localStorageRepository: TaskRepository = {
  load() {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (!raw) return [];
      const parsed: unknown = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed.filter(isTask) : [];
    } catch {
      return [];
    }
  },
  save(tasks) {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(tasks));
    } catch {
      // Storage unavailable or full; keep working in memory.
    }
  },
};

function newId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export function useTasks(repo: TaskRepository = localStorageRepository) {
  const [tasks, setTasks] = useState<Task[]>(() => repo.load());

  useEffect(() => {
    repo.save(tasks);
  }, [repo, tasks]);

  const addTask = useCallback((title: string) => {
    const trimmed = title.trim();
    if (!trimmed) return;
    const task: Task = {
      id: newId(),
      title: trimmed,
      done: false,
      createdAt: new Date().toISOString(),
    };
    setTasks((prev) => [task, ...prev]);
  }, []);

  const toggleTask = useCallback((id: string) => {
    setTasks((prev) => prev.map((t) => (t.id === id ? { ...t, done: !t.done } : t)));
  }, []);

  const deleteTask = useCallback((id: string) => {
    setTasks((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const clearDone = useCallback(() => {
    setTasks((prev) => prev.filter((t) => !t.done));
  }, []);

  return { tasks, addTask, toggleTask, deleteTask, clearDone };
}
