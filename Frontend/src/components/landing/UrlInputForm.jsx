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
    <form onSubmit={handleSubmit} className="space-y-5">
      {/* URL A input */}
      <div>
        <label className="block text-sm font-medium text-brand-light mb-1.5 opacity-90">
          Video A — YouTube
        </label>
        <input
          type="url"
          value={urlA}
          onChange={(e) => setUrlA(e.target.value)}
          placeholder="https://youtube.com/watch?v=..."
          disabled={ingesting}
          className="w-full px-4 py-3 bg-brand-dark/50 border border-brand-primary rounded-lg focus:ring-2 focus:ring-brand-light focus:border-brand-light disabled:opacity-50 disabled:cursor-not-allowed text-sm text-white placeholder-gray-400 transition-all shadow-inner"
        />
      </div>

      {/* URL B input */}
      <div>
        <label className="block text-sm font-medium text-brand-light mb-1.5 opacity-90">
          Video B — Instagram Reel
        </label>
        <input
          type="url"
          value={urlB}
          onChange={(e) => setUrlB(e.target.value)}
          placeholder="https://instagram.com/reel/..."
          disabled={ingesting}
          className="w-full px-4 py-3 bg-brand-dark/50 border border-brand-primary rounded-lg focus:ring-2 focus:ring-brand-light focus:border-brand-light disabled:opacity-50 disabled:cursor-not-allowed text-sm text-white placeholder-gray-400 transition-all shadow-inner"
        />
      </div>

      {/* Submit button */}
      <button
        type="submit"
        disabled={ingesting || !urlA.trim() || !urlB.trim()}
        className="w-full flex items-center justify-center gap-2 bg-gradient-to-r from-brand-secondary to-brand-primary hover:from-brand-light hover:to-brand-secondary text-white hover:text-brand-dark px-4 py-3.5 rounded-lg font-bold disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-300 shadow-[0_0_15px_rgba(64,138,113,0.3)] hover:shadow-[0_0_25px_rgba(176,228,204,0.5)] transform hover:-translate-y-0.5"
      >
        {ingesting ? (
          <>
            <Loader2 size={20} className="animate-spin" /> Analyzing Videos...
          </>
        ) : (
          <>
            <ArrowRight size={20} /> Analyze Videos
          </>
        )}
      </button>

      {/* Inline error */}
      {ingestError && (
        <p className="text-red-300 text-sm bg-red-900/40 border border-red-500/50 rounded-lg px-3 py-2 text-center mt-2 shadow-sm backdrop-blur-sm">
          {ingestError}
        </p>
      )}
    </form>
  );
}
