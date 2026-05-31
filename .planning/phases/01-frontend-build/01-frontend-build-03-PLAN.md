---
phase: 01-frontend-build
plan: 03
type: execute
wave: 2
depends_on:
  - 01-frontend-build-01
files_modified:
  - Frontend/src/components/chat/Header.jsx
  - Frontend/src/components/chat/VideoCard.jsx
  - Frontend/src/components/chat/EngagementComparison.jsx
autonomous: true
requirements: [FE-05, FE-06, FE-10]

must_haves:
  truths:
    - "User sees EngageX header with rate limit badge and New Session button"
    - "User sees two video cards with platform badge, thumbnail, title, stats, engagement, hashtags"
    - "User sees a winner indicator on the higher-engagement video card"
    - "User sees a horizontal bar chart comparing engagement rates"
  artifacts:
    - path: "Frontend/src/components/chat/Header.jsx"
      provides: "Chat page header"
      contains: "RateLimitBadge"
    - path: "Frontend/src/components/chat/VideoCard.jsx"
      provides: "Video metadata display card"
      contains: "formatNumber, formatDuration"
    - path: "Frontend/src/components/chat/EngagementComparison.jsx"
      provides: "CSS horizontal engagement comparison bars"
      contains: "engagement_rate"
  key_links:
    - from: "Header.jsx"
      to: "shared/RateLimitBadge.jsx"
      via: "import"
      pattern: "RateLimitBadge"
    - from: "Header.jsx"
      to: "useEngageStore"
      via: "resetStore"
      pattern: "resetStore"
    - from: "VideoCard.jsx"
      to: "lib/utils.js"
      via: "import formatNumber, formatDuration"
      pattern: "formatNumber|formatDuration"
    - from: "VideoCard.jsx"
      to: "useEngageStore"
      via: "store state for video data"
      pattern: "useEngageStore"
---

<objective>
Build the chat page analytics components: header with navigation, video cards displaying full metadata, and a pure-CSS engagement comparison chart.

Purpose: These components form the left two panels of the three-panel chat layout. They display the video comparison data that users reference while chatting.
Output: Header.jsx, VideoCard.jsx, EngagementComparison.jsx
</objective>

<execution_context>
@$HOME/.config/opencode/get-shit-done/workflows/execute-plan.md
@$HOME/.config/opencode/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/01-frontend-build/01-frontend-build-CONTEXT.md
@Frontend/src/store/useEngageStore.js
</context>

<tasks>

<task type="auto">
<name>Task 1: Create Header component</name>
<files>
  Frontend/src/components/chat/Header.jsx
</files>

<read_first>
  Frontend/src/store/useEngageStore.js
  Frontend/src/components/shared/RateLimitBadge.jsx (will exist — created in Plan 01)
</read_first>

<action>
Create `Frontend/src/components/chat/Header.jsx`:

```jsx
import { useNavigate } from "react-router-dom"
import { Plus } from "lucide-react"
import useEngageStore from "../../store/useEngageStore"
import RateLimitBadge from "../shared/RateLimitBadge"

export default function Header() {
  const navigate = useNavigate()
  const resetStore = useEngageStore((s) => s.resetStore)

  const handleNewSession = () => {
    resetStore()
    localStorage.removeItem("engagex_session_id")
    navigate("/")
  }

  return (
    <header className="flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-white">
      {/* Logo / wordmark */}
      <div className="flex items-center gap-2">
        <span className="text-xl font-bold text-gray-900 tracking-tight">
          EngageX
        </span>
      </div>

      {/* Right side */}
      <div className="flex items-center gap-3">
        <RateLimitBadge />
        <button
          onClick={handleNewSession}
          className="flex items-center gap-1.5 text-sm text-gray-600 hover:text-gray-900 bg-gray-100 hover:bg-gray-200 px-3 py-1.5 rounded-lg transition-colors"
        >
          <Plus size={16} />
          New Session
        </button>
      </div>
    </header>
  )
}
```

- Import `useNavigate` from `react-router-dom`
- Import `Plus` from `lucide-react`
- Import `useEngageStore` for `resetStore` action
- Import `RateLimitBadge` from shared
- `handleNewSession`: calls `resetStore()`, removes localStorage key, navigates to `/`
- Header: flex row, border-b, white background
- Left: "EngageX" wordmark (bold, text-xl)
- Right: RateLimitBadge + "New Session" button with Plus icon
</action>

<acceptance_criteria>
  - `Frontend/src/components/chat/Header.jsx` exists
  - `grep -n "RateLimitBadge" Frontend/src/components/chat/Header.jsx` matches
  - `grep -n "resetStore" Frontend/src/components/chat/Header.jsx` matches
  - `grep -n "localStorage.removeItem" Frontend/src/components/chat/Header.jsx` matches
  - `grep -n "New Session" Frontend/src/components/chat/Header.jsx` matches
  - `grep -n "export default function Header" Frontend/src/components/chat/Header.jsx` matches
