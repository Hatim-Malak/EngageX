import useEngageStore from "../../store/useEngageStore";
import MarkdownRenderer from "./MarkdownRenderer";

export default function StreamingMessage() {
  const streamingResponse = useEngageStore((s) => s.streamingResponse);
  const isStreaming = useEngageStore((s) => s.isStreaming);

  if (!isStreaming) return null;

  // Append a solid block character to simulate a cursor
  const contentWithCursor = streamingResponse ? `${streamingResponse} ▍` : "";

  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] md:max-w-[80%] px-5 py-4 rounded-2xl rounded-bl-sm bg-brand-dark/80 backdrop-blur-md border border-brand-primary/40 text-brand-light text-sm leading-relaxed shadow-md">
        {streamingResponse ? (
          <div className="animate-pulse-cursor">
            <MarkdownRenderer content={contentWithCursor} />
          </div>
        ) : (
          <p className="text-brand-secondary italic">
            EngageX is thinking<span className="animate-pulse">...</span>
          </p>
        )}
      </div>
    </div>
  );
}
