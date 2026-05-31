import { useNavigate } from "react-router-dom";
import { Plus } from "lucide-react";
import useEngageStore from "../../store/useEngageStore";
import RateLimitBadge from "../shared/RateLimitBadge";

export default function Header() {
  const navigate = useNavigate();
  const resetStore = useEngageStore((s) => s.resetStore);

  const handleNewSession = () => {
    resetStore();
    localStorage.removeItem("engagex_session_id");
    navigate("/");
  };

  return (
    <header className="flex items-center justify-between px-6 py-4 border-b border-brand-primary/30 bg-brand-dark/50 backdrop-blur-md relative z-20">
      {/* Logo / wordmark */}
      <div className="flex items-center gap-2">
        <span className="text-2xl font-extrabold tracking-tight text-transparent bg-clip-text bg-gradient-to-r from-brand-light to-brand-secondary">
          EngageX
        </span>
      </div>

      {/* Right side */}
      <div className="flex items-center gap-4">
        <RateLimitBadge />
        <button
          onClick={handleNewSession}
          className="flex items-center gap-1.5 text-sm font-semibold text-brand-light hover:text-white bg-brand-primary/40 hover:bg-brand-primary/70 border border-brand-primary/50 px-4 py-2 rounded-lg transition-all duration-300 shadow-sm"
        >
          <Plus size={16} />
          New Session
        </button>
      </div>
    </header>
  );
}
