import "./Header.css";
import type { HealthState } from "../hooks/useHealth";

interface HeaderProps {
  health: HealthState;
}

/** Title bar, plus the live/scripted indicator for the model backing the agent. */
export function Header({ health }: HeaderProps) {
  const { label, tone } = describe(health);

  return (
    <header className="header">
      <div className="logo">
        <div className="logo-icon" aria-hidden="true">
          ⚡
        </div>
        <div>
          <h1>Data Source Onboarding Agent</h1>
        </div>
      </div>
      <span className="health" title={health.llm ?? undefined}>
        <span className={`health-dot ${tone}`} aria-hidden="true" />
        {label}
      </span>
    </header>
  );
}

function describe(health: HealthState): { label: string; tone: string } {
  switch (health.status) {
    case "loading":
      return { label: "checking", tone: "offline" };
    case "error":
      return { label: "api unreachable", tone: "down" };
    default:
      return health.liveModel
        ? { label: "live model", tone: "" }
        : { label: "offline — scripted", tone: "offline" };
  }
}
