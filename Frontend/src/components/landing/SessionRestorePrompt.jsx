import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { X } from "lucide-react";
import useEngageStore from "../../store/useEngageStore";

export default function SessionRestorePrompt() {
  const [dismissed, setDismissed] = useState(false);
  const navigate = useNavigate();
  const loadSession = useEngageStore((s) => s.loadSession);

  const savedId = typeof window !== "undefined" ? localStorage.getItem("engagex_session_id") : null;

  if (!savedId || dismissed) return null;

  const handleResume = async () => {
    await loadSession(savedId);
    navigate("/chat");
  };

  const handleDismiss = () => {
    localStorage.removeItem("engagex_session_id");
    setDismissed(true);
  };

  return (
    <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 flex items-center justify-between">
      <div>
        <p className="text-sm font-medium text-blue-900">Resume previous session?</p>
        <p className="text-xs text-blue-700 mt-0.5">Pick up where you left off</p>
      </div>
      <div className="flex items-center gap-2">
        <button
          onClick={handleResume}
          className="bg-blue-600 text-white px-3 py-1.5 rounded-md text-sm font-medium hover:bg-blue-700 transition-colors"
        >
          Resume
        </button>
        <button
          onClick={handleDismiss}
          className="text-blue-400 hover:text-blue-600 p-1"
          aria-label="Dismiss"
        >
          <X size={16} />
        </button>
      </div>
    </div>
  );
}
