import { useRef, useEffect } from "react";
import useEngageStore from "../../store/useEngageStore";
import CitationList from "./CitationList";
import StreamingMessage from "./StreamingMessage";
import MarkdownRenderer from "./MarkdownRenderer";

export default function MessageList() {
  const messages = useEngageStore((s) => s.messages);
  const queryError = useEngageStore((s) => s.queryError);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="flex-1 overflow-y-auto p-5 space-y-5 custom-scrollbar">
      {messages.length === 0 ? (
        <p className="text-center text-brand-light/50 font-medium text-sm mt-10">
          No messages yet. Ask a question to get started.
        </p>
      ) : (
        messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${
              msg.role === "user" ? "justify-end" : "justify-start"
            }`}
          >
            <div
              className={`max-w-[85%] md:max-w-[80%] px-5 py-4 rounded-2xl text-sm leading-relaxed shadow-md ${
                msg.role === "user"
                  ? "bg-gradient-to-br from-brand-secondary to-brand-primary text-white rounded-br-sm"
                  : "bg-brand-dark/80 backdrop-blur-md border border-brand-primary/40 text-brand-light rounded-bl-sm"
              }`}
            >
              {msg.role === "user" ? (
                <p className="whitespace-pre-wrap break-words">{msg.content}</p>
              ) : (
                <MarkdownRenderer content={msg.content} />
              )}
              {msg.role === "assistant" && msg.citations && (
                <div className="mt-4 pt-3 border-t border-brand-primary/20">
                  <CitationList citations={msg.citations} />
                </div>
              )}
            </div>
          </div>
        ))
      )}
      {queryError && (
        <div className="flex justify-center">
          <div className="bg-red-900/40 backdrop-blur-sm border border-red-500/50 text-red-300 text-sm px-4 py-2 rounded-xl shadow-sm max-w-[80%] text-center">
            {queryError}
          </div>
        </div>
      )}
      <StreamingMessage />
      <div ref={bottomRef} />
    </div>
  );
}
