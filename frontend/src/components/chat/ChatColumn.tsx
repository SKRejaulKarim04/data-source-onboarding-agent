import { forwardRef, useEffect, useRef } from "react";
import "./Chat.css";
import { Bubble, TypingIndicator } from "./Bubble";
import { ExtractionCard } from "./ExtractionCard";
import { QuestionsCard } from "./QuestionsCard";
import { InputBar } from "./InputBar";
import { Welcome } from "./Welcome";
import type { ChatMessage } from "../../types/chat";

interface ChatColumnProps {
  messages: ChatMessage[];
  prompt: string;
  busy: boolean;
  generating: boolean;
  /** True once a connector exists, which retires the generate button. */
  hasConnector: boolean;
  width: number | null;
  onPromptChange: (value: string) => void;
  onSubmitPrompt: () => void;
  onGenerate: () => void;
  onAnswers: (answers: Record<string, string>) => void;
}

export const ChatColumn = forwardRef<HTMLDivElement, ChatColumnProps>(
  function ChatColumn(props, ref) {
    const { messages, prompt, busy, generating, hasConnector, width } = props;
    const thread = useRef<HTMLDivElement>(null);

    // Follow the conversation. `busy` is in the deps so the typing indicator
    // appearing also scrolls into view.
    useEffect(() => {
      const element = thread.current;
      if (element) element.scrollTop = element.scrollHeight;
    }, [messages, busy]);

    // Only the newest card of each kind stays interactive; older ones describe
    // a state the server has already moved past.
    const latestExtraction = lastIdOf(messages, "extraction");
    const latestQuestions = lastIdOf(messages, "questions");

    function renderMessage(message: ChatMessage) {
      switch (message.kind) {
        case "text":
          return message.text;

        case "extraction":
          return (
            <ExtractionCard
              extraction={message.extraction}
              canGenerate={
                message.id === latestExtraction && !busy && !hasConnector
              }
              // Only the card whose button was pressed says "Generating…".
              generating={generating && message.id === latestExtraction}
              onGenerate={props.onGenerate}
            />
          );

        case "questions":
          return (
            <QuestionsCard
              questions={message.questions}
              stale={message.id !== latestQuestions}
              busy={busy}
              onSubmit={props.onAnswers}
            />
          );

        case "connector":
          return (
            <>
              <div className="msg-label">Connector Generated</div>
              <div className={`note-inline ${message.accepted ? "ok" : "bad"}`}>
                <span>
                  {message.accepted ? "✓ Accepted" : "✗ Rejected"} —{" "}
                  {message.summary}
                </span>
              </div>
              <p className="msg-hint">
                Check the <strong>Standards</strong>, <strong>Code</strong> and{" "}
                <strong>Artifact</strong> tabs on the right for full details.
              </p>
            </>
          );

        case "sandbox":
          return (
            <>
              <div className="msg-label">Connection Test</div>
              <div className={`note-inline ${message.success ? "ok" : "bad"}`}>
                <span>
                  {message.success ? "✓ Connected" : "✗ Failed"} —{" "}
                  {message.summary}
                </span>
              </div>
            </>
          );

        case "error":
          return (
            <div className="note-inline bad">
              <span>{message.text}</span>
            </div>
          );
      }
    }

    return (
      <div
        className="chat-column"
        ref={ref}
        style={width != null ? { width: `${width}px` } : undefined}
      >
        <div className="chat-thread scroll-y" ref={thread}>
          {messages.length === 0 ? (
            <Welcome onPick={props.onPromptChange} />
          ) : (
            messages.map((message) => (
              <Bubble key={message.id} role={message.role}>
                {renderMessage(message)}
              </Bubble>
            ))
          )}
          {busy && <TypingIndicator />}
        </div>

        <InputBar
          value={prompt}
          busy={busy}
          onChange={props.onPromptChange}
          onSubmit={props.onSubmitPrompt}
        />
      </div>
    );
  },
);

function lastIdOf(messages: ChatMessage[], kind: ChatMessage["kind"]) {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message && message.kind === kind) return message.id;
  }
  return null;
}
