import { useState } from "react";
import { TasksView } from "./components/TasksView";
import { TopicsView } from "./components/TopicsView";

type View = "tasks" | "topics";

const VIEWS: { value: View; label: string }[] = [
  { value: "tasks", label: "Tasks" },
  { value: "topics", label: "Topics" },
];

export default function App() {
  const [view, setView] = useState<View>("tasks");

  return (
    <div className="app">
      <header className="header">
        <h1 className="header__title">SilentDesk</h1>
        <nav className="segmented" aria-label="Views">
          {VIEWS.map((v) => (
            <button
              key={v.value}
              type="button"
              className={`segmented__btn${view === v.value ? " is-active" : ""}`}
              aria-current={view === v.value ? "page" : undefined}
              onClick={() => setView(v.value)}
            >
              {v.label}
            </button>
          ))}
        </nav>
      </header>

      {view === "tasks" ? <TasksView /> : <TopicsView />}
    </div>
  );
}
