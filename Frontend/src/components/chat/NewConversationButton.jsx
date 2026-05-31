import { MessageSquarePlus } from "lucide-react";
import useEngageStore from "../../store/useEngageStore";

export default function NewConversationButton() {
  const clearHistory = useEngageStore((s) => s.clearHistory);
  const messages = useEngageStore((s) => s.messages);

  if (messages.length === 0) return null;

  return (
    <div className="px-4 py-2 border-b border-gray-100">
      <button
        onClick={() => clearHistory()}
        className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-blue-600 transition-colors"
        title="Start a new conversation (videos stay loaded)"
      >
        <MessageSquarePlus size={14} />
        New Conversation
      </button>
    </div>
  );
}
