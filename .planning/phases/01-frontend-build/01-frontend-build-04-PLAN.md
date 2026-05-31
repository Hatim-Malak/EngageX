---
phase: 01-frontend-build
plan: 04
type: execute
wave: 2
depends_on:
  - 01-frontend-build-01
files_modified:
  - Frontend/src/components/chat/ChatInput.jsx
  - Frontend/src/components/chat/CitationList.jsx
  - Frontend/src/components/chat/MessageList.jsx
  - Frontend/src/components/chat/StreamingMessage.jsx
  - Frontend/src/components/chat/SuggestedQuestions.jsx
  - Frontend/src/components/chat/NewConversationButton.jsx
  - Frontend/src/components/chat/ChatPanel.jsx
autonomous: true
requirements: [FE-07, FE-08, FE-09]

must_haves:
  truths:
    - "User can type a message in a textarea and send it"
    - "User can stop an active streaming response"
    - "User sees messages rendered with user right-aligned and assistant left-aligned"
    - "User sees a blinking cursor on streaming messages"
    - "User sees suggested questions when chat is empty"
    - "User can click a suggested question to send it"
    - "User can click citation chips to open YouTube at timestamps"
    - "User can start a new conversation without losing session"
    - "User sees 'Daily limit reached' when queriesRemaining is 0"
    - "Chat panel auto-scrolls to bottom on new messages"
  artifacts:
    - path: "Frontend/src/components/chat/ChatInput.jsx"
      provides: "Message input with send/stop buttons"
      contains: "sendStreamQuery, abortStream"
    - path: "Frontend/src/components/chat/CitationList.jsx"
      provides: "Clickable citation chips"
      contains: "timestamp_start, timestamp_end"
    - path: "Frontend/src/components/chat/MessageList.jsx"
      provides: "Message bubble rendering"
      contains: "messages"
    - path: "Frontend/src/components/chat/StreamingMessage.jsx"
      provides: "Live streaming response display"
      contains: "streamingResponse, isStreaming"
    - path: "Frontend/src/components/chat/SuggestedQuestions.jsx"
      provides: "Clickable question chips"
      contains: "sendStreamQuery"
    - path: "Frontend/src/components/chat/NewConversationButton.jsx"
      provides: "Clears conversation history"
      contains: "clearHistory"
    - path: "Frontend/src/components/chat/ChatPanel.jsx"
      provides: "Panel composing all chat sub-components"
      contains: "ChatInput, MessageList, StreamingMessage"
  key_links:
    - from: "ChatPanel.jsx"
      to: "useEngageStore"
      via: "messages, queryError"
      pattern: "useEngageStore"
    - from: "ChatInput.jsx"
      to: "useEngageStore"
      via: "sendStreamQuery, abortStream, isStreaming, queryLoading, queriesRemaining"
      pattern: "sendStreamQuery"
    - from: "StreamingMessage.jsx"
      to: "useEngageStore"
      via: "streamingResponse, isStreaming"
      pattern: "streamingResponse"
    - from: "CitationList.jsx"
      to: "window.open"
      via: "YouTube URLs at timestamp"
      pattern: "youtube.com/watch"
---

<objective>
Build all chat conversation components: input, message display, streaming response, citations, suggested questions, and the panel that composes them.

Purpose: These form the rightmost panel of the three-panel chat layout — the core interaction surface where users query the AI and see responses.
Output: ChatInput.jsx, CitationList.jsx, MessageList.jsx, StreamingMessage.jsx, SuggestedQuestions.jsx, NewConversationButton.jsx, ChatPanel.jsx
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
<name>Task 1: Create ChatInput and CitationList components</name>
<files>
  Frontend/src/components/chat/ChatInput.jsx
  Frontend/src/components/chat/CitationList.jsx
</files>

<read_first>
  Frontend/src/store/useEngageStore.js
</read_first>

<action>
Create two components:

### 1. ChatInput.jsx
- Import `useState, useRef, useEffect` from `react`
- Import `useEngageStore` from `../../store/useEngageStore`
- Import `Send, Square` from `lucide-react`

**Store selectors:**
```js
const sendStreamQuery = useEngageStore((s) => s.sendStreamQuery)
const abortStream = useEngageStore((s) => s.abortStream)
const isStreaming = useEngageStore((s) => s.isStreaming)
const queryLoading = useEngageStore((s) => s.queryLoading)
const queriesRemaining = useEngageStore((s) => s.queriesRemaining)
```

- Local state: `input` (string, default "")
- Textarea ref for auto-resize

