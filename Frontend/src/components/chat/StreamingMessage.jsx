import useEngageStore from "../../store/useEngageStore";

export default function StreamingMessage() {
  const streamingResponse = useEngageStore((s) => s.streamingResponse);
  const isStreaming = useEngageStore((s) => s.isStreaming);

  if (!isStreaming) return null;

  return (
    <div className="flex justify-start">
      <div className="max-w-[80%] px-4 py-3 rounded-2xl rounded-bl-sm bg-brand-dark/80 backdrop-blur-md border border-brand-primary/40 text-brand-light text-sm leading-relaxed shadow-md">
        {streamingResponse ? (
          <p className="whitespace-pre-wrap break-words">
            {streamingResponse}
            <span className="inline-block w-1 h-4 bg-brand-light ml-1 animate-pulse">
              |
            </span>
          </p>
        ) : (
          <p className="text-brand-secondary italic">
            EngageX is thinking<span className="animate-pulse">...</span>
          </p>
        )}
      </div>
    </div>
  );
}
