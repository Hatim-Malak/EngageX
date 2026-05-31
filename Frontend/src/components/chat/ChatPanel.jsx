import MessageList from "./MessageList";
import ChatInput from "./ChatInput";
import SuggestedQuestions from "./SuggestedQuestions";
import NewConversationButton from "./NewConversationButton";

export default function ChatPanel() {
  return (
    <div className="flex flex-col h-full bg-white border-l border-gray-200">
      <NewConversationButton />

      <div className="flex-1 flex flex-col min-h-0">
        <SuggestedQuestions />
        <MessageList />
      </div>

      <ChatInput />
    </div>
  );
}
