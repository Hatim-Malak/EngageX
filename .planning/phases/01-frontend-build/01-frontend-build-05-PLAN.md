---
phase: 01-frontend-build
plan: 05
type: execute
wave: 3
depends_on:
  - 01-frontend-build-01
  - 01-frontend-build-03
  - 01-frontend-build-04
files_modified:
  - Frontend/src/pages/Chat.jsx
  - Frontend/src/App.jsx
autonomous: true
requirements: [FE-04, FE-11]

must_haves:
  truths:
    - "Chat page loads with session validation — redirects to / if no valid session"
    - "Three-panel layout renders: Video A card | Video B card | Chat panel"
    - "On mobile, video cards collapse to horizontal scroll row"
    - "EngagementComparison is visible between or below video cards"
    - "Header with EngageX logo and controls is at the top"
    - "Chat page is lazy-loaded via React.lazy for performance"
  artifacts:
    - path: "Frontend/src/pages/Chat.jsx"
      provides: "Full chat page with session lifecycle and three-panel layout"
      contains: "Header, VideoCard, EngagementComparison, ChatPanel"
    - path: "Frontend/src/App.jsx"
      provides: "Updated route with React.lazy for /chat"
      contains: "lazy("
  key_links:
    - from: "Chat.jsx"
      to: "useEngageStore"
      via: "loadSession, loadHistory, fetchRateLimits, videoA, videoB, engagement"
      pattern: "loadSession"
    - from: "Chat.jsx"
      to: "localStorage"
      via: "localStorage.getItem('engagex_session_id')"
      pattern: "engagex_session_id"
    - from: "Chat.jsx"
      to: "react-router-dom"
      via: "useNavigate for redirect"
      pattern: "useNavigate"
    - from: "App.jsx (updated)"
      to: "React.lazy"
      via: "lazy(() => import('./pages/Chat'))"
      pattern: "React.lazy|lazy("
---

<objective>
Wire up the full chat page: session initialization, three-panel responsive layout, lazy loading, and composition of all chat components.

Purpose: This is the assembly plan that connects all chat components together with the session lifecycle and responsive layout.
Output: Chat.jsx, App.jsx (updated with lazy loading)
</objective>

<execution_context>
@$HOME/.config/opencode/get-shit-done/workflows/execute-plan.md
@$HOME/.config/opencode/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/01-frontend-build/01-frontend-build-CONTEXT.md
@Frontend/src/store/useEngageStore.js
@Frontend/src/components/chat/Header.jsx
@Frontend/src/components/chat/VideoCard.jsx
@Frontend/src/components/chat/EngagementComparison.jsx
@Frontend/src/components/chat/ChatPanel.jsx
</context>

<tasks>

<task type="auto">
<name>Task 1: Create Chat page with session lifecycle and three-panel layout</name>
<files>
  Frontend/src/pages/Chat.jsx
</files>

<read_first>
  Frontend/src/store/useEngageStore.js
  Frontend/src/components/chat/Header.jsx
  Frontend/src/components/chat/VideoCard.jsx
  Frontend/src/components/chat/EngagementComparison.jsx
  Frontend/src/components/chat/ChatPanel.jsx
</read_first>

<action>
Create `Frontend/src/pages/Chat.jsx`:

```jsx
import { useEffect } from "react"
import { useNavigate } from "react-router-dom"
import useEngageStore from "../store/useEngageStore"
import Header from "../components/chat/Header"
import VideoCard from "../components/chat/VideoCard"
import EngagementComparison from "../components/chat/EngagementComparison"
import ChatPanel from "../components/chat/ChatPanel"
import LoadingSpinner from "../components/shared/LoadingSpinner"

export default function Chat() {
  const navigate = useNavigate()

  // Store selectors
  const loadSession = useEngageStore((s) => s.loadSession)
  const loadHistory = useEngageStore((s) => s.loadHistory)
  const fetchRateLimits = useEngageStore((s) => s.fetchRateLimits)
  const sessionLoading = useEngageStore((s) => s.sessionLoading)
  const sessionExists = useEngageStore((s) => s.sessionExists)
  const videoA = useEngageStore((s) => s.videoA)
  const videoB = useEngageStore((s) => s.videoB)
  const engagement = useEngageStore((s) => s.engagement)

  // Session initialization
  useEffect(() => {
    const initSession = async () => {
      const saved = localStorage.getItem("engagex_session_id")
      if (!saved) {
        navigate("/", { replace: true })
        return
      }

      const data = await loadSession(saved)
      if (!data || !data.exists) {
        localStorage.removeItem("engagex_session_id")
        navigate("/", { replace: true })
        return
      }

      // Session valid — load conversation history and rate limits
      await loadHistory()
      await fetchRateLimits()
    }

    initSession()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Loading state
  if (sessionLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <LoadingSpinner size={32} color="text-blue-500" />
          <p className="mt-3 text-sm text-gray-500">Loading session...</p>
        </div>
      </div>
    )
  }

  // If session doesn't exist after load, wait for redirect
  if (!sessionExists) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <p className="text-sm text-gray-400">Redirecting...</p>
      </div>
    )
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
              <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Video A</span>
              {engagement?.winner === "A" && (
                <span className="text-xs bg-yellow-100 text-yellow-800 px-1.5 py-0.5 rounded-full">Winner</span>
              )}
            </div>
            <VideoCard video={videoA} label="A" isWinner={engagement?.winner === "A"} />
          </div>

          {/* Video B card */}
          <div className="min-w-[260px] md:min-w-0 flex-shrink-0 md:flex-shrink">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Video B</span>
              {engagement?.winner === "B" && (
                <span className="text-xs bg-yellow-100 text-yellow-800 px-1.5 py-0.5 rounded-full">Winner</span>
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
  )
}
```

