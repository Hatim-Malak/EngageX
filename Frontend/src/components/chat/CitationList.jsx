import { ExternalLink, Clock } from "lucide-react";
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
      toast("Open Instagram to view at this timestamp", { icon: "📱" });
    }
  };

  return (
    <div className="flex flex-wrap gap-1.5 mt-2">
      {citations.map((cit, i) => (
        <button
          key={i}
          onClick={() => handleCitationClick(cit)}
          className="inline-flex items-center gap-1 text-xs bg-blue-50 text-blue-700 hover:bg-blue-100 px-2 py-1 rounded-full transition-colors border border-blue-200"
        >
          <Clock size={10} />
          Video {cit.video_id} · {cit.timestamp_start}–{cit.timestamp_end}
        </button>
      ))}
    </div>
  );
}
