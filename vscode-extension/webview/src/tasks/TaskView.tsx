import { useState, useCallback, useEffect, useRef } from "react";
import { useVscodeMessage, postMessage } from "../hooks/useVscode";

export interface Task {
  id: number;
  title: string;
  description: string;
  status: TaskStatus;
  priority: number;
  category: string | null;
  epic_id: number | null;
  epic_title: string | null;
  dependencies: number[];
  created_at: string;
  updated_at: string;
}

type TaskStatus = "ready" | "active" | "blocked" | "done" | "failed" | "wontdo";

interface TaskGroup {
  status: TaskStatus;
  label: string;
  tasks: Task[];
  collapsed: boolean;
}

type IncomingMessage =
  | { type: "tasks"; data: Task[] }
  | { type: "taskUpdated"; data: Task }
  | { type: "loading"; data: boolean }
  | { type: "error"; data: string };

const STATUS_ORDER: TaskStatus[] = ["ready", "active", "blocked", "done", "failed", "wontdo"];

const STATUS_LABELS: Record<TaskStatus, string> = {
  ready: "Ready",
  active: "Active",
  blocked: "Blocked",
  done: "Done",
  failed: "Failed",
  wontdo: "Won't Do",
};

const STATUS_ICONS: Record<TaskStatus, string> = {
  ready: "\u{25CB}", // white circle
  active: "\u{25D4}", // circle with upper right quadrant
  blocked: "\u{26D4}", // no entry
  done: "\u{2705}", // check mark
  failed: "\u{274C}", // cross mark
  wontdo: "\u{23ED}", // skip
};

function groupTasks(tasks: Task[]): TaskGroup[] {
  const grouped = new Map<TaskStatus, Task[]>();
  for (const status of STATUS_ORDER) {
    grouped.set(status, []);
  }
  for (const task of tasks) {
    const group = grouped.get(task.status);
    if (group) {
      group.push(task);
    }
  }
  return STATUS_ORDER.map((status) => ({
    status,
    label: STATUS_LABELS[status],
    tasks: grouped.get(status) ?? [],
    collapsed: status === "done" || status === "failed" || status === "wontdo",
  }));
}

