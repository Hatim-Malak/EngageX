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
      <div className="p-4 border-t border-brand-primary/30 bg-brand-dark/60 backdrop-blur-md">
        <p className="text-sm text-center text-red-400 font-medium">
          Daily limit reached — resets at midnight UTC
        </p>
      </div>
    );
  }

  return (
    <div className="border-t border-brand-primary/30 p-4 bg-brand-dark/50 backdrop-blur-md">
      <div className="flex items-end gap-3 max-w-4xl mx-auto">
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
          className="flex-1 resize-none bg-brand-dark/80 border border-brand-primary rounded-xl px-4 py-3 text-sm text-white placeholder-gray-500 focus:ring-2 focus:ring-brand-light focus:border-brand-light disabled:opacity-50 disabled:cursor-not-allowed outline-none shadow-inner custom-scrollbar transition-all"
        />
        {isStreaming ? (
          <button
            onClick={handleStop}
            className="flex-shrink-0 bg-red-600/90 text-white p-3.5 rounded-xl hover:bg-red-500 transition-colors shadow-lg border border-red-400/30"
            aria-label="Stop streaming"
            title="Stop"
          >
            <Square size={20} className="fill-current" />
          </button>
        ) : (
          <button
            onClick={handleSubmit}
            disabled={!input.trim() || queryLoading}
            className="flex-shrink-0 bg-gradient-to-br from-brand-secondary to-brand-primary text-white p-3.5 rounded-xl hover:to-brand-secondary disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-lg border border-brand-secondary/50 group"
            aria-label="Send message"
            title="Send"
          >
            <Send size={20} className="group-hover:translate-x-0.5 transition-transform" />
          </button>
        )}
      </div>
    </div>
  );
}
