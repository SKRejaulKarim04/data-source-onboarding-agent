import { useLayoutEffect, useRef } from "react";
import { SendIcon } from "../Icons";

const MAX_HEIGHT = 120;

interface InputBarProps {
  value: string;
  busy: boolean;
  onChange: (value: string) => void;
  onSubmit: () => void;
}

/** Prompt box. Enter sends, Shift+Enter adds a line, height follows content. */
export function InputBar({ value, busy, onChange, onSubmit }: InputBarProps) {
  const textarea = useRef<HTMLTextAreaElement>(null);

  // Runs before paint so the box never flashes at the wrong height.
  useLayoutEffect(() => {
    const element = textarea.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, MAX_HEIGHT)}px`;
  }, [value]);

  const canSend = value.trim().length > 0 && !busy;

  return (
    <div className="input-bar">
      <div className="input-wrap">
        <textarea
          ref={textarea}
          rows={1}
          value={value}
          placeholder="Describe your data source…"
          autoComplete="off"
          aria-label="Describe your data source"
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              if (canSend) onSubmit();
            }
          }}
        />
        <button
          type="button"
          className="send-btn"
          title="Send"
          aria-label="Send"
          disabled={!canSend}
          onClick={onSubmit}
        >
          <SendIcon />
        </button>
      </div>
    </div>
  );
}
