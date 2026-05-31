---
phase: 01-frontend-build
plan: 02
type: execute
wave: 1
depends_on: []
files_modified:
  - Frontend/src/pages/Landing.jsx
  - Frontend/src/components/landing/UrlInputForm.jsx
  - Frontend/src/components/landing/IngestProgressIndicator.jsx
  - Frontend/src/components/landing/SessionRestorePrompt.jsx
autonomous: true
requirements: [FE-01, FE-02, FE-03]

must_haves:
  truths:
    - "User can see two URL input fields (YouTube + Instagram) on the landing page"
    - "User can submit URLs and see ingestion progress"
    - "User sees 3 animated steps during ingestion"
    - "User can restore a previous session from localStorage"
    - "On success, user is redirected to /chat"
  artifacts:
    - path: "Frontend/src/pages/Landing.jsx"
      provides: "Landing page layout composing all landing components"
      contains: "UrlInputForm"
    - path: "Frontend/src/components/landing/UrlInputForm.jsx"
      provides: "URL inputs and ingest trigger"
      contains: "ingestVideos"
    - path: "Frontend/src/components/landing/IngestProgressIndicator.jsx"
      provides: "3-step animated progress"
      contains: "ingesting"
    - path: "Frontend/src/components/landing/SessionRestorePrompt.jsx"
      provides: "Session restore card"
      contains: "engagex_session_id"
  key_links:
    - from: "UrlInputForm.jsx"
      to: "useEngageStore"
      via: "ingestVideos, ingesting, ingestResult, ingestError"
      pattern: "useEngageStore"
    - from: "Landing.jsx"
      to: "react-router-dom"
      via: "useNavigate for redirect after ingest"
      pattern: "useNavigate"
    - from: "SessionRestorePrompt.jsx"
      to: "localStorage"
      via: "localStorage.getItem('engagex_session_id')"
      pattern: "engagex_session_id"
---

<objective>
Build the landing page (route `/`) with URL input form, ingestion progress indicator, and session restore prompt.

Purpose: Users enter two video URLs to start analysis. The page handles the complete ingestion flow from input → progress → redirect.
Output: Landing.jsx, UrlInputForm.jsx, IngestProgressIndicator.jsx, SessionRestorePrompt.jsx
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
<name>Task 1: Create UrlInputForm component</name>
<files>
  Frontend/src/components/landing/UrlInputForm.jsx
</files>

<read_first>
  Frontend/src/store/useEngageStore.js
</read_first>

<action>
Create `Frontend/src/components/landing/UrlInputForm.jsx`:

- Import `useEngageStore` from `../../store/useEngageStore`
- Import `useNavigate` from `react-router-dom`
- Import `Loader2, ArrowRight` from `lucide-react`
- Local state: `urlA` (string, default ""), `urlB` (string, default ""), via `useState`

**Store selectors:**
```js
const ingestVideos = useEngageStore((s) => s.ingestVideos)
const ingesting = useEngageStore((s) => s.ingesting)
const ingestResult = useEngageStore((s) => s.ingestResult)
const ingestError = useEngageStore((s) => s.ingestError)
```

**Submit handler:**
```js
const handleSubmit = async (e) => {
  e.preventDefault()
  if (!urlA.trim() || !urlB.trim()) return
  await ingestVideos(urlA.trim(), urlB.trim())
}
```

**useEffect to redirect on success:**
```js
const navigate = useNavigate()
useEffect(() => {
  if (ingestResult) {
    localStorage.setItem("engagex_session_id", ingestResult.session_id)
    navigate("/chat")
  }
}, [ingestResult, navigate])
```

**Render:**
```jsx
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
      <><Loader2 size={18} className="animate-spin" /> Analyzing Videos...</>
    ) : (
      <><ArrowRight size={18} /> Analyze Videos</>
    )}
  </button>

  {/* Inline error */}
  {ingestError && (
    <p className="text-red-600 text-sm bg-red-50 border border-red-200 rounded-lg px-3 py-2">
      {ingestError}
    </p>
  )}
</form>
```

