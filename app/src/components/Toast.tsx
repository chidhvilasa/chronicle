import { useEffect } from "react";
import { TOAST_DURATION_MS } from "../config";
import { useAppStore } from "../store/useAppStore";

/** Bottom-of-screen notification for background events like a completed replay. */
export function Toast() {
  const toast = useAppStore((state) => state.toast);
  const dismissToast = useAppStore((state) => state.dismissToast);

  useEffect(() => {
    if (toast === null) return;
    const timeoutId = setTimeout(dismissToast, TOAST_DURATION_MS);
    return () => clearTimeout(timeoutId);
  }, [toast, dismissToast]);

  if (toast === null) return null;

  return (
    <div className="toast" data-testid="toast" role="status">
      <span>{toast.message}</span>
      {toast.onAction !== undefined && (
        <button
          type="button"
          className="toast-action"
          onClick={() => {
            toast.onAction?.();
            dismissToast();
          }}
        >
          {toast.actionLabel ?? "OK"}
        </button>
      )}
      <button type="button" className="toast-dismiss" aria-label="Dismiss" onClick={dismissToast}>
        ×
      </button>
    </div>
  );
}
