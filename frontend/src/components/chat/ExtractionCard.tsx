import type { Extraction, SpecDraft } from "../../api/types";

interface ExtractionCardProps {
  extraction: Extraction;
  /** False for superseded cards and while a call is in flight. */
  canGenerate: boolean;
  generating: boolean;
  onGenerate: () => void;
}

/** What the agent understood: security notes, the draft spec, and the go button. */
export function ExtractionCard({
  extraction,
  canGenerate,
  generating,
  onGenerate,
}: ExtractionCardProps) {
  const draft = extraction.draft ?? {};

  return (
    <>
      <div className="msg-label">Extraction Result</div>

      {extraction.security_findings.map((finding, index) => (
        <div
          key={`${finding.kind}-${index}`}
          className={`note-inline ${finding.kind === "credential" ? "bad" : "warn"}`}
        >
          <span>
            <strong>{finding.label}</strong> — {finding.detail}
          </span>
        </div>
      ))}

      {extraction.notes.map((note, index) => (
        <div key={`note-${index}`} className="note-inline info">
          <span>{note}</span>
        </div>
      ))}

      <dl className="spec-grid">
        {specRows(extraction, draft).map(([key, value]) => (
          <Row key={key} label={key} value={value} />
        ))}
        {extraction.assumed.length > 0 && (
          <Row label="assumed" value={extraction.assumed.join(", ")} />
        )}
        {extraction.missing.length > 0 && (
          <>
            <dt>missing</dt>
            <dd>
              <span className="flag fail">{extraction.missing.join(", ")}</span>
            </dd>
          </>
        )}
      </dl>

      {extraction.ready && (
        <div className="actions">
          <button
            className="btn"
            type="button"
            onClick={onGenerate}
            disabled={!canGenerate}
          >
            {generating ? "Generating…" : "⚡ Generate Connector"}
          </button>
        </div>
      )}
    </>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </>
  );
}

function specRows(
  extraction: Extraction,
  draft: SpecDraft,
): Array<[string, string]> {
  return [
    ["confidence", `${(extraction.confidence * 100).toFixed(0)}%`],
    ["source type", draft.source_type || "—"],
    ["class", draft.connector_name || "—"],
    ["host", draft.host || draft.base_url || "—"],
    ["port", draft.port != null ? String(draft.port) : "—"],
    ["database", draft.database || "—"],
    ["auth", draft.auth_method || "—"],
    ["access", draft.read_only === false ? "read-write" : "read-only"],
  ];
}
