import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import useEngageStore from "../store/useEngageStore";
import Header from "../components/chat/Header";
import VideoCard from "../components/chat/VideoCard";
import EngagementComparison from "../components/chat/EngagementComparison";
import ChatPanel from "../components/chat/ChatPanel";
import LoadingSpinner from "../components/shared/LoadingSpinner";

export default function Chat() {
  const navigate = useNavigate();

  // Store selectors
  const loadSession = useEngageStore((s) => s.loadSession);
  const loadHistory = useEngageStore((s) => s.loadHistory);
  const fetchRateLimits = useEngageStore((s) => s.fetchRateLimits);
  const sessionLoading = useEngageStore((s) => s.sessionLoading);
  const sessionExists = useEngageStore((s) => s.sessionExists);
  const videoA = useEngageStore((s) => s.videoA);
  const videoB = useEngageStore((s) => s.videoB);
  const engagement = useEngageStore((s) => s.engagement);

  // Session initialization
  useEffect(() => {
    const initSession = async () => {
      const saved = localStorage.getItem("engagex_session_id");
      if (!saved) {
        navigate("/", { replace: true });
        return;
      }

      const data = await loadSession(saved);
      if (!data || !data.exists) {
        localStorage.removeItem("engagex_session_id");
        navigate("/", { replace: true });
        return;
      }

      // Session valid — load conversation history and rate limits
      await loadHistory();
      await fetchRateLimits();
    };

    initSession();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Loading state
  if (sessionLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-brand-dark">
        <div className="text-center">
          <LoadingSpinner size={32} color="text-brand-light" />
          <p className="mt-3 text-sm text-brand-secondary font-medium">Loading session...</p>
        </div>
      </div>
    );
  }

  // If session doesn't exist after load, wait for redirect
  if (!sessionExists) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-brand-dark">
        <p className="text-sm text-brand-secondary font-medium">Redirecting...</p>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-brand-dark text-white relative overflow-hidden">
      {/* Background radial gradients for depth */}
      <div className="absolute top-[-20%] left-[-10%] w-[60%] h-[60%] rounded-full bg-brand-primary opacity-10 blur-[120px] pointer-events-none" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[50%] h-[50%] rounded-full bg-brand-secondary opacity-10 blur-[120px] pointer-events-none" />

      {/* Header */}
      <Header />

      {/* Main content: three-panel layout */}
      <div className="flex-1 flex flex-col md:flex-row min-h-0 p-4 gap-4 relative z-10">
        {/* Left panel: Video cards */}
        <div className="flex md:flex-col gap-4 md:w-72 lg:w-80 overflow-y-auto overflow-x-hidden custom-scrollbar pb-4 pr-2 shrink-0">
          {/* Video A card */}
          <div className="min-w-[260px] md:min-w-0 shrink-0">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-xs font-bold text-brand-secondary uppercase tracking-widest">
                Video A
              </span>
              {engagement?.winner === "A" && (
                <span className="text-[10px] font-bold uppercase tracking-wider bg-gradient-to-r from-yellow-500 to-yellow-600 text-white px-2 py-0.5 rounded-full shadow-sm">
                  Winner
                </span>
              )}
            </div>
            <VideoCard video={videoA} label="A" isWinner={engagement?.winner === "A"} />
          </div>

          {/* Video B card */}
          <div className="min-w-[260px] md:min-w-0 shrink-0">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-xs font-bold text-brand-secondary uppercase tracking-widest">
                Video B
              </span>
              {engagement?.winner === "B" && (
                <span className="text-[10px] font-bold uppercase tracking-wider bg-gradient-to-r from-yellow-500 to-yellow-600 text-white px-2 py-0.5 rounded-full shadow-sm">
                  Winner
                </span>
              )}
            </div>
            <VideoCard video={videoB} label="B" isWinner={engagement?.winner === "B"} />
          </div>

          {/* Engagement comparison — between video cards on desktop */}
          <div className="hidden md:block pb-4 shrink-0">
            <EngagementComparison />
          </div>
        </div>

        {/* Mobile: Engagement comparison below scroll row */}
        <div className="md:hidden shrink-0">
          <EngagementComparison />
        </div>

        {/* Right panel: Chat */}
        <div className="flex-1 flex flex-col min-h-0 md:min-h-0">
          <div className="flex-1 flex flex-col bg-brand-dark/40 backdrop-blur-xl rounded-xl border border-brand-primary/50 shadow-2xl overflow-hidden">
            <ChatPanel />
          </div>
        </div>
      </div>
    </div>
  );
}
