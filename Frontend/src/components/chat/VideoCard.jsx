import { ExternalLink } from "lucide-react";
import { formatNumber, formatDuration } from "../../lib/utils";

export default function VideoCard({ video, label, isWinner }) {
  if (!video) return null;

  // Extract YouTube video ID from URL
  const getYoutubeId = (url) => {
    if (!url) return null;
    const match = url.match(/(?:v=|youtu\.be\/|shorts\/)([^&?/]+)/);
    return match ? match[1] : null;
  };

  // Thumbnail URL
  const ytId = video.platform === "youtube" ? getYoutubeId(video.url) : null;
  const thumbnailUrl = ytId ? `https://img.youtube.com/vi/${ytId}/mqdefault.jpg` : null;

  // Format upload date
  const formatDate = (dateStr) => {
    try {
      return new Date(dateStr).toLocaleDateString("en-US", {
        year: "numeric",
        month: "short",
        day: "numeric",
      });
    } catch {
      return dateStr;
    }
  };

  return (
    <div className="bg-brand-primary/20 backdrop-blur-md border border-brand-secondary/30 rounded-xl overflow-hidden shadow-lg relative group transition-all duration-300 hover:border-brand-secondary/70 hover:shadow-[0_0_15px_rgba(64,138,113,0.3)]">
      {/* Thumbnail / header area */}
      <div className="relative">
        {thumbnailUrl ? (
          <img
            src={thumbnailUrl}
            alt={`${video.title} thumbnail`}
            className="w-full h-40 object-cover opacity-90 group-hover:opacity-100 transition-opacity"
            loading="lazy"
            onError={(e) => {
              e.target.style.display = "none";
              e.target.parentElement
                .querySelector(".fallback")
                .classList.remove("hidden");
            }}
          />
        ) : null}
        {/* Fallback for Instagram or broken thumbnail */}
        <div
          className={`w-full h-40 bg-gradient-to-br from-purple-700 via-pink-600 to-orange-500 flex items-center justify-center ${
            thumbnailUrl ? "hidden fallback absolute inset-0" : ""
          }`}
        >
          <span className="text-white font-bold tracking-wide text-sm drop-shadow-md">
            {video.platform === "youtube" ? "YouTube Video" : "Instagram Reel"}
          </span>
        </div>
        
        {/* Platform badge */}
        <span
          className={`absolute top-2 left-2 px-2.5 py-1 rounded text-xs font-bold text-white shadow-md backdrop-blur-sm ${
            video.platform === "youtube"
              ? "bg-red-600/90"
              : "bg-gradient-to-r from-pink-500/90 to-orange-400/90"
          }`}
        >
          {video.platform === "youtube" ? "YouTube" : "Instagram"}
        </span>
      </div>

      {/* Content */}
      <div className="p-4 space-y-3">
        {/* Title */}
        <h3
          className="font-bold text-white text-sm line-clamp-2 leading-snug drop-shadow-sm"
          title={video.title}
        >
          {video.title}
        </h3>

        {/* Creator + followers */}
        <div className="flex items-center justify-between text-xs text-brand-light/80 font-medium">
          <span>{video.creator}</span>
          <span>{formatNumber(video.follower_count)} followers</span>
        </div>

        {/* Stats row */}
        <div className="flex items-center gap-3 text-xs text-brand-light/70 bg-brand-dark/40 p-2 rounded-lg border border-brand-primary/40">
          <div className="flex-1 text-center border-r border-brand-primary/40">
            <span className="block font-bold text-white">{formatNumber(video.views)}</span>
            <span className="text-[10px] uppercase tracking-wider">views</span>
          </div>
          <div className="flex-1 text-center border-r border-brand-primary/40">
            <span className="block font-bold text-white">{formatNumber(video.likes)}</span>
            <span className="text-[10px] uppercase tracking-wider">likes</span>
          </div>
          <div className="flex-1 text-center">
            <span className="block font-bold text-white">{formatNumber(video.comments)}</span>
            <span className="text-[10px] uppercase tracking-wider">comments</span>
          </div>
        </div>

        {/* Engagement rate */}
        <div className="flex items-center justify-between py-1">
          <span className="text-xs font-semibold tracking-wider text-brand-secondary uppercase">
            Engagement Rate
          </span>
          <span className="text-xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-brand-light to-white drop-shadow-sm">
            {video.engagement_rate.toFixed(1)}%
          </span>
        </div>

        {/* Hashtags */}
        {video.hashtags && video.hashtags.length > 0 && (
          <div className="flex flex-wrap gap-1.5 pt-1">
            {video.hashtags.slice(0, 3).map((tag, i) => (
              <span
                key={i}
                className="text-xs bg-brand-primary/40 border border-brand-secondary/30 text-brand-light px-2 py-0.5 rounded-full"
              >
                #{tag}
              </span>
            ))}
            {video.hashtags.length > 3 && (
              <span className="text-xs text-brand-light/50 font-medium px-1">
                +{video.hashtags.length - 3} more
              </span>
            )}
          </div>
        )}

        {/* Upload date + duration */}
        <div className="flex items-center justify-between text-[11px] font-medium text-gray-400 pt-2 border-t border-brand-primary/30">
          <span>{formatDate(video.upload_date)}</span>
          <span>{formatDuration(video.duration)}</span>
        </div>
      </div>
    </div>
  );
}