**Auto-resize handler:**
```js
const textareaRef = useRef(null)
const adjustHeight = () => {
  const el = textareaRef.current
  if (el) {
    el.style.height = "auto"
    el.style.height = Math.min(el.scrollHeight, 120) + "px" // max 4 rows ~120px
  }
}
```

**Submit handler:**
```js
const handleSubmit = async () => {
  const trimmed = input.trim()
  if (!trimmed || isStreaming || queryLoading) return
  setInput("")
  // Reset textarea height
  if (textareaRef.current) textareaRef.current.style.height = "auto"
  await sendStreamQuery(trimmed)
}
```

**Keydown handler:**
```js
const handleKeyDown = (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault()
    handleSubmit()
  }
  // Shift+Enter = new line (default behavior)
}
```

**Stop handler:**
```js
const handleStop = () => {
  abortStream()
}
```

**Render — rate limit exhausted:**
```jsx
if (queriesRemaining === 0) {
  return (
    <div className="p-4 border-t border-gray-200 bg-gray-50">
      <p className="text-sm text-center text-orange-600 font-medium">
        Daily limit reached — resets at midnight UTC
      </p>
    </div>
  )
}
```

**Render — normal input:**
```jsx
<div className="border-t border-gray-200 p-3 bg-white">
  <div className="flex items-end gap-2">
    <textarea
      ref={textareaRef}
      value={input}
      onChange={(e) => { setInput(e.target.value); adjustHeight() }}
      onKeyDown={handleKeyDown}
      placeholder="Ask about your videos..."
      disabled={isStreaming || queryLoading}
      rows={1}
      className="flex-1 resize-none border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:opacity-50 disabled:cursor-not-allowed outline-none"
    />
    {isStreaming ? (
      <button
        onClick={handleStop}
        className="flex-shrink-0 bg-red-500 text-white p-2.5 rounded-lg hover:bg-red-600 transition-colors"
        aria-label="Stop streaming"
        title="Stop"
      >
        <Square size={18} />
      </button>
    ) : (
      <button
        onClick={handleSubmit}
        disabled={!input.trim() || queryLoading}
        className="flex-shrink-0 bg-blue-600 text-white p-2.5 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        aria-label="Send message"
        title="Send"
      >
        <Send size={18} />
      </button>
    )}
  </div>
</div>
```

- Textarea auto-resizes to content (max ~120px)
- Send button: Arrow icon, disabled when input empty or loading
- Stop button: Square icon, shown only during streaming
- Loading state: textarea disabled while streaming
- Enter (without Shift) → submit. Shift+Enter → new line
- queriesRemaining === 0 → show "Daily limit reached" message instead of input

### 2. CitationList.jsx
- Props: `citations` — array of `{video_id: "A"|"B", timestamp_start: "MM:SS", timestamp_end: "MM:SS"}`

```jsx
import { ExternalLink, Clock } from "lucide-react"

export default function CitationList({ citations }) {
  if (!citations || citations.length === 0) return null

  // Convert "MM:SS" to seconds for YouTube timestamp parameter
  const toSeconds = (timestamp) => {
    const [m, s] = timestamp.split(":").map(Number)
    return m * 60 + s
  }

  const handleCitationClick = (citation) => {
    if (citation.video_id === "A") {
      // YouTube — open at timestamp
      const seconds = toSeconds(citation.timestamp_start)
      window.open(`https://youtube.com/watch?v=${VIDEO_ID_A}&t=${seconds}`, "_blank", "noopener")
    } else {
      // Instagram — show toast
      toast("Open Instagram to view at this timestamp", { icon: "📱" })
    }
  }

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
  )
}
```

- Import `toast` from `react-hot-toast`
- For Video A citations (YouTube): `window.open` with `https://youtube.com/watch?v={VIDEO_ID}&t={seconds}`
- Need to get VIDEO_ID_A — this is the YouTube video ID. Create a helper to extract it from the video URL. Since CitationList doesn't have direct access to videoA URL, we'll need to get it from the store:
  ```js
  import useEngageStore from "../../store/useEngageStore"
  const videoA = useEngageStore((s) => s.videoA)
  const getYoutubeId = (url) => {
    const match = url?.match(/(?:v=|youtu\.be\/)([^&?/]+)/)
    return match ? match[1] : null
  }
  const VIDEO_ID_A = getYoutubeId(videoA?.url)
  ```
- For Video B (Instagram): `toast("Open Instagram to view at this timestamp", { icon: "📱" })`
- Each citation renders as a small rounded chip with Clock icon and timestamp range
- Return null if citations is empty/null/undefined
</action>

