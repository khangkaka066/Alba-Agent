"use client";

import { useCallback, useEffect, useRef, useState, type RefObject } from "react";
import { createPortal } from "react-dom";

export function usePanelSize(key: string, initial: number, min: number, max: number) {
  const [size, setSize] = useState(initial);
  useEffect(() => { try { const saved = Number(localStorage.getItem(key)); if (saved >= min && saved <= max) setSize(saved); } catch { /* local preferences are optional */ } }, [key, min, max]);
  useEffect(() => { const reset = () => setSize(initial); window.addEventListener("nexus:reset-layout", reset); return () => window.removeEventListener("nexus:reset-layout", reset); }, [initial]);
  const change = useCallback((next: number) => { const value = Math.max(min, Math.min(max, next)); setSize(value); try { localStorage.setItem(key, String(value)); } catch { /* storage can be disabled */ } }, [key, min, max]);
  return [size, change] as const;
}

/** A drag shield keeps the pointer in this document when it crosses a preview iframe. */
export function PanelResize({ label, value, min, max, onChange, horizontal = false, reverse = false, initial, className = "", percentOf }: {
  label: string; value: number; min: number; max: number; onChange: (next: number) => void;
  horizontal?: boolean; reverse?: boolean; initial: number; className?: string; percentOf?: RefObject<HTMLElement | null>;
}) {
  const drag = useRef<{ coordinate: number; value: number; scale: number } | null>(null);
  const [active, setActive] = useState(false);
  const change = (next: number) => onChange(Math.max(min, Math.min(max, next)));
  useEffect(() => {
    if (!active) return;
    const move = (event: PointerEvent) => {
      const start = drag.current;
      if (start) onChange(Math.max(min, Math.min(max, start.value + ((horizontal ? event.clientY : event.clientX) - start.coordinate) * start.scale * (reverse ? -1 : 1))));
    };
    const stop = () => { drag.current = null; setActive(false); };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") { event.preventDefault(); stop(); } };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", stop); window.addEventListener("pointercancel", stop); window.addEventListener("blur", stop); window.addEventListener("keydown", escape);
    return () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", stop); window.removeEventListener("pointercancel", stop); window.removeEventListener("blur", stop); window.removeEventListener("keydown", escape); };
  }, [active, horizontal, min, max, onChange, reverse]);
  return <><div role="separator" tabIndex={0} aria-label={label} aria-orientation={horizontal ? "horizontal" : "vertical"}
    aria-valuemin={min} aria-valuemax={max} aria-valuenow={Math.round(value)}
    className={`ag-panel-resize ${horizontal ? "is-horizontal" : "is-vertical"} ${active ? "is-dragging" : ""} ${className}`}
    onDoubleClick={() => change(initial)}
    onKeyDown={(event) => {
      const negative = horizontal ? "ArrowUp" : "ArrowLeft", positive = horizontal ? "ArrowDown" : "ArrowRight";
      if ([negative, positive, "Home", "End"].includes(event.key)) {
        event.preventDefault();
        change(event.key === "Home" ? min : event.key === "End" ? max : value + (event.key === positive ? 1 : -1) * (reverse ? -1 : 1) * (percentOf ? 2 : event.shiftKey ? 40 : 12));
      }
    }}
    onPointerDown={(event) => {
      if (event.button !== 0) return;
      event.preventDefault();
      event.currentTarget.setPointerCapture(event.pointerId);
      const bounds = percentOf?.current?.getBoundingClientRect();
      drag.current = { coordinate: horizontal ? event.clientY : event.clientX, value, scale: bounds ? 100 / (horizontal ? bounds.height : bounds.width) : 1 };
      setActive(true);
    }}
    />{active && createPortal(<div className={`ag-resize-shield ${horizontal ? "is-horizontal" : ""}`} aria-hidden="true" />, document.body)}</>;
}
