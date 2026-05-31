# Phase 01: Frontend Build — Context

**Gathered:** 2026-05-31
**Status:** Ready for planning
**Source:** User specification

---

## Domain

Build the complete frontend for EngageX — a RAG-powered video engagement analysis tool. Two videos (YouTube + Instagram Reel) are ingested, embedded, and stored. A creator then chats with an AI that compares them, explains engagement differences, and suggests improvements.

**Phase boundary:** All frontend UI components, pages, routing, state consumption, utility functions. Backend and AI services are already built. The Zustand store (`useEngageStore`) and API layer (`api.js`) are already written and MUST NOT be modified.

---

## Implementation Decisions (Locked)

### Tech Stack
- **Framework:** Vite + React 19 (JSX, not Next.js)
- **Routing:** react-router-dom v7
- **Styling:** Tailwind CSS only — no component libraries (shadcn, MUI, Chakra, etc.)
- **State:** Zustand via `useEngageStore` (already written — DO NOT MODIFY)
- **Icons:** lucide-react
- **Toast:** react-hot-toast (already used in store)
- **Env:** `VITE_API_BASE_URL=http://localhost:8000` (already in api.js)

### State Management Rules
- Never call the API directly — always use store actions
- Never modify the store — only read state and call actions
- Persist only `sessionId` in localStorage key `engagex_session_id`
- Import store like: `const { videoA, messages, sendStreamQuery, isStreaming } = useEngageStore()`

### Page 1 — `/` Landing Page
- Full-height centered layout, two columns on desktop, stacked on mobile
- `<UrlInputForm />`: Two inputs (YouTube + Instagram), submit calls `ingestVideos()`
- `<IngestProgressIndicator />`: 3 animated cosmetic steps shown during ingestion
- `<SessionRestorePrompt />`: Resume previous session card from localStorage
- On success: save `session_id` to localStorage → redirect to `/chat`

### Page 2 — `/chat` Chat Interface
- Three-panel layout: Video A card | Video B card | Chat panel
- On mobile: Video cards collapse to swipeable horizontal scroll row
- On page load: read sessionId from localStorage → `loadSession()` → redirect to `/` if invalid
- `<Header />`: Logo, rate limit badge, "New Session" button
- `<VideoCard />`: Platform badge, thumbnail, title, creator, stats, engagement rate, hashtags, winner indicator
- `<EngagementComparison />`: Pure CSS horizontal bar chart
- `<ChatPanel />` with `<MessageList />`, `<StreamingMessage />`, `<ChatInput />`, `<SuggestedQuestions />`, `<NewConversationButton />`
- `<CitationList />`: Clickable chips opening YouTube at timestamp
- SSE streaming handled entirely in store — components just call `sendStreamQuery()` and read `streamingResponse`
- Chat auto-scrolls to bottom on new messages
- On Enter (without Shift) submit, on Shift+Enter new line

### Error Handling
- `ingestError` → inline below form on landing page
- `sessionExists === false` → redirect to `/`
- `queriesRemaining === 0` → "Daily limit reached — resets at midnight UTC"
- `queryError` → error bubble in message list
- `error` (global) → `<ErrorBanner />` auto-dismiss after 5s
- Streaming aborted → message marked "_(cancelled)_" (store handles this)

### Performance
- No chart libraries — pure CSS bars
- No animation libraries — CSS transitions only
- Lazy load `/chat` page with React.lazy
- `messages[]` uses `key={index}` — capped at ~20, no virtualization
- Thumbnails use `<img>` with width/height (Vite, not Next.js Image)
- `<StreamingMessage />` in isolated component to prevent full message list re-render

### File Structure
```
Frontend/src/
  App.jsx                          ← Router setup with react-router-dom
  main.jsx                         ← Entry point (unchanged)
  index.css                        ← Tailwind directives (unchanged)
  pages/
    Landing.jsx                    ← Landing page
    Chat.jsx                       ← Chat page
  components/
    landing/
      UrlInputForm.jsx
      IngestProgressIndicator.jsx
      SessionRestorePrompt.jsx
    chat/
      Header.jsx
      VideoCard.jsx
      EngagementComparison.jsx
      ChatPanel.jsx
      MessageList.jsx
      StreamingMessage.jsx
      CitationList.jsx
      ChatInput.jsx
      SuggestedQuestions.jsx
      NewConversationButton.jsx
    shared/
      RateLimitBadge.jsx
      LoadingSpinner.jsx
      ErrorBanner.jsx
  store/
    useEngageStore.js               ← ALREADY WRITTEN — DO NOT MODIFY
    api.js                          ← ALREADY WRITTEN — DO NOT MODIFY
  lib/
    utils.js                        ← formatNumber, formatDuration
```

### Session Lifecycle on `/chat`
```
useEffect(() => {
  const saved = localStorage.getItem("engagex_session_id")
  if (!saved) { navigate("/"); return }
  loadSession(saved).then(data => {
    if (!data?.exists) { navigate("/"); return }
    loadHistory()
    fetchRateLimits()
  })
}, [])
```

---

## the agent's Discretion

- Exact Tailwind color scheme and spacing values
- CSS animation details for ingest progress indicator
- Mobile breakpoint values for responsive layout
- Specific loading spinner design
- Transition/animation durations
- How YouTube video ID is extracted from URL (regex implementation)
- Exact card shadow/border styles
- Chat bubble max-width percentages
- Scroll-to-bottom smooth vs instant behavior

---

## Deferred Ideas

- Dark mode
- Search/filter functionality
- User authentication/login
- Analytics dashboard
- Export/Share features
- Video preview/playback in app
- Multi-language support

---

*Phase: 01-frontend-build*
*Context gathered: 2026-05-31*
