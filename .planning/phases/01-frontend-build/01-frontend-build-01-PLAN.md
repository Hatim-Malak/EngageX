---
phase: 01-frontend-build
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - Frontend/src/App.jsx
  - Frontend/src/lib/utils.js
  - Frontend/src/components/shared/LoadingSpinner.jsx
  - Frontend/src/components/shared/ErrorBanner.jsx
  - Frontend/src/components/shared/RateLimitBadge.jsx
autonomous: true
requirements: [FE-10, FE-12]

must_haves:
  truths:
    - "App has two routes: / for landing and /chat for chat interface"
    - "Utility functions format numbers with K/M suffixes and seconds as MM:SS"
    - "LoadingSpinner renders a spinning animation with configurable size and color"
    - "ErrorBanner displays global errors from store with dismiss and auto-dismiss"
    - "RateLimitBadge shows queriesRemaining/queriesLimit with color coding"
  artifacts:
    - path: "Frontend/src/App.jsx"
      provides: "React Router routes and Toast container"
      contains: "BrowserRouter"
    - path: "Frontend/src/lib/utils.js"
      provides: "formatNumber and formatDuration exports"
      exports: ["formatNumber", "formatDuration"]
    - path: "Frontend/src/components/shared/LoadingSpinner.jsx"
      provides: "Animated loading spinner"
      exports: ["LoadingSpinner"]
    - path: "Frontend/src/components/shared/ErrorBanner.jsx"
      provides: "Global error display"
      exports: ["ErrorBanner"]
    - path: "Frontend/src/components/shared/RateLimitBadge.jsx"
      provides: "Rate limit indicator"
      exports: ["RateLimitBadge"]
  key_links:
    - from: "App.jsx"
      to: "react-router-dom"
      via: "BrowserRouter, Routes, Route"
      pattern: "BrowserRouter"
    - from: "App.jsx"
      to: "react-hot-toast"
      via: "Toaster component"
      pattern: "Toaster"
    - from: "RateLimitBadge.jsx"
      to: "useEngageStore"
      via: "queriesRemaining, queriesLimit selectors"
      pattern: "useEngageStore"
    - from: "ErrorBanner.jsx"
      to: "useEngageStore"
      via: "error, clearError selectors"
      pattern: "useEngageStore"
    - from: "VideoCard.jsx (Plan 03)"
      to: "lib/utils.js"
      via: "import formatNumber, formatDuration"
      pattern: "formatNumber|formatDuration"
---

<objective>
Create the foundation layer for the EngageX frontend: routing infrastructure, utility functions, and shared reusable components. These are consumed by all other plans.

Purpose: Establish the base layer so all component plans can import shared primitives without circular dependencies.
Output: App.jsx with routing, lib/utils.js, shared/LoadingSpinner.jsx, shared/ErrorBanner.jsx, shared/RateLimitBadge.jsx
</objective>

<execution_context>
@$HOME/.config/opencode/get-shit-done/workflows/execute-plan.md
@$HOME/.config/opencode/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/phases/01-frontend-build/01-frontend-build-CONTEXT.md
@Frontend/src/store/useEngageStore.js
@Frontend/src/store/api.js
@Frontend/src/main.jsx
</context>

<tasks>

<task type="auto">
<name>Task 1: Create utility functions (formatNumber, formatDuration)</name>
<files>
  Frontend/src/lib/utils.js
</files>

<read_first>
  Frontend/src/lib/utils.js (will create new file)
</read_first>

<action>
Create `Frontend/src/lib/utils.js` with two exported functions:

1. `formatNumber(n: number): string`
   - If n >= 1_000_000: return `(n / 1_000_000).toFixed(1).replace(/\.0$/, '') + 'M'`
     - Example: 4500000 → "4.5M", 1000000 → "1M"
   - If n >= 1_000: return `(n / 1_000).toFixed(1).replace(/\.0$/, '') + 'K'`
     - Example: 1234 → "1.2K", 5000 → "5K"
   - Otherwise: return `String(n)`
     - Example: 213 → "213"
   - Handle edge case n === 0: return "0"

