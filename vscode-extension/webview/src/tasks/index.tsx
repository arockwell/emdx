import { createRoot } from "react-dom/client";
import { StrictMode } from "react";
import { TaskView } from "./TaskView";
import "../styles/base.css";

const container = document.getElementById("root");
if (!container) {
  throw new Error("Root element not found");
}

const root = createRoot(container);
root.render(
  <StrictMode>
    <TaskView />
  </StrictMode>
);
