import { useMemo, useState } from "react";
import { EmptyState } from "./EmptyState";
import { hasArtifact, hasConnector, hasSandbox } from "../../api/types";
import type {
  ArtifactPayload,
  Connector,
  SandboxRun,
  SchemaTable,
} from "../../api/types";

interface ConnectionTabProps {
  connector: Partial<Connector> | undefined;
  artifact: Partial<ArtifactPayload> | undefined;
  sandbox: Partial<SandboxRun> | undefined;
  testing: boolean;
  onTest: (credentials: Record<string, string>) => void;
}

/**
 * Live connection test.
 *
 * The credential fields are derived from `manifest.required_env` — the manifest
 * records the *names* a connector needs, never values, so this is the only
 * place those values exist, and they leave with the component.
 */
export function ConnectionTab({
  connector,
  artifact,
  sandbox,
  testing,
  onTest,
}: ConnectionTabProps) {
  const [credentials, setCredentials] = useState<Record<string, string>>({});

  const secretVars = useMemo(() => {
    if (!hasArtifact(artifact)) return [];
    return (artifact.manifest.required_env ?? []).filter(
      (name) => name.endsWith("USERNAME") || name.endsWith("PASSWORD"),
    );
  }, [artifact]);

  if (!hasConnector(connector)) {
    return (
      <EmptyState icon="🔗">
        Generate a connector first, then test your connection.
      </EmptyState>
    );
  }

  return (
    <>
      <p className="tab-intro">
        Credentials are sent once for this test. They are not stored, logged, or
        written to the artifact.
      </p>

      {secretVars.map((name) => (
        <label className="cred-label" key={name}>
          <span>{name}</span>
          <input
            className="control"
            type={name.endsWith("PASSWORD") ? "password" : "text"}
            autoComplete={
              name.endsWith("PASSWORD") ? "new-password" : "username"
            }
            value={credentials[name] ?? ""}
            disabled={testing}
            onChange={(event) =>
              setCredentials((current) => ({
                ...current,
                [name]: event.target.value,
              }))
            }
          />
        </label>
      ))}

      <div className="actions">
        <button
          className="btn"
          type="button"
          disabled={testing}
          onClick={() => onTest(credentials)}
        >
          {testing ? "Testing…" : "Run connection test"}
        </button>
      </div>

      {hasSandbox(sandbox) && <TestResult result={sandbox} />}
    </>
  );
}

function TestResult({ result }: { result: SandboxRun }) {
  return (
    <>
      <div
        className={`note ${result.success ? "" : "bad"}`}
        style={{ marginTop: 14 }}
      >
        <div className="test-result">
          <span className={`flag ${result.success ? "pass" : "fail"}`}>
            {result.success ? "connected" : "failed"}
          </span>
          <span className="summary-text">{result.summary}</span>
        </div>
        {!result.success && result.error && (
          <div className="error-detail">{result.error}</div>
        )}
      </div>

      {result.tables.length > 0 && <SchemaTableView tables={result.tables} />}
    </>
  );
}

function SchemaTableView({ tables }: { tables: SchemaTable[] }) {
  return (
    <>
      <h3 className="section-title">Schema — {tables.length} tables</h3>
      <div className="table-wrap">
        <table className="schema">
          <thead>
            <tr>
              <th>table</th>
              <th>columns</th>
              <th>primary key</th>
            </tr>
          </thead>
          <tbody>
            {tables.map((table) => (
              <tr key={`${table.schema}.${table.name}`}>
                <td>
                  {table.schema}.{table.name}
                </td>
                <td>{table.columns.length}</td>
                <td>
                  {table.columns
                    .filter((column) => column.primary_key)
                    .map((column) => column.name)
                    .join(", ") || "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