- Button disabled when either input empty OR `ingesting === true`
- Error shown inline in a styled red box when `ingestError` is truthy
- All inputs use `disabled={ingesting}` to prevent edits during ingestion
</action>

<acceptance_criteria>
  - File `Frontend/src/components/landing/UrlInputForm.jsx` exists
  - `grep -n "ingestVideos" Frontend/src/components/landing/UrlInputForm.jsx` matches
  - `grep -n "engagex_session_id" Frontend/src/components/landing/UrlInputForm.jsx` matches
  - `grep -n "youtube.com/watch" Frontend/src/components/landing/UrlInputForm.jsx` matches
  - `grep -n "instagram.com/reel" Frontend/src/components/landing/UrlInputForm.jsx` matches
  - `grep -n "ingestError" Frontend/src/components/landing/UrlInputForm.jsx` matches
  - `grep -n "Loader2" Frontend/src/components/landing/UrlInputForm.jsx` matches (loading spinner icon)
</acceptance_criteria>

<verify>
  <automated>node -e "const fs=require('fs');const p='Frontend/src/components/landing/UrlInputForm.jsx';fs.existsSync(p)?console.log('OK: '+p):(console.error('MISSING: '+p),process.exit(1))"</automated>
</verify>

<done>
UrlInputForm renders two URL inputs with labels, submit button that calls ingestVideos, shows loading state during ingestion, saves session_id to localStorage on success, navigates to /chat, and displays ingestError inline.
</done>
</task>

<task type="auto">
<name>Task 2: Create IngestProgressIndicator and SessionRestorePrompt</name>
<files>
  Frontend/src/components/landing/IngestProgressIndicator.jsx
  Frontend/src/components/landing/SessionRestorePrompt.jsx
</files>

<read_first>
  Frontend/src/store/useEngageStore.js
</read_first>

<action>
Create two components:

### 1. IngestProgressIndicator.jsx
- Import `useEngageStore` from `../../store/useEngageStore`
- Import `Check, Loader2` from `lucide-react`
- Import `useState, useEffect` from `react`
- Select `ingesting` from store
- Return `null` when `ingesting` is false (hidden when not ingesting)

Three animated steps:
```js
const STEPS = [
  { label: "Fetching transcripts & metadata", duration: 20 },
  { label: "Embedding with BGE-M3", duration: 20 },
  { label: "Storing in Pinecone", duration: 20 },
]
```

- Local state: `activeStep` (number, default -1)
- On mount when `ingesting` becomes true, start a timer chain:
  - `activeStep = 0` immediately
  - After 20s → `activeStep = 1`
  - After 40s → `activeStep = 2`
- Use `useEffect` with `setTimeout` for each transition
- Clear all timeouts on unmount or when `ingesting` becomes false
- Each step renders:
  ```jsx
  <div className="flex items-center gap-3" key={index}>
    <div className="w-6 h-6 flex items-center justify-center">
      {activeStep > index ? (
        <Check size={16} className="text-green-500" />  // completed
      ) : activeStep === index ? (
        <Loader2 size={16} className="animate-spin text-blue-500" />  // in progress
      ) : (
        <div className="w-2 h-2 rounded-full bg-gray-300" />  // pending
      )}
    </div>
    <span className={`text-sm ${
      activeStep > index ? "text-green-700" :
      activeStep === index ? "text-blue-700 font-medium" :
      "text-gray-400"
    }`}>
      {step.label}
    </span>
  </div>
  ```
- Wrap in a container: `bg-white border border-gray-200 rounded-lg p-4 space-y-3`

### 2. SessionRestorePrompt.jsx
- Import `useState, useEffect` from `react`
- Import `useNavigate` from `react-router-dom`
- Import `useEngageStore` from `../../store/useEngageStore`
- Import `X` from `lucide-react`
- Local state: `dismissed` (boolean, default false)
- Select `loadSession` from store

