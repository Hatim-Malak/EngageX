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
    <div className="bg-brand-primary/20 backdrop-blur-md border border-brand-secondary/30 rounded-xl p-4 flex items-center justify-between shadow-lg">
      <div>
        <p className="text-sm font-semibold text-white">Resume previous session?</p>
        <p className="text-xs text-brand-light mt-0.5 opacity-80">Pick up where you left off</p>
      </div>
      <div className="flex items-center gap-3">
        <button
          onClick={handleResume}
          className="bg-brand-secondary text-white px-4 py-1.5 rounded-lg text-sm font-bold hover:bg-brand-light hover:text-brand-dark transition-all duration-300 shadow-md"
        >
          Resume
        </button>
        <button
          onClick={handleDismiss}
          className="text-gray-400 hover:text-white p-1 transition-colors"
          aria-label="Dismiss"
        >
          <X size={18} />
        </button>
      </div>
    </div>
  );
}
