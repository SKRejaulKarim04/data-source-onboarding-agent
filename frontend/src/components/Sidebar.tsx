import { forwardRef } from "react";
import "./Sidebar.css";
import { PlusIcon, TrashIcon } from "./Icons";
import type { RequestSummary } from "../api/types";

interface SidebarProps {
  requests: RequestSummary[];
  activeId: string | null;
  /** `null` means "leave it to the CSS" — the user has not resized it. */
  width: number | null;
  onNewRequest: () => void;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
}

/** Request history. Mirrors `GET /api/requests`, newest first. */
export const Sidebar = forwardRef<HTMLElement, SidebarProps>(function Sidebar(
  { requests, activeId, width, onNewRequest, onSelect, onDelete },
  ref,
) {
  return (
    <aside
      className="sidebar"
      ref={ref}
      style={width != null ? { width: `${width}px` } : undefined}
    >
      <div className="sidebar-header">
        <button className="new-btn" onClick={onNewRequest} type="button">
          <PlusIcon />
          New Request
        </button>
      </div>

      <div className="history-list scroll-y">
        {requests.length === 0 ? (
          <div className="history-empty">No requests yet</div>
        ) : (
          requests.map((request) => (
            <div
              key={request.id}
              className={`history-item${request.id === activeId ? " active" : ""}`}
            >
              <button
                type="button"
                className="history-content"
                onClick={() => onSelect(request.id)}
                aria-current={request.id === activeId}
              >
                <div className="history-title">
                  {request.prompt || "New Request"}
                </div>
                <div className="history-status">{request.status}</div>
              </button>
              <button
                type="button"
                className="history-del"
                title="Delete request"
                aria-label={`Delete request: ${request.prompt || request.id}`}
                onClick={() => onDelete(request.id)}
              >
                <TrashIcon />
              </button>
            </div>
          ))
        )}
      </div>
    </aside>
  );
});
