import { Clock } from "lucide-react";
import { toast } from "react-hot-toast";
import useEngageStore from "../../store/useEngageStore";

export default function CitationList({ citations }) {
  const videoA = useEngageStore((s) => s.videoA);

  if (!citations || citations.length === 0) return null;

  const getYoutubeId = (url) => {
    const match = url?.match(/(?:v=|youtu\.be\/)([^&?/]+)/);
    return match ? match[1] : null;
  };

  const VIDEO_ID_A = getYoutubeId(videoA?.url);

  const toSeconds = (timestamp) => {
    const [m, s] = timestamp.split(":").map(Number);
    return m * 60 + s;
  };

  const handleCitationClick = (citation) => {
    if (citation.video_id === "A") {
      const seconds = toSeconds(citation.timestamp_start);
      window.open(
        `https://youtube.com/watch?v=${VIDEO_ID_A}&t=${seconds}`,
        "_blank",
        "noopener"
      );
    } else {
      toast.success("Open Instagram to view at this timestamp", { 
        icon: "📱",
        style: {
          background: "#091413",
          color: "#B0E4CC",
          border: "1px solid #285A48"
        }
      });
    }
  };

  return (
    <div className="flex flex-wrap gap-2 mt-3 pt-3 border-t border-brand-primary/30">
      {citations.map((cit, i) => (
        <button
          key={i}
          onClick={() => handleCitationClick(cit)}
          className="inline-flex items-center gap-1 text-[11px] font-medium bg-brand-primary/40 text-brand-light hover:bg-brand-secondary hover:text-white px-2.5 py-1 rounded-md transition-colors border border-brand-secondary/40 shadow-sm"
        >
          <Clock size={12} />
          Video {cit.video_id} · {cit.timestamp_start}–{cit.timestamp_end}
        </button>
      ))}
    </div>
  );
}
