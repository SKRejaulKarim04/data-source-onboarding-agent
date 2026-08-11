import type { ReactNode } from "react";

interface BubbleProps {
  role: "user" | "agent";
  children: ReactNode;
}

/** One chat bubble: avatar plus body, sided by role. */
export function Bubble({ role, children }: BubbleProps) {
  return (
    <div className={`msg ${role}`}>
      <div className="msg-avatar" aria-hidden="true">
        {role === "user" ? "U" : "⚡"}
      </div>
      <div className="msg-body">{children}</div>
    </div>
  );
}

export function TypingIndicator() {
  return (
    <Bubble role="agent">
      <div className="typing" role="status" aria-label="The agent is working">
        <span />
        <span />
        <span />
      </div>
    </Bubble>
  );
}
