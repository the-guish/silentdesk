import type { Task } from "../types";

interface Props {
  task: Task;
  onToggle: (id: string) => void;
  onDelete: (id: string) => void;
}

export function TaskItem({ task, onToggle, onDelete }: Props) {
  return (
    <li className={`task${task.done ? " task--done" : ""}`}>
      <label className="task__main">
        <input
          type="checkbox"
          checked={task.done}
          onChange={() => onToggle(task.id)}
        />
        <span className="task__title">{task.title}</span>
      </label>
      <button
        type="button"
        className="task__delete"
        onClick={() => onDelete(task.id)}
        aria-label={`Delete "${task.title}"`}
        title="Delete"
      >
        <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
          <path
            d="M4 4l8 8M12 4l-8 8"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
          />
        </svg>
      </button>
    </li>
  );
}
