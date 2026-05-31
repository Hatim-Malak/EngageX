import useEngageStore from "../../store/useEngageStore";

export default function StreamingMessage() {
  const streamingResponse = useEngageStore((s) => s.streamingResponse);
  const isStreaming = useEngageStore((s) => s.isStreaming);

  if (!isStreaming) return null;

  return (
    <div className="flex justify-start">
      <div className="max-w-[75%] px-3 py-2 rounded-lg rounded-bl-sm bg-gray-100 text-gray-900 text-sm leading-relaxed">
        {streamingResponse ? (
          <p className="whitespace-pre-wrap break-words">
            {streamingResponse}
            <span className="inline-block w-0.5 h-4 bg-gray-700 ml-0.5 animate-pulse">
              |
            </span>
          </p>
        ) : (
          <p className="text-gray-400 italic">
            EngageX is thinking<span className="animate-pulse">...</span>
          </p>
        )}
      </div>
    </div>
  );
}