2. `formatDuration(seconds: number): string`
   - Calculate minutes = Math.floor(seconds / 60)
   - Calculate secs = Math.floor(seconds % 60)
   - Return `${minutes}:${secs.toString().padStart(2, '0')}`
   - Example: 213 → "3:33", 60 → "1:00", 5 → "0:05"
   - Handle edge case seconds <= 0: return "0:00"

Use JSDoc comments for both functions with @param and @returns tags.
Use `export function` named exports (not default).
</action>

<acceptance_criteria>
  - File `Frontend/src/lib/utils.js` exists
  - `grep -n "export function formatNumber" Frontend/src/lib/utils.js` returns a match
  - `grep -n "export function formatDuration" Frontend/src/lib/utils.js` returns a match
  - `grep -n "1_000_000" Frontend/src/lib/utils.js` returns a match
  - `grep -n "padStart" Frontend/src/lib/utils.js` returns a match
  - File contains `@param` JSDoc tags
</acceptance_criteria>

<verify>
  <automated>node -e "
    const m = require('path'); const fs = require('fs');
    const code = fs.readFileSync('Frontend/src/lib/utils.js', 'utf8');
    // Quick eval check - extract functions
    const fnMatch = code.match(/export function formatNumber\s*\([^)]+\)\s*\{([^}]+)\}/);
    if (!fnMatch) process.exit(1);
    process.exit(0);
  " 2>&1 || echo "ERROR: formatNumber not found"</automated>
</verify>

<done>
formatNumber converts 1234 to "1.2K", 4500000 to "4.5M", 213 to "213". formatDuration converts 213 to "3:33", 60 to "1:00". Both functions handle edge cases.
</done>
</task>

<task type="auto">
<name>Task 2: Create shared UI components (LoadingSpinner, ErrorBanner, RateLimitBadge)</name>
<files>
  Frontend/src/components/shared/LoadingSpinner.jsx
  Frontend/src/components/shared/ErrorBanner.jsx
  Frontend/src/components/shared/RateLimitBadge.jsx
</files>

<read_first>
  Frontend/src/store/useEngageStore.js
</read_first>

<action>
Create three shared components:

### 1. LoadingSpinner.jsx
- Props: `size` (number, default 24), `color` (string, default "text-blue-500")
- Renders a `<div>` with Tailwind classes: `animate-spin rounded-full border-2 border-gray-300 border-t-current`
- The `size` prop sets `width` and `height` as inline styles: `{ width: size, height: size }`
- The `color` prop is applied as a className override
- The spinner uses Tailwind's `border-current` trick — the `color` class (e.g. `text-blue-500`) sets `currentColor` which the spinner uses for its animated arc
- Add `role="status"` and `aria-label="Loading"` for accessibility

### 2. ErrorBanner.jsx
- Imports `useEngageStore` from `../../store/useEngageStore`
- Selects: `const error = useEngageStore((s) => s.error)` and `const clearError = useEngageStore((s) => s.clearError)`
- Returns `null` if `error` is falsy
- When `error` is truthy, renders a fixed-bottom banner:
  ```jsx
  <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 bg-red-50 border border-red-200 text-red-800 px-4 py-3 rounded-lg shadow-lg max-w-md w-full">
    <span className="flex-1 text-sm">{error}</span>
    <button onClick={clearError} className="text-red-500 hover:text-red-700" aria-label="Dismiss">
      <X size={16} />
    </button>
  </div>
  ```
- Import `X` from `lucide-react`
- Uses `useEffect` to auto-dismiss after 5 seconds: `useEffect(() => { const t = setTimeout(clearError, 5000); return () => clearTimeout(t); }, [error])`
- Only one timer active at a time (error dependency in useEffect)

### 3. RateLimitBadge.jsx
- Imports `useEngageStore` from `../../store/useEngageStore`
- Selects: `queriesRemaining`, `queriesLimit`
- Computes color class:
  - `queriesRemaining > 20` → `"bg-green-100 text-green-800 border-green-200"`
  - `queriesRemaining >= 10` → `"bg-yellow-100 text-yellow-800 border-yellow-200"`
  - `queriesRemaining < 10` → `"bg-red-100 text-red-800 border-red-200"`
