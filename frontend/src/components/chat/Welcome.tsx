export interface Suggestion {
  label: string;
  prompt: string;
}

/** The three demo paths: happy, needs-clarification, and REST. */
export const SUGGESTIONS: Suggestion[] = [
  {
    label: "🐘 Connect a local PostgreSQL database",
    prompt:
      "Onboard our local Postgres source at localhost port 55432, database dsoa_source, read-only.",
  },
  {
    label: "🐬 Connect a MySQL database (incomplete — shows clarification)",
    prompt: "Onboard the MySQL orders database.",
  },
  {
    label: "🌐 Connect a public REST API",
    prompt:
      "Onboard a public REST API at https://jsonplaceholder.typicode.com. The path to fetch users is /users. No authentication is required.",
  },
];

interface WelcomeProps {
  onPick: (prompt: string) => void;
}

export function Welcome({ onPick }: WelcomeProps) {
  return (
    <div className="welcome">
      <div className="welcome-icon" aria-hidden="true">
        🔌
      </div>
      <h2>What would you like to connect?</h2>
      <p>
        Describe your data source in plain English — I&apos;ll generate a
        production-ready Python connector.
      </p>
      <div className="suggestions">
        {SUGGESTIONS.map((suggestion) => (
          <button
            key={suggestion.label}
            type="button"
            onClick={() => onPick(suggestion.prompt)}
          >
            {suggestion.label}
          </button>
        ))}
      </div>
    </div>
  );
}
