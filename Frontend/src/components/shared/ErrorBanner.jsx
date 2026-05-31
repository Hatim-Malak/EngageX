import { useEffect } from "react";
import { X } from "lucide-react";
import useEngageStore from "../../store/useEngageStore";

/**
 * Fixed-bottom error banner that reads from the global store.
 * Auto-dismisses after 5 seconds. Shows nothing when no error.
 */
export default function ErrorBanner() {
  const error = useEngageStore((s) => s.error);
  const clearError = useEngageStore((s) => s.clearError);

  useEffect(() => {
    if (!error) return;
    const t = setTimeout(clearError, 5000);
    return () => clearTimeout(t);
  }, [error, clearError]);

  if (!error) return null;

  return (
    <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 bg-red-50 border border-red-200 text-red-800 px-4 py-3 rounded-lg shadow-lg max-w-md w-full">
      <span className="flex-1 text-sm">{error}</span>
      <button
        onClick={clearError}
        className="text-red-500 hover:text-red-700"
        aria-label="Dismiss"
      >
        <X size={16} />
      </button>
    </div>
  );
}
