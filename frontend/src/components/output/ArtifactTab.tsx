import { EmptyState } from "./EmptyState";
import { api } from "../../api/client";
import { hasArtifact } from "../../api/types";
import type { ArtifactPayload } from "../../api/types";

interface ArtifactTabProps {
  requestId: string | null;
  artifact: Partial<ArtifactPayload> | undefined;
}

/** The handover bundle: files, checksum, manifest, and the zip. */
export function ArtifactTab({ requestId, artifact }: ArtifactTabProps) {
  if (!hasArtifact(artifact) || !requestId) {
    return <EmptyState icon="📦">No artifact bundle yet.</EmptyState>;
  }

  return (
    <>
      <dl className="kv">
        <dt>name</dt>
        <dd>{artifact.name}</dd>
        <dt>version</dt>
        <dd>{artifact.version}</dd>
        <dt>checksum</dt>
        <dd>{artifact.checksum}</dd>
        <dt>files</dt>
        <dd>{artifact.files.join(", ")}</dd>
      </dl>

      <div className="actions">
        {/* A plain link, not fetch(): the browser streams the zip straight to
            disk with the filename the API sets in Content-Disposition. */}
        <a
          className="btn"
          href={api.downloadUrl(requestId)}
          download={`${artifact.name}-${artifact.version}.zip`}
        >
          📥 Download bundle
        </a>
      </div>

      <h3 className="section-title">Manifest</h3>
      <pre className="code">{JSON.stringify(artifact.manifest, null, 2)}</pre>
    </>
  );
}
