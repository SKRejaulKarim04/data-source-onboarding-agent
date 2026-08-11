import { useCallback, useEffect, useRef, useState } from "react";

interface ResizerOptions {
  /** localStorage key; the width survives a reload. */
  storageKey: string;
  min: number;
  /** Recomputed each render — it usually depends on the viewport. */
  max: number;
  /** Turns a pointer x-coordinate into the width this column should have. */
  measure: (clientX: number) => number;
  /**
   * The column's width right now. Needed for keyboard resizing before the first
   * drag, when `width` is still null and the real width comes from the CSS —
   * 250px for the sidebar, 45% for the chat column.
   */
  currentWidth: () => number;
}

export interface Resizer {
  /** `null` until the user resizes: the CSS default owns the width up to then. */
  width: number | null;
  dragging: boolean;
  onPointerDown: (event: React.PointerEvent<HTMLElement>) => void;
  onKeyDown: (event: React.KeyboardEvent<HTMLElement>) => void;
}

const KEYBOARD_STEP = 16;

/**
 * Drag-to-resize for one column.
 *
 * Pointer events rather than mouse events, so a trackpad, a touchscreen and a
 * pen all work, and pointer capture keeps the drag alive when the cursor
 * outruns the 4px handle.
 */
export function useResizer({
  storageKey,
  min,
  max,
  measure,
  currentWidth,
}: ResizerOptions): Resizer {
  const [width, setWidth] = useState<number | null>(() => read(storageKey));
  const [dragging, setDragging] = useState(false);

  // Refs, not deps: these change identity every render, and the move handler
  // must not be torn down and rebuilt mid-drag.
  const measureRef = useRef(measure);
  measureRef.current = measure;
  const currentRef = useRef(currentWidth);
  currentRef.current = currentWidth;
  const boundsRef = useRef({ min, max });
  boundsRef.current = { min, max };

  const clamp = useCallback((value: number) => {
    const { min: lower, max: upper } = boundsRef.current;
    return Math.round(Math.min(Math.max(value, lower), Math.max(lower, upper)));
  }, []);

  useEffect(() => {
    if (!dragging) return;

    const onMove = (event: PointerEvent) => {
      event.preventDefault();
      setWidth(clamp(measureRef.current(event.clientX)));
    };
    const stop = () => setDragging(false);

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", stop);
    window.addEventListener("pointercancel", stop);
    document.body.classList.add("is-resizing");

    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", stop);
      window.removeEventListener("pointercancel", stop);
      document.body.classList.remove("is-resizing");
    };
  }, [dragging, clamp]);

  // Persist after the drag settles rather than on every move.
  useEffect(() => {
    if (dragging || width == null) return;
    try {
      window.localStorage.setItem(storageKey, String(width));
    } catch {
      /* private mode, quota — a lost preference is not worth an error */
    }
  }, [dragging, width, storageKey]);

  const onPointerDown = useCallback(
    (event: React.PointerEvent<HTMLElement>) => {
      if (event.button !== 0) return;
      event.preventDefault();
      event.currentTarget.setPointerCapture?.(event.pointerId);
      setDragging(true);
    },
    [],
  );

  const onKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLElement>) => {
      const delta =
        event.key === "ArrowLeft"
          ? -KEYBOARD_STEP
          : event.key === "ArrowRight"
            ? KEYBOARD_STEP
            : 0;
      if (delta === 0) return;
      event.preventDefault();
      setWidth((current) => clamp((current ?? currentRef.current()) + delta));
    },
    [clamp],
  );

  return { width, dragging, onPointerDown, onKeyDown };
}

function read(key: string): number | null {
  try {
    const stored = window.localStorage.getItem(key);
    if (!stored) return null;
    const value = Number.parseInt(stored, 10);
    return Number.isFinite(value) ? value : null;
  } catch {
    return null;
  }
}