<acceptance_criteria>
  - `Frontend/src/components/chat/ChatInput.jsx` exists
  - `grep -n "sendStreamQuery" Frontend/src/components/chat/ChatInput.jsx` matches
  - `grep -n "abortStream" Frontend/src/components/chat/ChatInput.jsx` matches
  - `grep -n "queriesRemaining" Frontend/src/components/chat/ChatInput.jsx` matches
  - `grep -n "Daily limit reached" Frontend/src/components/chat/ChatInput.jsx` matches
  - `Frontend/src/components/chat/CitationList.jsx` exists
  - `grep -n "youtube.com/watch" Frontend/src/components/chat/CitationList.jsx` matches
  - `grep -n "toSeconds" Frontend/src/components/chat/CitationList.jsx` matches
</acceptance_criteria>

<verify>
  <automated>node -e "const fs=require('fs');['ChatInput','CitationList'].forEach(n=>{const p='Frontend/src/components/chat/'+n+'.jsx';if(!fs.existsSync(p)){console.error('MISSING: '+p);process.exit(1)}console.log('OK: '+p)})"</automated>
</verify>

<done>
ChatInput renders auto-resizing textarea with Send button, Stop button during streaming, disabled when queriesRemaining=0 with "Daily limit reached" message. CitationList renders clickable chips opening YouTube at timestamps or showing toast for Instagram.
</done>
</task>

<task type="auto">
<name>Task 2: Create MessageList, StreamingMessage, SuggestedQuestions, NewConversationButton</name>
<files>
  Frontend/src/components/chat/MessageList.jsx
  Frontend/src/components/chat/StreamingMessage.jsx
  Frontend/src/components/chat/SuggestedQuestions.jsx
  Frontend/src/components/chat/NewConversationButton.jsx
</files>

<read_first>
  Frontend/src/store/useEngageStore.js
</read_first>

<action>
Create four components:

### 1. MessageList.jsx
- Import `useRef, useEffect` from `react`
- Import `useEngageStore` from `../../store/useEngageStore`
- Import `CitationList` from `./CitationList`
- Import `StreamingMessage` from `./StreamingMessage`

```jsx
import { useRef, useEffect } from "react"
import useEngageStore from "../../store/useEngageStore"
import CitationList from "./CitationList"
import StreamingMessage from "./StreamingMessage"

export default function MessageList() {
  const messages = useEngageStore((s) => s.messages)
  const queryError = useEngageStore((s) => s.queryError)
  const bottomRef = useRef(null)

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-4">
      {messages.length === 0 ? (
        <p className="text-center text-gray-400 text-sm mt-8">No messages yet. Ask a question to get started.</p>
      ) : (
        messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[75%] px-3 py-2 rounded-lg text-sm leading-relaxed ${
                msg.role === "user"
                  ? "bg-gray-800 text-white rounded-br-sm"
                  : "bg-gray-100 text-gray-900 rounded-bl-sm"
              }`}
            >
              <p className="whitespace-pre-wrap break-words">{msg.content}</p>
              {msg.role === "assistant" && msg.citations && (
                <CitationList citations={msg.citations} />
              )}
            </div>
          </div>
        ))
      )}
      {/* Error bubble */}
      {queryError && (
        <div className="flex justify-center">
          <div className="bg-red-50 border border-red-200 text-red-700 text-sm px-3 py-2 rounded-lg max-w-[75%]">
            {queryError}
          </div>
        </div>
      )}
      {/* Streaming message (isolated component) */}
      <StreamingMessage />
      {/* Invisible scroll anchor */}
      <div ref={bottomRef} />
    </div>
  )
}
```

- Messages container: `flex-1 overflow-y-auto`
- User messages: `justify-end`, dark bg (`bg-gray-800 text-white`), `rounded-br-sm`
- Assistant messages: `justify-start`, light bg (`bg-gray-100 text-gray-900`), `rounded-bl-sm`
- Each assistant message with citations renders `<CitationList />` below the content
- Empty state: "No messages yet. Ask a question to get started."
- Error bubble: centered red box when `queryError` is truthy
- Scroll anchor `<div ref={bottomRef} />` — auto-scrolls on messages change
- Messages use `key={i}` (index) — no virtualization needed for capped ~20 messages
- `<StreamingMessage />` rendered AFTER the messages list (isolated from the `.map()` to prevent full list re-render on streaming updates)

### 2. StreamingMessage.jsx
```jsx
import useEngageStore from "../../store/useEngageStore"

