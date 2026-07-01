import { useEffect, useState } from "react";

function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

/**
 * Listens for the `chronicle-server-error` event the Rust backend emits when
 * it fails to start the local Chronicle server, so the UI can show a
 * human-readable banner instead of silently having no data. No-ops outside
 * the Tauri desktop shell (e.g. plain `npm run dev` in a browser).
 */
export function useServerStartupError(): string | null {
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!isTauriRuntime()) return;

    let unlisten: (() => void) | undefined;
    let cancelled = false;

    import("@tauri-apps/api/event").then(({ listen }) => {
      listen<string>("chronicle-server-error", (event) => {
        if (!cancelled) setMessage(event.payload);
      }).then((fn) => {
        if (cancelled) {
          fn();
        } else {
          unlisten = fn;
        }
      });
    });

    return () => {
      cancelled = true;
      unlisten?.();
    };
  }, []);

  return message;
}
