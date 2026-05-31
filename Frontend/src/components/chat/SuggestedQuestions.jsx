import useEngageStore from "../../store/useEngageStore";

const QUESTIONS = [
  "Why did Video A get more engagement than Video B?",
  "What's the engagement rate of each video?",
  "Compare the hooks in the first 5 seconds",
  "Who's the creator of Video B and what's their follower count?",
  "Suggest improvements for Video B based on what worked in Video A",
];

export default function SuggestedQuestions() {
  const messages = useEngageStore((s) => s.messages);
  const sendStreamQuery = useEngageStore((s) => s.sendStreamQuery);
  const isStreaming = useEngageStore((s) => s.isStreaming);
  const queryLoading = useEngageStore((s) => s.queryLoading);

  if (messages.length > 0 || isStreaming || queryLoading) return null;

  return (
    <div className="p-4 space-y-2">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
        Suggested Questions
      </p>
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
  );
}
