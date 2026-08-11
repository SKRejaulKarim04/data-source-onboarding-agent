import { useMemo, useState } from "react";
import type { ClarifyingQuestion } from "../../api/types";

/** Sentinel for the "something else" branch of an options question. */
const OTHER = "__other__";

interface QuestionsCardProps {
  questions: ClarifyingQuestion[];
  /** Superseded cards stay visible but stop accepting input. */
  stale: boolean;
  busy: boolean;
  onSubmit: (answers: Record<string, string>) => void;
}

interface FieldState {
  choice: string;
  custom: string;
}

export function QuestionsCard({
  questions,
  stale,
  busy,
  onSubmit,
}: QuestionsCardProps) {
  const [fields, setFields] = useState<Record<string, FieldState>>({});
  const [submitted, setSubmitted] = useState(false);

  const answers = useMemo(() => collect(questions, fields), [questions, fields]);
  const hasAnswers = Object.keys(answers).length > 0;

  function update(field: string, patch: Partial<FieldState>) {
    setFields((current) => ({
      ...current,
      [field]: {
        choice: current[field]?.choice ?? "",
        custom: current[field]?.custom ?? "",
        ...patch,
      },
    }));
  }

  function handleSubmit() {
    if (!hasAnswers) return;
    setSubmitted(true);
    onSubmit(answers);
  }

  return (
    <>
      <div className="msg-label">I need a few more details</div>
      <div className="q-block">
        {questions.map((question) => {
          const state = fields[question.field] ?? { choice: "", custom: "" };
          const usesSelect = question.options.length > 0;
          const showCustom =
            !usesSelect || (question.free_text && state.choice === OTHER);

          return (
            <div className="q-item" key={question.field}>
              <div className="q-text">
                <label htmlFor={`q-${question.field}`}>
                  {question.question}
                </label>
              </div>
              <div className="q-why">{question.why}</div>

              {usesSelect && (
                <select
                  id={`q-${question.field}`}
                  className="control"
                  value={state.choice}
                  disabled={stale || busy}
                  onChange={(event) =>
                    update(question.field, { choice: event.target.value })
                  }
                >
                  <option value="">— choose —</option>
                  {question.options.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                  {question.free_text && <option value={OTHER}>Other…</option>}
                </select>
              )}

              {showCustom && (
                <input
                  id={usesSelect ? undefined : `q-${question.field}`}
                  className="control"
                  type="text"
                  autoComplete="off"
                  placeholder={question.example ?? ""}
                  aria-label={usesSelect ? "Custom value" : undefined}
                  value={state.custom}
                  disabled={stale || busy}
                  onChange={(event) =>
                    update(question.field, { custom: event.target.value })
                  }
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      handleSubmit();
                    }
                  }}
                />
              )}
            </div>
          );
        })}
      </div>

      <div className="q-actions">
        <button
          className="btn"
          type="button"
          onClick={handleSubmit}
          disabled={stale || busy || !hasAnswers}
        >
          {submitted ? "Update answers" : "Submit answers"}
        </button>
        {stale && <span className="q-stale">superseded</span>}
      </div>
    </>
  );
}

/** Only fields the user actually filled in are sent. */
function collect(
  questions: ClarifyingQuestion[],
  fields: Record<string, FieldState>,
): Record<string, string> {
  const answers: Record<string, string> = {};
  for (const question of questions) {
    const state = fields[question.field];
    if (!state) continue;

    const usesSelect = question.options.length > 0;
    const raw =
      !usesSelect || state.choice === OTHER ? state.custom : state.choice;
    const value = raw.trim();
    if (value) answers[question.field] = value;
  }
  return answers;
}
