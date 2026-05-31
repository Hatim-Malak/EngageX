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
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <LoadingSpinner size={32} color="text-blue-500" />
          <p className="mt-3 text-sm text-gray-500">Loading session...</p>
        </div>
      </div>
    );
  }

  // If session doesn't exist after load, wait for redirect
  if (!sessionExists) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <p className="text-sm text-gray-400">Redirecting...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      {/* Header */}
      <Header />

      {/* Main content: three-panel layout */}
      <div className="flex-1 flex flex-col md:flex-row min-h-0 p-4 gap-4">
        {/* Left panel: Video cards */}
        <div className="flex md:flex-col gap-4 md:w-72 lg:w-80 overflow-x-auto md:overflow-x-visible pb-2 md:pb-0">
          {/* Video A card */}
          <div className="min-w-[260px] md:min-w-0 flex-shrink-0 md:flex-shrink">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                Video A
              </span>
              {engagement?.winner === "A" && (
                <span className="text-xs bg-yellow-100 text-yellow-800 px-1.5 py-0.5 rounded-full">
                  Winner
                </span>
              )}
            </div>
            <VideoCard video={videoA} label="A" isWinner={engagement?.winner === "A"} />
          </div>

          {/* Video B card */}
          <div className="min-w-[260px] md:min-w-0 flex-shrink-0 md:flex-shrink">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                Video B
              </span>
              {engagement?.winner === "B" && (
                <span className="text-xs bg-yellow-100 text-yellow-800 px-1.5 py-0.5 rounded-full">
                  Winner
                </span>
              )}
            </div>
            <VideoCard video={videoB} label="B" isWinner={engagement?.winner === "B"} />
          </div>

          {/* Engagement comparison — between video cards on desktop */}
          <div className="hidden md:block">
            <EngagementComparison />
          </div>
        </div>

        {/* Mobile: Engagement comparison below scroll row */}
        <div className="md:hidden">
          <EngagementComparison />
        </div>

        {/* Right panel: Chat */}
        <div className="flex-1 flex flex-col min-h-0 md:min-h-0">
          <div className="flex-1 flex flex-col bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden">
            <ChatPanel />
          </div>
        </div>
      </div>
    </div>
  );
}