export function TaskView() {
  const [allTasks, setAllTasks] = useState<Task[]>([]);
  const [groups, setGroups] = useState<TaskGroup[]>([]);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [collapsedGroups, setCollapsedGroups] = useState<Set<TaskStatus>>(
    new Set(["done", "failed", "wontdo"])
  );

  // Flat list of visible tasks for keyboard navigation
  const [flatTasks, setFlatTasks] = useState<Task[]>([]);
  const [focusIndex, setFocusIndex] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    postMessage({ type: "fetchTasks" });
  }, []);

  useEffect(() => {
    const newGroups = groupTasks(allTasks);
    setGroups(newGroups);

    const visible: Task[] = [];
    for (const group of newGroups) {
      if (!collapsedGroups.has(group.status)) {
        visible.push(...group.tasks);
      }
    }
    setFlatTasks(visible);
  }, [allTasks, collapsedGroups]);

  const handleMessage = useCallback(
    (msg: IncomingMessage) => {
      switch (msg.type) {
        case "tasks":
          setAllTasks(msg.data);
          setLoading(false);
          if (msg.data.length > 0 && !selectedTask) {
            setSelectedTask(msg.data[0]);
          }
          break;
        case "taskUpdated": {
          setAllTasks((prev) =>
            prev.map((t) => (t.id === msg.data.id ? msg.data : t))
          );
          if (selectedTask?.id === msg.data.id) {
            setSelectedTask(msg.data);
          }
          break;
        }
        case "loading":
          setLoading(msg.data);
          break;
        case "error":
          setError(msg.data);
          setLoading(false);
          break;
      }
    },
    [selectedTask]
  );

  useVscodeMessage(handleMessage);

  const toggleGroup = useCallback((status: TaskStatus) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(status)) {
        next.delete(status);
      } else {
        next.add(status);
      }
      return next;
    });
  }, []);

  const updateTaskStatus = useCallback((taskId: number, newStatus: TaskStatus) => {
    postMessage({ type: "updateTaskStatus", id: taskId, status: newStatus });
  }, []);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (flatTasks.length === 0) return;

      switch (e.key) {
        case "ArrowDown":
        case "j":
          e.preventDefault();
          setFocusIndex((prev) => {
            const next = Math.min(prev + 1, flatTasks.length - 1);
            setSelectedTask(flatTasks[next]);
            return next;
          });
          break;
        case "ArrowUp":
        case "k":
          e.preventDefault();
          setFocusIndex((prev) => {
            const next = Math.max(prev - 1, 0);
            setSelectedTask(flatTasks[next]);
            return next;
          });
          break;
        case "d":
          if (selectedTask) {
            updateTaskStatus(selectedTask.id, "done");
          }
          break;
        case "a":
          if (selectedTask) {
            updateTaskStatus(selectedTask.id, "active");
          }
          break;
        case "b":
          if (selectedTask) {
            updateTaskStatus(selectedTask.id, "blocked");
          }
          break;
      }
    },
    [flatTasks, selectedTask, updateTaskStatus]
  );

  return (
    <div className="panel-container">
      {loading && <div className="loading-bar" />}

      {error && (
        <div className="error-banner" role="alert">
          {error}
          <button className="error-dismiss" onClick={() => setError(null)} aria-label="Dismiss">
            x
          </button>
        </div>
      )}

      <div className="split-layout" onKeyDown={handleKeyDown} tabIndex={0} ref={listRef}>
        <div className="list-pane">
          <div className="task-list" role="tree" aria-label="Tasks">
            {groups.map((group) => (
              <div key={group.status} className="task-group">
                <button
                  className="group-header"
                  onClick={() => toggleGroup(group.status)}
                  aria-expanded={!collapsedGroups.has(group.status)}
                >
                  <span className="group-chevron">
                    {collapsedGroups.has(group.status) ? "\u{25B6}" : "\u{25BC}"}
                  </span>
                  <span className="group-label">
                    {STATUS_ICONS[group.status]} {group.label}
                  </span>
                  <span className="group-count">{group.tasks.length}</span>
                </button>

                {!collapsedGroups.has(group.status) && (
                  <div className="group-tasks" role="group">
                    {group.tasks.map((task) => {
                      const visibleIdx = flatTasks.indexOf(task);
                      return (
                        <div
                          key={task.id}
                          className={[
                            "task-row",
                            task.id === selectedTask?.id ? "selected" : "",
                            visibleIdx === focusIndex ? "focused" : "",
                          ]
                            .filter(Boolean)
                            .join(" ")}
                          onClick={() => {
                            setSelectedTask(task);
                            setFocusIndex(visibleIdx);
                          }}
                          role="treeitem"
                          aria-selected={task.id === selectedTask?.id}
                        >
                          <span className="task-priority">
                            {task.priority > 0 ? `P${task.priority}` : ""}
                          </span>
                          <span className="task-title">{task.title}</span>
                          {task.category && (
                            <span className="badge badge-category">{task.category}</span>
                          )}
                        </div>
                      );
                    })}
                    {group.tasks.length === 0 && (
                      <div className="empty-group">No tasks</div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        <div className="preview-pane">
          {selectedTask ? (
            <TaskDetail
              task={selectedTask}
              onStatusChange={updateTaskStatus}
            />
          ) : (
            <div className="empty-state">
              <p>Select a task to view details</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

interface TaskDetailProps {
  task: Task;
  onStatusChange: (id: number, status: TaskStatus) => void;
}

function TaskDetail({ task, onStatusChange }: TaskDetailProps) {
  return (
    <div className="task-detail">
      <header className="detail-header">
        <h2 className="detail-title">
          {STATUS_ICONS[task.status]} {task.title}
        </h2>
        <div className="detail-meta">
          <span className="meta-item">ID: #{task.id}</span>
          <span className="meta-item">Status: {STATUS_LABELS[task.status]}</span>
          {task.priority > 0 && (
            <span className="meta-item">Priority: P{task.priority}</span>
          )}
          {task.category && (
            <span className="meta-item">Category: {task.category}</span>
          )}
          {task.epic_title && (
            <span className="meta-item">Epic: {task.epic_title}</span>
          )}
        </div>
      </header>

      {task.description && (
        <div className="detail-description">
          <h3>Description</h3>
          <p>{task.description}</p>
        </div>
      )}

      {task.dependencies.length > 0 && (
        <div className="detail-dependencies">
          <h3>Dependencies</h3>
          <div className="dep-chips">
            {task.dependencies.map((depId) => (
              <span key={depId} className="badge">
                #{depId}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="detail-actions">
        {task.status !== "active" && (
          <button
            className="action-btn action-active"
            onClick={() => onStatusChange(task.id, "active")}
          >
            Mark Active
          </button>
        )}
        {task.status !== "done" && (
          <button
            className="action-btn action-done"
            onClick={() => onStatusChange(task.id, "done")}
          >
            Mark Done
          </button>
        )}
        {task.status !== "blocked" && (
          <button
            className="action-btn action-blocked"
            onClick={() => onStatusChange(task.id, "blocked")}
          >
            Mark Blocked
          </button>
        )}
      </div>
    </div>
  );
}
