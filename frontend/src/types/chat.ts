import type { ClarifyingQuestion, Extraction } from "../api/types";

/**
 * The conversation model.
 *
 * The thread is a list of typed messages rather than a blob of HTML, so every
 * bubble is a component with props and the interactive ones (clarifying
 * questions, the generate button) keep their own React state instead of being
 * re-wired by id after each innerHTML write.
 */
export type ChatMessage =
  | { id: string; role: "user"; kind: "text"; text: string }
  | { id: string; role: "agent"; kind: "extraction"; extraction: Extraction }
  | {
      id: string;
      role: "agent";
      kind: "questions";
      questions: ClarifyingQuestion[];
    }
  | {
      id: string;
      role: "agent";
      kind: "connector";
      accepted: boolean;
      summary: string;
    }
  | {
      id: string;
      role: "agent";
      kind: "sandbox";
      success: boolean;
      summary: string;
    }
  | { id: string; role: "agent"; kind: "error"; text: string };

let counter = 0;

/** Monotonic ids. Stable React keys matter more here than global uniqueness. */
export function messageId(prefix: string): string {
  counter += 1;
  return `${prefix}-${counter}`;
}