```jsx
const savedId = typeof window !== "undefined" ? localStorage.getItem("engagex_session_id") : null
const navigate = useNavigate()
```

- If `savedId` is null OR `dismissed` is true → return null
- On "Resume" click:
  ```js
  const handleResume = async () => {
    await loadSession(savedId)
    navigate("/chat")
  }
  ```
- On dismiss (X button):
  ```js
  const handleDismiss = () => {
    localStorage.removeItem("engagex_session_id")
    setDismissed(true)
  }
  ```

- Render:
  ```jsx
  <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 flex items-center justify-between">
    <div>
      <p className="text-sm font-medium text-blue-900">Resume previous session?</p>
      <p className="text-xs text-blue-700 mt-0.5">Pick up where you left off</p>
    </div>
    <div className="flex items-center gap-2">
      <button
        onClick={handleResume}
        className="bg-blue-600 text-white px-3 py-1.5 rounded-md text-sm font-medium hover:bg-blue-700 transition-colors"
      >
        Resume
      </button>
      <button
        onClick={handleDismiss}
        className="text-blue-400 hover:text-blue-600 p-1"
        aria-label="Dismiss"
      >
        <X size={16} />
      </button>
    </div>
  </div>
  ```
</action>

<acceptance_criteria>
  - `Frontend/src/components/landing/IngestProgressIndicator.jsx` exists
  - `grep -n "Fetching transcripts" Frontend/src/components/landing/IngestProgressIndicator.jsx` matches
  - `grep -n "BGE-M3" Frontend/src/components/landing/IngestProgressIndicator.jsx` matches
  - `grep -n "Pinecone" Frontend/src/components/landing/IngestProgressIndicator.jsx` matches
  - `grep -n "useEffect" Frontend/src/components/landing/IngestProgressIndicator.jsx` matches
  - `Frontend/src/components/landing/SessionRestorePrompt.jsx` exists
  - `grep -n "engagex_session_id" Frontend/src/components/landing/SessionRestorePrompt.jsx` matches
  - `grep -n "Resume previous session" Frontend/src/components/landing/SessionRestorePrompt.jsx` matches
  - `grep -n "localStorage.removeItem" Frontend/src/components/landing/SessionRestorePrompt.jsx` matches
</acceptance_criteria>

<verify>
  <automated>node -e "const fs=require('fs');['IngestProgressIndicator','SessionRestorePrompt'].forEach(n=>{const p='Frontend/src/components/landing/'+n+'.jsx';if(!fs.existsSync(p)){console.error('MISSING: '+p);process.exit(1)}console.log('OK: '+p)})"</automated>
</verify>

<done>
IngestProgressIndicator shows 3 animated steps sequentially during ingestion (20s apart, cosmetic only). SessionRestorePrompt shows a resume card when localStorage has a sessionId, with Resume and Dismiss actions.
</done>
</task>

<task type="auto">
<name>Task 3: Create Landing page composing all landing components</name>
<files>
  Frontend/src/pages/Landing.jsx
</files>

<read_first>
  Frontend/src/components/landing/UrlInputForm.jsx (sketch — to understand its interface)
  Frontend/src/components/landing/IngestProgressIndicator.jsx (sketch)
  Frontend/src/components/landing/SessionRestorePrompt.jsx (sketch)
</read_first>

<action>
Create `Frontend/src/pages/Landing.jsx`:

```jsx
import UrlInputForm from "../components/landing/UrlInputForm"
import IngestProgressIndicator from "../components/landing/IngestProgressIndicator"
import SessionRestorePrompt from "../components/landing/SessionRestorePrompt"

export default function Landing() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-blue-50 flex items-center justify-center p-4">
      <div className="w-full max-w-4xl">
        {/* Hero section */}
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold text-gray-900 tracking-tight">
            EngageX
          </h1>
          <p className="mt-2 text-gray-600 text-lg">
            Compare YouTube and Instagram engagement with AI-powered analysis
          </p>
        </div>

        {/* Main card */}
        <div className="bg-white rounded-xl shadow-lg border border-gray-200 overflow-hidden">
          {/* Two-column layout on desktop, stacked on mobile */}
          <div className="flex flex-col md:flex-row">
            {/* Left: Form */}
            <div className="flex-1 p-6 md:p-8">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">
                Analyze Your Videos
              </h2>
              <UrlInputForm />
            </div>

            {/* Right: Info / Steps */}
            <div className="flex-1 bg-gray-50 p-6 md:p-8 border-t md:border-t-0 md:border-l border-gray-200">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">
                How It Works
              </h2>
              <ol className="space-y-4">
                {[
                  ["Paste URLs", "Add a YouTube and Instagram Reel link"],
                  ["AI Analysis", "Our engine extracts transcripts, metadata, and engagement data"],
                  ["Smart Chat", "Ask questions and get comparative insights"],
                ].map(([title, desc], i) => (
                  <li key={i} className="flex gap-3">
                    <span className="flex-shrink-0 w-7 h-7 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-sm font-semibold">
                      {i + 1}
                    </span>
                    <div>
                      <p className="font-medium text-gray-900 text-sm">{title}</p>
                      <p className="text-gray-500 text-sm">{desc}</p>
                    </div>
                  </li>
                ))}
              </ol>
            </div>
          </div>

          {/* Progress indicator (below card, only visible during ingestion) */}
          <IngestProgressIndicator />
        </div>

        {/* Session restore prompt below the main card */}
        <div className="mt-6">
          <SessionRestorePrompt />
        </div>
      </div>
    </div>
  )
}
```

- Layout: full-viewport height (`min-h-screen`), centered content
- Background: subtle gradient `from-gray-50 to-blue-50`
- Two-column on desktop (`md:flex-row`), stacked on mobile
- Left column: form with "Analyze Your Videos" heading
- Right column: "How It Works" numbered steps
- IngestProgressIndicator placed inside/after the card (cosmetic)
- SessionRestorePrompt below the main card
- No store imports needed — all data flow happens through child components
</action>

<acceptance_criteria>
  - `Frontend/src/pages/Landing.jsx` exists
  - `grep -n "UrlInputForm" Frontend/src/pages/Landing.jsx` matches
  - `grep -n "IngestProgressIndicator" Frontend/src/pages/Landing.jsx` matches
  - `grep -n "SessionRestorePrompt" Frontend/src/pages/Landing.jsx` matches
  - `grep -n "md:flex-row" Frontend/src/pages/Landing.jsx` matches (responsive layout)
  - `grep -n "export default function Landing" Frontend/src/pages/Landing.jsx` matches
</acceptance_criteria>

<verify>
  <automated>cd Frontend && npx vite build 2>&1 | tail -5</automated>
</verify>

<done>
Landing.jsx renders a full-height centered layout with two-column desktop / stacked mobile design, composes UrlInputForm, IngestProgressIndicator, and SessionRestorePrompt. Build succeeds.
</done>
</task>

</tasks>

<verification>
- `npm run build` succeeds in Frontend/ directory
- All 4 landing files exist
- Landing page renders without JS errors
</verification>

<success_criteria>
- Landing page shows at route `/` with full-height centered layout
- Two-column layout on desktop (form left, instructions right), stacked on mobile
- URL inputs for YouTube and Instagram with proper labels and placeholders
- Submit button triggers `ingestVideos()` and shows loading state
- On success: saves session_id to localStorage, navigates to /chat
- On error: shows inline error message below form
- IngestProgressIndicator shows 3 animated steps during ingestion
- SessionRestorePrompt shows when localStorage has a saved session with Resume/Dismiss
- Build passes without errors
</success_criteria>

<output>
After completion, create `.planning/phases/01-frontend-build/01-frontend-build-02-SUMMARY.md`
</output>