export default function StreamingMessage() {
  const streamingResponse = useEngageStore((s) => s.streamingResponse)
  const isStreaming = useEngageStore((s) => s.isStreaming)

  if (!isStreaming) return null

  return (
    <div className="flex justify-start">
      <div className="max-w-[75%] px-3 py-2 rounded-lg rounded-bl-sm bg-gray-100 text-gray-900 text-sm leading-relaxed">
        {streamingResponse ? (
          <p className="whitespace-pre-wrap break-words">
            {streamingResponse}
            <span className="inline-block w-0.5 h-4 bg-gray-700 ml-0.5 animate-pulse">|</span>
          </p>
        ) : (
          <p className="text-gray-400 italic">
            EngageX is thinking<span className="animate-pulse">...</span>
          </p>
        )}
      </div>
    </div>
  )
}
```

- Returns `null` when not streaming
- When `streamingResponse` is empty: show "EngageX is thinking..." with animated dots
- When `streamingResponse` has content: show text with blinking cursor `|` at end using `animate-pulse`
- Same styling as assistant messages (left-aligned, light bg)
- Isolated in its own component to prevent MessageList re-renders on streaming updates

### 3. SuggestedQuestions.jsx
```jsx
import useEngageStore from "../../store/useEngageStore"

const QUESTIONS = [
  "Why did Video A get more engagement than Video B?",
  "What's the engagement rate of each video?",
  "Compare the hooks in the first 5 seconds",
  "Who's the creator of Video B and what's their follower count?",
  "Suggest improvements for Video B based on what worked in Video A",
]