- Formats remaining as `Intl.NumberFormat().format(queriesRemaining)` — handles large numbers
- Renders:
  ```jsx
  <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${colorClass}`}>
    <span className={`w-1.5 h-1.5 rounded-full ${dotColor}`} />
    {queriesRemaining}/{queriesLimit} queries left
  </span>
  ```
</action>

<acceptance_criteria>
  - `Frontend/src/components/shared/LoadingSpinner.jsx` exists with `export default` and has `animate-spin`
  - `Frontend/src/components/shared/ErrorBanner.jsx` exists with `useEngageStore`, `clearError`, `useEffect`, `setTimeout`
  - `Frontend/src/components/shared/RateLimitBadge.jsx` exists with `queriesRemaining` and color class logic
  - `grep -n "animate-spin" Frontend/src/components/shared/LoadingSpinner.jsx` matches
  - `grep -n "fixed bottom-4" Frontend/src/components/shared/ErrorBanner.jsx` matches
  - `grep -n "bg-red-100" Frontend/src/components/shared/RateLimitBadge.jsx` matches
</acceptance_criteria>

<verify>
  <automated>node -e "const fs=require('fs'); ['LoadingSpinner','ErrorBanner','RateLimitBadge'].forEach(n=>{const p='Frontend/src/components/shared/'+n+'.jsx';if(!fs.existsSync(p)){console.error('MISSING: '+p);process.exit(1)}console.log('OK: '+p)});"</automated>
</verify>

<done>
Three shared components exist: LoadingSpinner (configurable spinner), ErrorBanner (fixed-bottom error with auto-dismiss), RateLimitBadge (color-coded remaining/total).
</done>
</task>

<task type="auto">
<name>Task 3: Set up App.jsx with React Router and Toaster</name>
<files>
  Frontend/src/App.jsx
</files>

<read_first>
  Frontend/src/App.jsx
</read_first>

<action>
Rewrite `Frontend/src/App.jsx`:

```jsx
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "react-hot-toast";
import Landing from "./pages/Landing";
import ErrorBanner from "./components/shared/ErrorBanner";

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
        <Route path="/chat" element={<div>Chat — Coming Soon</div>} />
      </Routes>
      <ErrorBanner />
    </BrowserRouter>
  );
}

export default App;
```

- Import `Landing` from `./pages/Landing` (will be created in Plan 02 — the placeholder message `"Chat — Coming Soon"` will be replaced in Plan 05)
- Keep `export default App;`
- The `/chat` route shows a temporary placeholder div until Plan 05 creates the real Chat page
- Toaster uses `top-center` position with 4s duration
</action>

<acceptance_criteria>
  - `grep -n "BrowserRouter" Frontend/src/App.jsx` returns a match
  - `grep -n "Toaster" Frontend/src/App.jsx` returns a match
  - `grep -n "ErrorBanner" Frontend/src/App.jsx` returns a match
  - File contains both route definitions: `path="/"` and `path="/chat"`
  - `grep -n "export default App" Frontend/src/App.jsx` matches
</acceptance_criteria>

<verify>
  <automated>cd Frontend && npx vite build 2>&1 | tail -5</automated>
</verify>

<done>
App.jsx renders BrowserRouter with two routes (/ and /chat), Toaster at top-center, and ErrorBanner fixed at bottom. Build succeeds.
</done>
</task>

</tasks>

<verification>
- `npm run build` succeeds in Frontend/ directory
- All five foundation files exist
- formatNumber and formatDuration handle edge cases correctly
</verification>

<success_criteria>
- App.jsx has working routing with react-router-dom for `/` and `/chat` routes
- lib/utils.js exports formatNumber and formatDuration with correct behavior
- LoadingSpinner renders with animate-spin and configurable size/color
- ErrorBanner displays global store errors with dismiss and 5s auto-dismiss
- RateLimitBadge shows colored badge based on remaining queries
- `npm run build` passes without errors
</success_criteria>

<output>
After completion, create `.planning/phases/01-frontend-build/01-frontend-build-01-SUMMARY.md`
</output>
