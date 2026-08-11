import type { Resizer as ResizerState } from "../hooks/useResizer";

interface ResizerProps {
  state: ResizerState;
  label: string;
  min: number;
  max: number;
  current: number;
}

/** The 4px drag handle between two columns. */
export function Resizer({ state, label, min, max, current }: ResizerProps) {
  return (
    <div
      className={`resizer${state.dragging ? " dragging" : ""}`}
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      aria-valuemin={min}
      aria-valuemax={max}
      aria-valuenow={Math.round(current)}
      tabIndex={0}
      onPointerDown={state.onPointerDown}
      onKeyDown={state.onKeyDown}
    />
  );
}