export default function SuggestedQuestions() {
  const messages = useEngageStore((s) => s.messages)
  const sendStreamQuery = useEngageStore((s) => s.sendStreamQuery)
  const isStreaming = useEngageStore((s) => s.isStreaming)
  const queryLoading = useEngageStore((s) => s.queryLoading)

  // Only show when chat is empty and not streaming
  if (messages.length > 0 || isStreaming || queryLoading) return null

  return (
    <div className="p-4 space-y-2">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">Suggested Questions</p>
      <div className="flex flex-wrap gap-2">
        {QUESTIONS.map((q, i) => (
          <button
            key={i}
            onClick={() => sendStreamQuery(q)}
            disabled={isStreaming || queryLoading}
            className="text-sm text-left bg-gray-50 hover:bg-blue-50 border border-gray-200 hover:border-blue-300 text-gray-700 hover:text-blue-700 px-3 py-2 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed max-w-full"
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  )
}
```

- 5 hardcoded questions array
- Hidden when `messages.length > 0` (only shown on empty chat)
- Disabled during streaming/loading
- Each chip: clickable, border style, hover effect
- Uses `sendStreamQuery` directly

### 4. NewConversationButton.jsx
```jsx
import { MessageSquarePlus } from "lucide-react"
import useEngageStore from "../../store/useEngageStore"

export default function NewConversationButton() {
  const clearHistory = useEngageStore((s) => s.clearHistory)
  const messages = useEngageStore((s) => s.messages)

  // Hide when no messages (already in empty state)
  if (messages.length === 0) return null

  return (
    <div className="px-4 py-2 border-b border-gray-100">
      <button
        onClick={() => clearHistory()}
        className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-blue-600 transition-colors"
        title="Start a new conversation (videos stay loaded)"
      >
        <MessageSquarePlus size={14} />
        New Conversation
      </button>
    </div>
  )
}
```

- Shows a small button at top of chat
- Only visible when there ARE messages (not in empty state)
- Calls `clearHistory()` which keeps the session alive but clears messages
- Subtle gray text that turns blue on hover
</action>

<acceptance_criteria>
  - `Frontend/src/components/chat/MessageList.jsx` exists
  - `grep -n "CitationList" Frontend/src/components/chat/MessageList.jsx` matches
  - `grep -n "StreamingMessage" Frontend/src/components/chat/MessageList.jsx` matches
  - `grep -n "scrollIntoView" Frontend/src/components/chat/MessageList.jsx` matches (auto-scroll)
  - `grep -n "bg-gray-800 text-white" Frontend/src/components/chat/MessageList.jsx` matches (user bubble style)
  - `Frontend/src/components/chat/StreamingMessage.jsx` exists
  - `grep -n "streamingResponse" Frontend/src/components/chat/StreamingMessage.jsx` matches
  - `grep -n "isStreaming" Frontend/src/components/chat/StreamingMessage.jsx` matches
  - `Frontend/src/components/chat/SuggestedQuestions.jsx` exists
  - `grep -n "Compare the hooks" Frontend/src/components/chat/SuggestedQuestions.jsx` matches
  - `grep -n "sendStreamQuery" Frontend/src/components/chat/SuggestedQuestions.jsx` matches
  - `Frontend/src/components/chat/NewConversationButton.jsx` exists
  - `grep -n "clearHistory" Frontend/src/components/chat/NewConversationButton.jsx` matches
  - `grep -n "MessageSquarePlus" Frontend/src/components/chat/NewConversationButton.jsx` matches
</acceptance_criteria>

<verify>
  <automated>node -e "const fs=require('fs');['MessageList','StreamingMessage','SuggestedQuestions','NewConversationButton'].forEach(n=>{const p='Frontend/src/components/chat/'+n+'.jsx';if(!fs.existsSync(p)){console.error('MISSING: '+p);process.exit(1)}console.log('OK: '+p)})"</automated>
</verify>

<done>
MessageList renders user/assistant messages in styled bubbles with auto-scroll. StreamingMessage shows live streaming text with blinking cursor. SuggestedQuestions shows 5 clickable question chips on empty chat. NewConversationButton clears history while keeping session alive.
</done>
</task>

<task type="auto">
<name>Task 3: Create ChatPanel composing all chat conversation components</name>
<files>
  Frontend/src/components/chat/ChatPanel.jsx
</files>

<read_first>
  Frontend/src/components/chat/MessageList.jsx (sketch)
  Frontend/src/components/chat/ChatInput.jsx (sketch)
  Frontend/src/components/chat/SuggestedQuestions.jsx (sketch)
  Frontend/src/components/chat/NewConversationButton.jsx (sketch)
</read_first>

<action>
Create `Frontend/src/components/chat/ChatPanel.jsx`:

```jsx
import MessageList from "./MessageList"
import ChatInput from "./ChatInput"
import SuggestedQuestions from "./SuggestedQuestions"
import NewConversationButton from "./NewConversationButton"

export default function ChatPanel() {
  return (
    <div className="flex flex-col h-full bg-white border-l border-gray-200">
      {/* New conversation button at top */}
      <NewConversationButton />

      {/* Suggested questions (shown when chat is empty) */}
      <div className="flex-1 flex flex-col min-h-0">
        <SuggestedQuestions />
        <MessageList />
      </div>

      {/* Input at bottom */}
      <ChatInput />
    </div>
  )
}
```

- Full-height flex column container with `h-full`
- `NewConversationButton` at top (in a border-bottom section)
- `<SuggestedQuestions />` rendered inside the scrollable area (above MessageList but in the same flex container)
- `MessageList` takes remaining space with `flex-1`
- `ChatInput` pinned to bottom with `border-t`
- The parent wrapper div uses `flex flex-col h-full` to fill available space in the chat page layout
</action>

<acceptance_criteria>
  - `Frontend/src/components/chat/ChatPanel.jsx` exists
  - `grep -n "MessageList" Frontend/src/components/chat/ChatPanel.jsx` matches
  - `grep -n "ChatInput" Frontend/src/components/chat/ChatPanel.jsx` matches
  - `grep -n "NewConversationButton" Frontend/src/components/chat/ChatPanel.jsx` matches
  - `grep -n "SuggestedQuestions" Frontend/src/components/chat/ChatPanel.jsx` matches
</acceptance_criteria>

<verify>
  <automated>node -e "const fs=require('fs');const p='Frontend/src/components/chat/ChatPanel.jsx';fs.existsSync(p)?console.log('OK: '+p):(console.error('MISSING: '+p),process.exit(1))"</automated>
</verify>

<done>
ChatPanel composes NewConversationButton, SuggestedQuestions, MessageList, and ChatInput into a vertical flex layout. Full height, input pinned to bottom.
</done>
</task>

</tasks>

<verification>
- `npm run build` succeeds in Frontend/ directory
- All 7 chat conversation files exist
- ChatPanel composes all sub-components without errors
</verification>

<success_criteria>
- ChatInput provides auto-resizing textarea with Send/Stop buttons, disabled when rate limited
- MessageList renders user (dark, right) and assistant (light, left) messages with auto-scroll
- StreamingMessage shows "EngageX is thinking..." or live response with blinking cursor
- CitationList renders timestamp chips that open YouTube/Instagram links
- SuggestedQuestions shows 5 question chips when chat is empty
- NewConversationButton clears messages without losing session
- ChatPanel composes everything in a vertical flex layout
- Build passes without errors
</success_criteria>

<output>
After completion, create `.planning/phases/01-frontend-build/01-frontend-build-04-SUMMARY.md`
</output>
