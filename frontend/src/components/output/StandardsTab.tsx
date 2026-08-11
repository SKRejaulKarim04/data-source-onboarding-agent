import { EmptyState } from "./EmptyState";
import { hasConnector } from "../../api/types";
import type { Connector } from "../../api/types";

interface StandardsTabProps {
  connector: Partial<Connector> | undefined;
}

/** Static-validation results: the gate a connector has to clear to be accepted. */
export function StandardsTab({ connector }: StandardsTabProps) {
  if (!hasConnector(connector)) {
    return (
      <EmptyState icon="📋">Submit a request to see standards compliance.</EmptyState>
    );
  }

  const conformance = connector.conformance_pct;
  const tone =
    conformance >= 100 ? "" : conformance >= 60 ? " partial" : " failing";

  return (
    <>
      <div className="checks-summary">
        <span className={`flag ${connector.accepted ? "pass" : "fail"}`}>
          {connector.accepted ? "accepted" : "rejected"}
        </span>
        <span className="summary-text">{connector.summary}</span>
      </div>

      <div
        className={`conformance${tone}`}
        role="img"
        aria-label={`Conformance ${conformance}%`}
      >
        <span style={{ width: `${Math.max(0, Math.min(100, conformance))}%` }} />
      </div>

      {connector.warnings.map((warning, index) => (
        <div className="note warn" key={index}>
          {warning}
        </div>
      ))}

      <div className="checks-grid">
        {connector.checks.map((check) => (
          <div
            className={`check-item ${check.passed ? "ok" : "bad"}`}
            key={check.name}
          >
            <span className="mark">{check.passed ? "PASS" : "FAIL"}</span>
            {check.name}
          </div>
        ))}
      </div>

      {connector.findings.length > 0 && (
        <>
          <h3 className="section-title">Findings</h3>
          {connector.findings.map((finding, index) => (
            <div
              className={`note ${finding.severity === "error" ? "bad" : "warn"}`}
              key={`${finding.check}-${index}`}
            >
              <strong>{finding.check}</strong>
              {finding.line != null ? ` · line ${finding.line}` : ""}
              {finding.tool ? ` · ${finding.tool}` : ""} — {finding.message}
              {finding.remedy && (
                <span className="note-remedy">Fix: {finding.remedy}</span>
              )}
            </div>
          ))}
        </>
      )}
    </>
  );
}
