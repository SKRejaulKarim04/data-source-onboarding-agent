/**
 * Wire types.
 *
 * These mirror the serializers in `src/dsoa/api/main.py` field for field. The
 * sub-objects (`extraction`, `connector`, `sandbox`, `artifact`) are returned as
 * `{}` before their stage has run, which is why every one of them is modelled as
 * a partial: the presence of a discriminating field — `summary`, `code`,
 * `name` — is what tells you the stage actually produced something.
 */

export type RequestStatus =
  | "extracted"
  | "needs_clarification"
  | "generated"
  | "rejected";

export interface HealthPayload {
  status: string;
  llm: string;
  live_model: boolean;
}

export interface RequestSummary {
  id: string;
  prompt: string;
  status: RequestStatus | string;
  created_at: string;
}

export interface SecurityFinding {
  kind: string;
  label: string;
  detail: string;
}

export interface ClarifyingQuestion {
  field: string;
  question: string;
  why: string;
  options: string[];
  example: string | null;
  free_text: boolean;
}

/** Every field of `SpecDraft` is optional by design — see spec.py. */
export interface SpecDraft {
  source_type?: string | null;
  connector_name?: string | null;
  slug?: string | null;
  description?: string;
  host?: string | null;
  port?: number | null;
  database?: string | null;
  schema_name?: string | null;
  base_url?: string | null;
  default_path?: string | null;
  pagination?: string | null;
  page_size?: number | null;
  auth_method?: string | null;
  env_prefix?: string | null;
  header_name?: string | null;
  token_url?: string | null;
  read_only?: boolean | null;
  tags?: string[];
  assumed_fields?: string[];
}

export interface Extraction {
  summary: string;
  confidence: number;
  ready: boolean;
  missing: string[];
  assumed: string[];
  notes: string[];
  security_findings: SecurityFinding[];
  questions: ClarifyingQuestion[];
  draft: SpecDraft;
}

export interface StandardsCheck {
  name: string;
  passed: boolean;
}

export interface ValidationFinding {
  check: string;
  severity: "error" | "warning" | string;
  message: string;
  line: number | null;
  tool: string | null;
  remedy: string | null;
}

export interface Connector {
  module_name: string;
  code: string;
  accepted: boolean;
  semver: string;
  template_key: string;
  template_version: string;
  spec_checksum: string;
  code_checksum: string;
  conformance_pct: number;
  summary: string;
  warnings: string[];
  repair_iterations: number;
  checks: StandardsCheck[];
  findings: ValidationFinding[];
}

export interface SchemaColumn {
  name: string;
  type: string;
  nullable: boolean;
  primary_key: boolean;
}

export interface SchemaTable {
  schema: string;
  name: string;
  columns: SchemaColumn[];
}

export interface SandboxRun {
  success: boolean;
  stage: string;
  summary: string;
  duration_ms: number;
  error: string | null;
  error_type: string | null;
  tables: SchemaTable[];
  table_count: number;
}

export interface ArtifactManifest {
  name?: string;
  version?: string;
  created_at?: string;
  source?: Record<string, unknown>;
  provenance?: Record<string, unknown>;
  validation?: Record<string, unknown>;
  connectivity?: Record<string, unknown>;
  required_env?: string[];
  [key: string]: unknown;
}

export interface ArtifactPayload {
  name: string;
  version: string;
  checksum: string;
  files: string[];
  manifest: ArtifactManifest;
}

/** The one shape every mutating endpoint returns. */
export interface OnboardingRequest {
  id: string;
  prompt: string;
  status: RequestStatus | string;
  created_at: string;
  history: string[];
  extraction: Partial<Extraction>;
  connector: Partial<Connector>;
  sandbox: Partial<SandboxRun>;
  artifact: Partial<ArtifactPayload>;
}

export interface TemplateEntry {
  key: string;
  version: string;
  template: string;
  description: string;
}

/* --- Narrowing helpers ----------------------------------------------------
 * The API sends `{}` for stages that have not run. These turn "did this stage
 * produce anything?" into a type guard, so components can stop writing
 * `connector && connector.code` and then still be handed `string | undefined`.
 */

export function hasExtraction(
  value: Partial<Extraction> | undefined,
): value is Extraction {
  return !!value && typeof value.summary === "string";
}

export function hasConnector(
  value: Partial<Connector> | undefined,
): value is Connector {
  return !!value && typeof value.code === "string" && value.code.length > 0;
}

export function hasSandbox(
  value: Partial<SandboxRun> | undefined,
): value is SandboxRun {
  return !!value && typeof value.summary === "string";
}

export function hasArtifact(
  value: Partial<ArtifactPayload> | undefined,
): value is ArtifactPayload {
  return !!value && typeof value.name === "string" && value.name.length > 0;
}
