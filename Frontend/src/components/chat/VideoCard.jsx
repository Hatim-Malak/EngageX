import { ExternalLink } from "lucide-react"
import { formatNumber, formatDuration } from "../../lib/utils"

export default function VideoCard({ video, label, isWinner }) {
  if (!video) return null

  // Extract YouTube video ID from URL
  const getYoutubeId = (url) => {
    const match = url.match(/(?:v=|youtu\.be\/)([^&?/]+)/)
    return match ? match[1] : null
  }

  // Thumbnail URL
  const thumbnailUrl = video.platform === "youtube"
    ? `https://img.youtube.com/vi/${getYoutubeId(video.url)}/mqdefault.jpg`
    : null  // Instagram: null → show gradient placeholder

  // Format upload date
  const formatDate = (dateStr) => {
    try {
      return new Date(dateStr).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" })
    } catch {
      return dateStr
    }
  }

  return (
    <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
      {/* Thumbnail / header area */}
      <div className="relative">
        {thumbnailUrl ? (
          <img
            src={thumbnailUrl}
            alt={`${video.title} thumbnail`}
            className="w-full h-36 object-cover"
            loading="lazy"
            onError={(e) => { e.target.style.display = "none"; e.target.parentElement.querySelector(".fallback").classList.remove("hidden") }}
          />
        ) : null}
        {/* Fallback for Instagram or broken thumbnail */}
        <div className={`w-full h-36 bg-gradient-to-br from-pink-500 via-purple-500 to-orange-400 flex items-center justify-center ${thumbnailUrl ? "hidden fallback absolute inset-0" : ""}`}>
          <span className="text-white font-semibold text-sm">Instagram Reel</span>
        </div>
        {/* Platform badge */}
        <span className={`absolute top-2 left-2 px-2 py-0.5 rounded text-xs font-semibold text-white ${
          video.platform === "youtube" ? "bg-red-600" : "bg-gradient-to-r from-pink-500 to-orange-400"
        }`}>
          {video.platform === "youtube" ? "YouTube" : "Instagram"}
        </span>
        {/* Winner badge */}
        {isWinner && (
          <span className="absolute top-2 right-2 bg-yellow-400 text-yellow-900 text-xs font-semibold px-2 py-0.5 rounded-full flex items-center gap-1">
            🏆 Higher Engagement
          </span>
        )}
      </div>

      {/* Content */}
      <div className="p-3 space-y-2">
        {/* Title */}
        <h3 className="font-semibold text-gray-900 text-sm line-clamp-2 leading-snug" title={video.title}>
          {video.title}
        </h3>

        {/* Creator + followers */}
        <div className="flex items-center justify-between text-xs text-gray-500">
          <span>{video.creator}</span>
          <span>{formatNumber(video.follower_count)} followers</span>
        </div>

        {/* Stats row */}
        <div className="flex items-center gap-3 text-xs text-gray-500">
          <span>{formatNumber(video.views)} views</span>
          <span>{formatNumber(video.likes)} likes</span>
          <span>{formatNumber(video.comments)} comments</span>
        </div>

        {/* Engagement rate */}
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-500">Engagement Rate</span>
          <span className="text-lg font-bold text-blue-600">{video.engagement_rate.toFixed(1)}%</span>
        </div>

        {/* Hashtags */}
        {video.hashtags && video.hashtags.length > 0 && (
          <div className="flex flex-wrap gap-1 pt-1">
            {video.hashtags.slice(0, 3).map((tag, i) => (
              <span key={i} className="text-xs bg-blue-50 text-blue-700 px-1.5 py-0.5 rounded">#{tag}</span>
            ))}
            {video.hashtags.length > 3 && (
              <span className="text-xs text-gray-400">+{video.hashtags.length - 3} more</span>
            )}
          </div>
        )}

        {/* Upload date + duration */}
        <div className="flex items-center justify-between text-xs text-gray-400 pt-1 border-t border-gray-100">
          <span>{formatDate(video.upload_date)}</span>
          <span>{formatDuration(video.duration)}</span>
        </div>
      </div>
    </div>
  )
}
