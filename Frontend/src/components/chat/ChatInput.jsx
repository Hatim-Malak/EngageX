import { useState, useRef } from "react";
import { Send, Square } from "lucide-react";
import useEngageStore from "../../store/useEngageStore";

export default function ChatInput() {
  const sendStreamQuery = useEngageStore((s) => s.sendStreamQuery);
  const abortStream = useEngageStore((s) => s.abortStream);
  const isStreaming = useEngageStore((s) => s.isStreaming);
  const queryLoading = useEngageStore((s) => s.queryLoading);
  const queriesRemaining = useEngageStore((s) => s.queriesRemaining);

  const [input, setInput] = useState("");
  const textareaRef = useRef(null);

  const adjustHeight = () => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, 120) + "px"; // max 4 rows ~120px
    }
  };

  const handleSubmit = async () => {
    const trimmed = input.trim();
    if (!trimmed || isStreaming || queryLoading) return;
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    await sendStreamQuery(trimmed);
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleStop = () => {
    abortStream();
  };

  if (queriesRemaining === 0) {
    return (
      <div className="p-4 border-t border-gray-200 bg-gray-50">
        <p className="text-sm text-center text-orange-600 font-medium">
          Daily limit reached — resets at midnight UTC
        </p>
      </div>
    );
  }

  return (
    <div className="border-t border-gray-200 p-3 bg-white">
      <div className="flex items-end gap-2">
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => {
            setInput(e.target.value);
            adjustHeight();
          }}
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
  );
}
