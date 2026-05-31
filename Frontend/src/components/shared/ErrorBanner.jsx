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
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 bg-red-900/40 backdrop-blur-md border border-red-500/50 text-red-200 px-5 py-3.5 rounded-xl shadow-[0_0_20px_rgba(220,38,38,0.3)] max-w-md w-full font-medium">
      <span className="flex-1 text-sm">{error}</span>
      <button
        onClick={clearError}
        className="text-red-400 hover:text-white transition-colors bg-red-950/50 rounded-md p-1"
        aria-label="Dismiss"
      >
        <X size={16} />
      </button>
    </div>
  );
}
