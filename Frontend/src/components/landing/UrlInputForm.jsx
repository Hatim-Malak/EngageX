import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2, ArrowRight } from "lucide-react";
import useEngageStore from "../../store/useEngageStore";

export default function UrlInputForm() {
  const [urlA, setUrlA] = useState("");
  const [urlB, setUrlB] = useState("");
  const navigate = useNavigate();

  const ingestVideos = useEngageStore((s) => s.ingestVideos);
  const ingesting = useEngageStore((s) => s.ingesting);
  const ingestResult = useEngageStore((s) => s.ingestResult);
  const ingestError = useEngageStore((s) => s.ingestError);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!urlA.trim() || !urlB.trim()) return;
    await ingestVideos(urlA.trim(), urlB.trim());
  };

  useEffect(() => {
    if (ingestResult) {
      localStorage.setItem("engagex_session_id", ingestResult.session_id);
      navigate("/chat");
    }
  }, [ingestResult, navigate]);

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {/* URL A input */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          Video A — YouTube
        </label>
        <input
          type="url"
          value={urlA}
          onChange={(e) => setUrlA(e.target.value)}
          placeholder="https://youtube.com/watch?v=..."
          disabled={ingesting}
          className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-sm"
        />
      </div>

      {/* URL B input */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          Video B — Instagram Reel
        </label>
        <input
          type="url"
          value={urlB}
          onChange={(e) => setUrlB(e.target.value)}
          placeholder="https://instagram.com/reel/..."
          disabled={ingesting}
          className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-sm"
        />
      </div>

      {/* Submit button */}
      <button
        type="submit"
        disabled={ingesting || !urlA.trim() || !urlB.trim()}
        className="w-full flex items-center justify-center gap-2 bg-blue-600 text-white px-4 py-2.5 rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        {ingesting ? (
          <>
            <Loader2 size={18} className="animate-spin" /> Analyzing Videos...
          </>
        ) : (
          <>
            <ArrowRight size={18} /> Analyze Videos
          </>
        )}
      </button>

      {/* Inline error */}
      {ingestError && (
        <p className="text-red-600 text-sm bg-red-50 border border-red-200 rounded-lg px-3 py-2">
          {ingestError}
        </p>
      )}
    </form>
  );
}
