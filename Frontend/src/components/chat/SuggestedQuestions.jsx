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
    <div className="p-6 space-y-3">
      <p className="text-xs font-bold text-brand-secondary uppercase tracking-widest text-center">
        Suggested Questions
      </p>
      <div className="flex flex-wrap justify-center gap-2">
        {QUESTIONS.map((q, i) => (
          <button
            key={i}
            onClick={() => sendStreamQuery(q)}
            disabled={isStreaming || queryLoading}
            className="text-sm text-left bg-brand-primary/20 hover:bg-brand-secondary/40 border border-brand-secondary/30 hover:border-brand-light/50 text-brand-light hover:text-white px-4 py-2.5 rounded-xl transition-all duration-300 disabled:opacity-50 disabled:cursor-not-allowed max-w-full shadow-sm hover:shadow-[0_0_15px_rgba(64,138,113,0.3)]"
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}