</acceptance_criteria>

<verify>
  <automated>node -e "const fs=require('fs');const p='Frontend/src/components/chat/Header.jsx';fs.existsSync(p)?console.log('OK: '+p):(console.error('MISSING: '+p),process.exit(1))"</automated>
</verify>

<done>
Header renders EngageX wordmark on left, RateLimitBadge and New Session button on right. New Session calls resetStore + clears localStorage + navigates to /.
</done>
</task>

<task type="auto">
<name>Task 2: Create VideoCard component</name>
<files>
  Frontend/src/components/chat/VideoCard.jsx
</files>

<read_first>
  Frontend/src/store/useEngageStore.js
  Frontend/src/lib/utils.js (will exist — created in Plan 01)
</read_first>

<action>
Create `Frontend/src/components/chat/VideoCard.jsx`:

**Props:**
```js
{
  video,        // videoA or videoB object from store (shape below)
  label,        // "A" | "B" — identifies which video
  isWinner      // boolean — true if this video has higher engagement
}
```

**Video object shape** (from store state):
```
{
  video_id: string       // "A" or "B"
  platform: string       // "youtube" | "instagram"
  url: string
  title: string
  creator: string
  follower_count: number
  views: number
  likes: number
  comments: number
  hashtags: string[]
  upload_date: string    // "YYYY-MM-DD"
  duration: number       // seconds
  engagement_rate: number // e.g. 1.211
}
```

**Implementation:**
```jsx
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
```

- Returns `null` if `video` is falsy
- YouTube thumbnail: extract video ID via regex, construct `https://img.youtube.com/vi/{ID}/mqdefault.jpg`
- Instagram: show gradient placeholder (pink-purple-orange gradient with "Instagram Reel" text)
- Platform badge: YouTube = red bg, Instagram = pink-to-orange gradient
- Winner badge: yellow pill top-right with trophy emoji — only when `isWinner === true`
- Title: `line-clamp-2` with `title` attribute for full text on hover
- Creator + follower_count in flex row
- Stats row: views | likes | comments (all formatted)
- Engagement rate: large bold number with % suffix
- Hashtags: first 3 as blue pills, "+N more" if > 3
- Upload date + duration in bottom border-t row
</action>

<acceptance_criteria>
  - `Frontend/src/components/chat/VideoCard.jsx` exists
  - `grep -n "formatNumber" Frontend/src/components/chat/VideoCard.jsx` matches
  - `grep -n "formatDuration" Frontend/src/components/chat/VideoCard.jsx` matches
  - `grep -n "img.youtube.com" Frontend/src/components/chat/VideoCard.jsx` matches (YouTube thumbnail)
  - `grep -n "engagement_rate" Frontend/src/components/chat/VideoCard.jsx` matches
  - `grep -n "Higher Engagement" Frontend/src/components/chat/VideoCard.jsx` matches
  - `grep -n "line-clamp-2" Frontend/src/components/chat/VideoCard.jsx` matches
  - `grep -n "hashtags.slice" Frontend/src/components/chat/VideoCard.jsx` matches
  - `grep -n "Instagram Reel" Frontend/src/components/chat/VideoCard.jsx` matches (fallback)
</acceptance_criteria>

<verify>
  <automated>node -e "const fs=require('fs');const p='Frontend/src/components/chat/VideoCard.jsx';fs.existsSync(p)?console.log('OK: '+p):(console.error('MISSING: '+p),process.exit(1))"</automated>
</verify>

<done>
VideoCard renders full video card with platform badge, thumbnail/gradient, title, creator+followers, stats row, engagement rate badge, hashtag pills, upload date, duration. Winner variant shows trophy badge.
</done>
</task>

<task type="auto">
<name>Task 3: Create EngagementComparison component</name>
<files>
  Frontend/src/components/chat/EngagementComparison.jsx
</files>

<read_first>
  Frontend/src/store/useEngageStore.js
</read_first>

<action>
Create `Frontend/src/components/chat/EngagementComparison.jsx`:

```jsx
import useEngageStore from "../../store/useEngageStore"
import { TrendingUp } from "lucide-react"

export default function EngagementComparison() {
  const engagement = useEngageStore((s) => s.engagement)

  if (!engagement) return null

  const { winner, engagement_rate_a, engagement_rate_b } = engagement
  const maxRate = Math.max(engagement_rate_a, engagement_rate_b)
  // Bar width as percentage of max (min 10% so even 0% shows a sliver)
  const barWidthA = Math.max((engagement_rate_a / maxRate) * 100, 10)
  const barWidthB = Math.max((engagement_rate_b / maxRate) * 100, 10)

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4 space-y-3">
      {/* Header */}
      <div className="flex items-center gap-2">
        <TrendingUp size={16} className="text-blue-600" />
        <h3 className="text-sm font-semibold text-gray-900">Engagement Rate Comparison</h3>
      </div>

      {/* Bar A */}
      <div className="space-y-1">
        <div className="flex items-center justify-between text-xs">
          <span className="font-medium text-gray-700">
            Video A {winner === "A" && <span className="text-yellow-600 ml-1">👑</span>}
          </span>
          <span className="font-semibold text-gray-900">{engagement_rate_a.toFixed(1)}%</span>
        </div>
        <div className="w-full bg-gray-100 rounded-full h-3">
          <div
            className={`h-full rounded-full transition-all duration-700 ${
              winner === "A" ? "bg-blue-600" : "bg-gray-400"
            }`}
            style={{ width: `${barWidthA}%` }}
          />
        </div>
      </div>

      {/* Bar B */}
      <div className="space-y-1">
        <div className="flex items-center justify-between text-xs">
          <span className="font-medium text-gray-700">
            Video B {winner === "B" && <span className="text-yellow-600 ml-1">👑</span>}
          </span>
          <span className="font-semibold text-gray-900">{engagement_rate_b.toFixed(1)}%</span>
        </div>
        <div className="w-full bg-gray-100 rounded-full h-3">
          <div
            className={`h-full rounded-full transition-all duration-700 ${
              winner === "B" ? "bg-blue-600" : "bg-gray-400"
            }`}
            style={{ width: `${barWidthB}%` }}
          />
        </div>
      </div>

      {/* Winner text */}
      <p className="text-xs text-gray-500 text-center pt-1">
        {winner === "A"
          ? "Video A has higher engagement rate"
          : "Video B has higher engagement rate"}
      </p>
    </div>
  )
}
```

- Import `useEngageStore` and select `engagement`
- Return `null` if engagement is null
- Compute bar widths: each bar is `(rate / maxRate) * 100` percent, minimum 10%
- Winner bar gets `bg-blue-600`, loser gets `bg-gray-400`
- Header row with `TrendingUp` icon from lucide-react
- Each bar row: label with percentage on right, bar below
- Crown emoji 👑 next to winner label
- Summary text at bottom
- Pure CSS — no chart libraries used. The `transition-all duration-700` on bars gives a subtle animation on load
</action>

<acceptance_criteria>
  - `Frontend/src/components/chat/EngagementComparison.jsx` exists
  - `grep -n "engagement_rate_a" Frontend/src/components/chat/EngagementComparison.jsx` matches
  - `grep -n "engagement_rate_b" Frontend/src/components/chat/EngagementComparison.jsx` matches
  - `grep -n "rounded-full" Frontend/src/components/chat/EngagementComparison.jsx` matches (bar style)
  - `grep -n "bg-blue-600" Frontend/src/components/chat/EngagementComparison.jsx` matches (winner bar)
  - No chart library imports present (`grep -i "recharts\|chart\.js\|nivo\|victory" Frontend/src/components/chat/EngagementComparison.jsx` returns empty)
</acceptance_criteria>

<verify>
  <automated>node -e "const p='Frontend/src/components/chat/EngagementComparison.jsx';const fs=require('fs');if(!fs.existsSync(p)){console.error('MISSING: '+p);process.exit(1)}const c=fs.readFileSync(p,'utf8');if(/recharts|chart\.js|nivo|victory/i.test(c)){console.error('ERROR: Chart lib detected');process.exit(1)}console.log('OK: '+p + ' (no chart libs)')"</automated>
</verify>

<done>
EngagementComparison renders two horizontal bars comparing Video A and B engagement rates. Winner highlighted in blue, loser in gray. Crown indicator on winner label. Summary text below. No chart libraries used.
</done>
</task>

</tasks>

<verification>
- `npm run build` succeeds in Frontend/ directory
- All 3 chat analytics files exist
- No chart library dependencies imported
</verification>

<success_criteria>
- Header shows EngageX wordmark, RateLimitBadge, and "New Session" button that resets store and redirects
- VideoCard renders full metadata: platform badge, thumbnail/gradient, title, creator, follower count, views/likes/comments, engagement rate, hashtags, date, duration. Winner badge on higher-engagement card.
- EngagementComparison shows two CSS bars comparing rates with winner highlight
- Build passes without errors
</success_criteria>

<output>
After completion, create `.planning/phases/01-frontend-build/01-frontend-build-03-SUMMARY.md`
</output>