**Key behaviors:**

1. **Session initialization** (exact same as spec):
   ```
   useEffect(() => {
     const saved = localStorage.getItem("engagex_session_id")
     if (!saved) { navigate("/", { replace: true }); return }
     loadSession(saved).then(data => {
       if (!data?.exists) {
         localStorage.removeItem("engagex_session_id")
         navigate("/", { replace: true })
         return
       }
       loadHistory()
       fetchRateLimits()
     })
   }, [])
   ```

2. **Loading states:**
   - `sessionLoading` → centered spinner with "Loading session..."
   - Session doesn't exist after load → "Redirecting..." text
   - After valid session → render full layout

3. **Desktop layout** (`md:` breakpoint and up):
   - Full viewport height (`min-h-screen flex flex-col`)
   - Header at top
   - Below header: `flex-row` with three areas:
     - Left sidebar (`md:w-72 lg:w-80`): Video A card stacked above Video B card, EngagementComparison below cards
     - Right area (`flex-1`): ChatPanel in a white card with border and shadow
   - Video area is `flex md:flex-col gap-4` — horizontal on mobile, vertical on desktop

4. **Mobile layout** (below `md:` breakpoint):
   - Video cards in a horizontal scroll row (`overflow-x-auto`, `flex-nowrap`)
   - Each card has `min-w-[260px]` with `flex-shrink-0`
   - EngagementComparison rendered below the scroll row (outside the `md:hidden` block)
   - ChatPanel takes full width below engagement

5. **Engagement winner labels:** Each video section shows a "Winner" badge in yellow (`bg-yellow-100 text-yellow-800`) when that video is the engagement winner
</action>

<acceptance_criteria>
  - `Frontend/src/pages/Chat.jsx` exists
  - `grep -n "loadSession" Frontend/src/pages/Chat.jsx` matches
  - `grep -n "loadHistory" Frontend/src/pages/Chat.jsx` matches
  - `grep -n "fetchRateLimits" Frontend/src/pages/Chat.jsx` matches
  - `grep -n "engagex_session_id" Frontend/src/pages/Chat.jsx` matches
  - `grep -n "navigate.*replace" Frontend/src/pages/Chat.jsx` matches (redirect with replace)
  - `grep -n "Header" Frontend/src/pages/Chat.jsx` matches
  - `grep -n "VideoCard" Frontend/src/pages/Chat.jsx` matches (used twice)
  - `grep -n "EngagementComparison" Frontend/src/pages/Chat.jsx` matches
  - `grep -n "ChatPanel" Frontend/src/pages/Chat.jsx` matches
  - `grep -n "md:flex-row" Frontend/src/pages/Chat.jsx` matches (desktop layout)
  - `grep -n "overflow-x-auto" Frontend/src/pages/Chat.jsx` matches (mobile scroll)
  - `grep -n "LoadingSpinner" Frontend/src/pages/Chat.jsx` matches
</acceptance_criteria>

<verify>
  <automated>node -e "const fs=require('fs');const p='Frontend/src/pages/Chat.jsx';if(!fs.existsSync(p)){console.error('MISSING: '+p);process.exit(1)}const c=fs.readFileSync(p,'utf8');const checks=['loadSession','loadHistory','fetchRateLimits','Header','VideoCard','EngagementComparison','ChatPanel'];const missing=checks.filter(ch=>!c.includes(ch));if(missing.length>0){console.error('MISSING imports/usage: '+missing.join(', '));process.exit(1)}console.log('OK: '+p)"</automated>
