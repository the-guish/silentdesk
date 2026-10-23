import { useMemo, useState } from "react";
import { TaskInput } from "./TaskInput";
import { TaskItem } from "./TaskItem";
import { useTasks } from "../store/tasks";
import type { TaskFilter } from "../types";

const FILTERS: { value: TaskFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "active", label: "Active" },
  { value: "done", label: "Done" },
];

export function TasksView() {
  const { tasks, addTask, toggleTask, deleteTask, clearDone } = useTasks();
  const [filter, setFilter] = useState<TaskFilter>("all");

  const activeCount = tasks.filter((t) => !t.done).length;
  const doneCount = tasks.length - activeCount;

  const visible = useMemo(() => {
    if (filter === "active") return tasks.filter((t) => !t.done);
    if (filter === "done") return tasks.filter((t) => t.done);
    return tasks;
  }, [tasks, filter]);

  return (
    <>
      <div className="toolbar">
        <TaskInput onAdd={addTask} />
      </div>

      <main className="content">
        {visible.length > 0 ? (
          <ul className="list">
            {visible.map((task) => (
              <TaskItem
                key={task.id}
                task={task}
                onToggle={toggleTask}
                onDelete={deleteTask}
              />
            ))}
          </ul>
        ) : (
          <p className="empty">
            {tasks.length === 0
              ? "No tasks yet. Add one above."
              : filter === "active"
                ? "Nothing left to do."
                : "No completed tasks."}
          </p>
        )}
      </main>

      <footer className="footer">
        <span className="footer__count">
          {activeCount} {activeCount === 1 ? "task" : "tasks"} left
        </span>
        <div className="segmented" role="group" aria-label="Filter tasks">
          {FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              className={`segmented__btn${filter === f.value ? " is-active" : ""}`}
              aria-pressed={filter === f.value}
              onClick={() => setFilter(f.value)}
            >
              {f.label}
            </button>
          ))}
        </div>
        <button
          type="button"
          className="footer__clear"
          onClick={clearDone}
          disabled={doneCount === 0}
        >
          Clear done
        </button>
      </footer>
    </>
  );
}
