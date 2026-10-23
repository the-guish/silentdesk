import { useState, type FormEvent } from "react";

interface Props {
  onAdd: (title: string) => void;
}

export function TaskInput({ onAdd }: Props) {
  const [value, setValue] = useState("");

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!value.trim()) return;
    onAdd(value);
    setValue("");
  }

  return (
    <form className="task-input" onSubmit={submit}>
      <input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Add a task and press Enter"
        aria-label="New task"
        autoFocus
      />
    </form>
  );
}
