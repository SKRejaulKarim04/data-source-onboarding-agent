import { useRef } from "react";
import "./OutputPanel.css";
import { StandardsTab } from "./StandardsTab";
import { CodeTab } from "./CodeTab";
import { ConnectionTab } from "./ConnectionTab";
import { ArtifactTab } from "./ArtifactTab";
import { hasConnector, hasSandbox } from "../../api/types";
import type { OnboardingRequest } from "../../api/types";

export type TabKey = "checks" | "code" | "connect" | "artifact";

const TABS: Array<{ key: TabKey; label: string }> = [
  { key: "checks", label: "Standards" },
  { key: "code", label: "Code" },
  { key: "connect", label: "Connection" },
  { key: "artifact", label: "Artifact" },
];

interface OutputPanelProps {
  request: OnboardingRequest | null;
  activeTab: TabKey;
  testing: boolean;
  onTabChange: (tab: TabKey) => void;
  onTest: (credentials: Record<string, string>) => void;
}

/** The right column: everything the pipeline produced, one tab per stage. */
export function OutputPanel({
  request,
  activeTab,
  testing,
  onTabChange,
  onTest,
}: OutputPanelProps) {
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  const connector = request?.connector;
  const sandbox = request?.sandbox;

  function badgeFor(key: TabKey): string | null {
    if (key === "checks" && hasConnector(connector)) {
      return connector.accepted ? "ok" : "bad";
    }
    if (key === "connect" && hasSandbox(sandbox)) {
      return sandbox.success ? "ok" : "bad";
    }
    return null;
  }

  // Roving arrow-key focus, which is what a tablist is expected to do.
  function onKeyDown(event: React.KeyboardEvent<HTMLButtonElement>) {
    const delta =
      event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (delta === 0) return;
    event.preventDefault();

    const index = TABS.findIndex((tab) => tab.key === activeTab);
    const next = TABS[(index + delta + TABS.length) % TABS.length]!;
    onTabChange(next.key);
    tabRefs.current[next.key]?.focus();
  }

  return (
    <section className="output-column">
      <div className="tabs" role="tablist" aria-label="Generated output">
        {TABS.map((tab) => {
          const badge = badgeFor(tab.key);
          return (
            <button
              key={tab.key}
              type="button"
              role="tab"
              id={`tab-${tab.key}`}
              aria-selected={tab.key === activeTab}
              aria-controls={`panel-${tab.key}`}
              tabIndex={tab.key === activeTab ? 0 : -1}
              ref={(element) => {
                tabRefs.current[tab.key] = element;
              }}
              className={tab.key === activeTab ? "on" : ""}
              onClick={() => onTabChange(tab.key)}
              onKeyDown={onKeyDown}
            >
              {tab.label}
              {badge && <span className={`tab-badge ${badge}`} />}
            </button>
          );
        })}
      </div>

      <div
        className="tab-body scroll-y"
        role="tabpanel"
        id={`panel-${activeTab}`}
        aria-labelledby={`tab-${activeTab}`}
        tabIndex={0}
      >
        {activeTab === "checks" && <StandardsTab connector={connector} />}
        {activeTab === "code" && <CodeTab connector={connector} />}
        {activeTab === "connect" && (
          <ConnectionTab
            // Remount per request so credentials never survive a switch.
            key={request?.id ?? "none"}
            connector={connector}
            artifact={request?.artifact}
            sandbox={sandbox}
            testing={testing}
            onTest={onTest}
          />
        )}
        {activeTab === "artifact" && (
          <ArtifactTab
            requestId={request?.id ?? null}
            artifact={request?.artifact}
          />
        )}
      </div>
    </section>
  );
}
