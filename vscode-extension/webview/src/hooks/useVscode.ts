import { useEffect } from "react";

interface VsCodeApi {
  postMessage(message: unknown): void;
  getState(): unknown;
  setState(state: unknown): void;
}

declare function acquireVsCodeApi(): VsCodeApi;

// Acquire the API once at module level (can only be called once per webview)
const vscode = acquireVsCodeApi();

/**
 * Hook that subscribes to messages from the VSCode extension host.
 * Automatically cleans up the listener on unmount.
 */
export function useVscodeMessage<T>(handler: (message: T) => void): void {
  useEffect(() => {
    const listener = (event: MessageEvent<T>) => {
      handler(event.data);
    };
    window.addEventListener("message", listener);
    return () => {
      window.removeEventListener("message", listener);
    };
  }, [handler]);
}

/**
 * Post a message to the VSCode extension host.
 */
export function postMessage(message: unknown): void {
  vscode.postMessage(message);
}

/**
 * Get persisted webview state.
 */
export function getState<T>(): T | undefined {
  return vscode.getState() as T | undefined;
}

/**
 * Persist webview state across visibility changes.
 */
export function setState(state: unknown): void {
  vscode.setState(state);
}
