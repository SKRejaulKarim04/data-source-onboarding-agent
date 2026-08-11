import { useEffect, useState } from "react";
import { EmptyState } from "./EmptyState";
import { PythonCode } from "./PythonCode";
import { CopyIcon } from "../Icons";
import { hasConnector } from "../../api/types";
import type { Connector } from "../../api/types";

interface CodeTabProps {
  connector: Partial<Connector> | undefined;
}

/** The generated module, plus the provenance that ties it to the request. */
export function CodeTab({ connector }: CodeTabProps) {
  if (!hasConnector(connector)) {
    return <EmptyState icon="💻">No connector generated yet.</EmptyState>;
  }

  return (
    <>
      <dl className="kv">
        <dt>module</dt>
        <dd>{connector.module_name}</dd>
        <dt>template</dt>
        <dd>
          {connector.template_key} v{connector.template_version}
        </dd>
        <dt>spec sha</dt>
        <dd>{connector.spec_checksum}</dd>
        <dt>code sha</dt>
        <dd>{connector.code_checksum}</dd>
        <dt>repairs</dt>
        <dd>{connector.repair_iterations}</dd>
      </dl>

      <div className="code-toolbar">
        <h3 className="section-title">{connector.module_name}</h3>
        <CopyButton text={connector.code} />
      </div>

      <PythonCode code={connector.code} />
    </>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(false), 1600);
    return () => window.clearTimeout(timer);
  }, [copied]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      // Clipboard access is blocked on insecure origins; silently leave the
      // label alone rather than claiming a copy that did not happen.
      setCopied(false);
    }
  }

  return (
    <button type="button" className="copy-btn" onClick={copy}>
      <CopyIcon />
      {copied ? "copied" : "copy"}
    </button>
  );
}
