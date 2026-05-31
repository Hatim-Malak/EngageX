import MessageList from "./MessageList";
import ChatInput from "./ChatInput";
import SuggestedQuestions from "./SuggestedQuestions";
import NewConversationButton from "./NewConversationButton";

export default function ChatPanel() {
  return (
    <div className="flex-1 flex flex-col min-h-0 w-full bg-transparent">
      <NewConversationButton />

      <div className="flex-1 flex flex-col min-h-0 relative">
        <SuggestedQuestions />
        <MessageList />
      </div>

      <ChatInput />
    </div>
  );
}
