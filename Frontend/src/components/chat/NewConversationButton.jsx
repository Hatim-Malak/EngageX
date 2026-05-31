import { MessageSquarePlus } from "lucide-react";
import useEngageStore from "../../store/useEngageStore";

export default function NewConversationButton() {
  const clearHistory = useEngageStore((s) => s.clearHistory);
  const messages = useEngageStore((s) => s.messages);

  if (messages.length === 0) return null;

  return (
    <div className="px-5 py-2.5 border-b border-brand-primary/30 bg-brand-dark/40 backdrop-blur-sm z-10 shadow-sm">
      <button
        onClick={() => clearHistory()}
        className="flex items-center gap-2 text-xs font-semibold text-brand-light/70 hover:text-white transition-colors"
        title="Start a new conversation (videos stay loaded)"
      >
        <MessageSquarePlus size={16} />
        New Conversation
      </button>
    </div>
  );
}