</verify>

<done>
Chat.jsx initializes session from localStorage (redirecting to / on failure), renders three-panel layout (Header, video cards sidebar + engagement comparison, ChatPanel), handles loading states, and is responsive (desktop flex-row, mobile stacked with scrollable video row).
</done>
</task>

<task type="auto">
<name>Task 2: Update App.jsx with React.lazy for Chat page</name>
<files>
  Frontend/src/App.jsx
</files>

<read_first>
  Frontend/src/App.jsx (currently has placeholder route for /chat)
</read_first>

<action>
Update `Frontend/src/App.jsx` to add lazy loading for the Chat page.

**Read the current App.jsx first** to see the existing structure (it should have BrowserRouter, Toaster, Routes, Route for / and /chat, ErrorBanner).

Add at the top of imports:
```jsx
import { lazy, Suspense } from "react"
```

Replace the direct import of Chat (which doesn't exist yet) with:
```jsx
const Chat = lazy(() => import("./pages/Chat"))
```

Replace the `/chat` route element from:
```jsx
<Route path="/chat" element={<div>Chat — Coming Soon</div>} />
```
To:
```jsx
<Route
  path="/chat"
  element={
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <p className="text-sm text-gray-400">Loading chat...</p>
      </div>
    }>
      <Chat />
    </Suspense>
  }
/>
```

The final App.jsx should look like:
```jsx
import { lazy, Suspense } from "react"
import { BrowserRouter, Routes, Route } from "react-router-dom"
import { Toaster } from "react-hot-toast"
import Landing from "./pages/Landing"
import ErrorBanner from "./components/shared/ErrorBanner"

const Chat = lazy(() => import("./pages/Chat"))

function App() {
  return (
    <BrowserRouter>
      <Toaster
        position="top-center"
        toastOptions={{
          duration: 4000,
          style: { fontSize: "14px" },
        }}
      />
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route
          path="/chat"
          element={
            <Suspense fallback={
              <div className="min-h-screen flex items-center justify-center bg-gray-50">
                <p className="text-sm text-gray-400">Loading chat...</p>
              </div>
            }>
              <Chat />
            </Suspense>
          }
        />
      </Routes>
      <ErrorBanner />
    </BrowserRouter>
  )
}

export default App
```

- Keep `Landing` as a direct import (it's needed immediately for the home page)
- Only `Chat` is lazy-loaded (per the spec requirement)
- Suspense fallback shows a centered "Loading chat..." message while the chunk loads
</action>

<acceptance_criteria>
  - `grep -n "lazy" Frontend/src/App.jsx` matches
  - `grep -n "Suspense" Frontend/src/App.jsx` matches
  - `grep -n "lazy(() => import" Frontend/src/App.jsx` matches
  - `grep -n "Loading chat" Frontend/src/App.jsx` matches (fallback content)
  - No direct import of Chat page: `!grep -q "from.*Chat" Frontend/src/App.jsx` should be true for lazy import (but we have `const Chat = lazy(...)` so check that pattern instead)
  - `grep -n "const Chat =" Frontend/src/App.jsx` matches (lazy definition)
</acceptance_criteria>

<verify>
  <automated>cd Frontend && npx vite build 2>&1 | tail -5</automated>
</verify>

<done>
App.jsx uses React.lazy for the Chat page with Suspense fallback. Build succeeds with Chat page included in a separate chunk.
</done>
</task>

</tasks>

<verification>
- `npm run build` succeeds in Frontend/ directory
- Chat page exists at `/chat` route
- Session lifecycle works: redirects to `/` when no session, loads history when valid
- Responsive layout: three panels on desktop, stacked on mobile
- All components compose without errors
</verification>

<success_criteria>
- Chat.jsx handles session init: read localStorage → loadSession → redirect to / on failure → loadHistory + fetchRateLimits on success
- Three-panel layout renders: video cards sidebar + EngagementComparison (left), ChatPanel (right) on desktop
- Mobile layout stacks vertically with horizontal-scrolling video cards
- Loading states shown during session initialization
- App.jsx lazy-loads Chat page with React.lazy + Suspense
- Full build succeeds with code splitting
</success_criteria>

<output>
After completion, create `.planning/phases/01-frontend-build/01-frontend-build-05-SUMMARY.md`
</output>
