import { useRef, useEffect } from "react";
import useEngageStore from "../../store/useEngageStore";
import CitationList from "./CitationList";
import StreamingMessage from "./StreamingMessage";

export default function MessageList() {
  const messages = useEngageStore((s) => s.messages);
  const queryError = useEngageStore((s) => s.queryError);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-4">
      {messages.length === 0 ? (
        <p className="text-center text-gray-400 text-sm mt-8">
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
      {queryError && (
        <div className="flex justify-center">
          <div className="bg-red-50 border border-red-200 text-red-700 text-sm px-3 py-2 rounded-lg max-w-[75%]">
            {queryError}
          </div>
        </div>
      )}
      <StreamingMessage />
      <div ref={bottomRef} />
    </div>
  );
}
