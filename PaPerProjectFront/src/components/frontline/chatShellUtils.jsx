// Shared utilities for the three floating chats (Frontline / HR / PM).
// These implement:
//   * useDraggableResizable — drag from a handle, resize from a corner,
//     persist width/height/position per storage key.
//   * ContextIndicator      — a small "↑ N messages of context" chip.
//   * useSlashAutocomplete  — attaches to the input; dynamically resolves
//     slash-command arguments by calling a `resolver` fn.
//   * ElapsedTimer          — self-updating "3.4s" clock, used inside the
//     "Thinking…" spinner so users can see how long the current request has
//     been running.
//
// Kept intentionally lightweight — no drag library, no CSS-in-JS beyond
// inline styles. All three chats consume the same primitives so their UX
// stays in sync as this file evolves.

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { ArrowUp } from 'lucide-react';
import { useIsMobile } from './tourUtils';

// Re-export so chat files that already import from chatShellUtils can grab
// the mobile flag without a second import.
export { useIsMobile };


// ---------- Live "elapsed time" clock for the thinking spinner ------------

/**
 * Self-updating elapsed-time counter. Renders "3.4s" and ticks every 100ms.
 *
 * Owns its own interval so consumers just drop it in — no state plumbing.
 * Cleans up on unmount, and pauses safely if the browser tab is throttled
 * (setInterval keeps working when hidden but the drift is fine for our use).
 *
 * Props:
 *   since       — timestamp (ms via performance.now() or Date.now()) when
 *                 the request started. If null/undefined, renders nothing.
 *   className   — optional wrapper class.
 *   precision   — decimal places to show (default 1). Bump to 2 for very
 *                 short-running local operations.
 */
export function ElapsedTimer({ since, className = '', precision = 1 }) {
  const [now, setNow] = useState(() => (
    (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now()
  ));

  useEffect(() => {
    if (since == null) return undefined;
    const id = setInterval(() => {
      setNow((typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now());
    }, 100);
    return () => clearInterval(id);
  }, [since]);

  if (since == null) return null;
  const seconds = Math.max(0, (now - since) / 1000);
  return <span className={className}>{seconds.toFixed(precision)}s</span>;
}

const MIN_WIDTH = 340;
const MIN_HEIGHT = 380;
const DEFAULT_WIDTH = 420;
const DEFAULT_HEIGHT = 580;

// ---------- Draggable + resizable ---------------------------------------

export function useDraggableResizable(storageKey, { defaultWidth = DEFAULT_WIDTH, defaultHeight = DEFAULT_HEIGHT } = {}) {
  const key = `${storageKey}__geom_v1`;
  const [geom, setGeom] = useState(() => readGeom(key, { defaultWidth, defaultHeight }));
  const isMobile = useIsMobile();

  useEffect(() => {
    try { localStorage.setItem(key, JSON.stringify(geom)); } catch (_) { /* ignore */ }
  }, [key, geom]);

  const dragState = useRef(null);
  const resizeState = useRef(null);

  // Drag handlers — attach to the header
  const dragHandleProps = {
    onMouseDown: (e) => {
      // Left-click only, and don't hijack clicks on child buttons inside the header
      if (e.button !== 0) return;
      if (e.target.closest('button')) return;
      e.preventDefault();
      dragState.current = {
        startX: e.clientX,
        startY: e.clientY,
        startRight: geom.right,
        startBottom: geom.bottom,
      };
      const onMove = (ev) => {
        if (!dragState.current) return;
        const dx = ev.clientX - dragState.current.startX;
        const dy = ev.clientY - dragState.current.startY;
        setGeom((g) => clampGeom({
          ...g,
          right: Math.max(8, dragState.current.startRight - dx),
          bottom: Math.max(8, dragState.current.startBottom - dy),
        }));
      };
      const onUp = () => {
        dragState.current = null;
        window.removeEventListener('mousemove', onMove);
        window.removeEventListener('mouseup', onUp);
      };
      window.addEventListener('mousemove', onMove);
      window.addEventListener('mouseup', onUp);
    },
    style: { cursor: 'grab' },
    title: 'Drag to reposition',
  };

  // Resize handlers — attach to the resize corner
  const resizeHandleProps = {
    onMouseDown: (e) => {
      if (e.button !== 0) return;
      e.preventDefault();
      e.stopPropagation();
      resizeState.current = {
        startX: e.clientX,
        startY: e.clientY,
        startWidth: geom.width,
        startHeight: geom.height,
      };
      const onMove = (ev) => {
        if (!resizeState.current) return;
        const dx = ev.clientX - resizeState.current.startX;
        const dy = ev.clientY - resizeState.current.startY;
        setGeom((g) => clampGeom({
          ...g,
          // Resizing from the TOP-LEFT corner: bigger width = drag left
          // (dx negative), bigger height = drag up (dy negative).
          width: Math.max(MIN_WIDTH, resizeState.current.startWidth - dx),
          height: Math.max(MIN_HEIGHT, resizeState.current.startHeight - dy),
        }));
      };
      const onUp = () => {
        resizeState.current = null;
        window.removeEventListener('mousemove', onMove);
        window.removeEventListener('mouseup', onUp);
      };
      window.addEventListener('mousemove', onMove);
      window.addEventListener('mouseup', onUp);
    },
  };

  // On mobile, render as a full-width bottom sheet — the desktop drag/resize
  // model doesn't make sense on a phone.
  const containerStyle = isMobile
    ? {
        left: 0,
        right: 0,
        bottom: 0,
        top: 'auto',
        width: '100vw',
        height: '85vh',
        maxHeight: '85vh',
        maxWidth: '100vw',
        borderRadius: '16px 16px 0 0',
      }
    : {
        right: geom.right,
        bottom: geom.bottom,
        width: geom.width,
        height: geom.height,
        maxHeight: 'calc(100vh - 40px)',
        maxWidth: 'calc(100vw - 32px)',
      };

  // On mobile we disable drag + resize so the sheet doesn't move under a fat finger.
  const mobileSafeDrag = isMobile ? { style: {}, title: undefined } : dragHandleProps;
  const mobileSafeResize = isMobile ? { onMouseDown: () => {} } : resizeHandleProps;

  return {
    containerStyle,
    dragHandleProps: mobileSafeDrag,
    resizeHandleProps: mobileSafeResize,
    isMobile,
  };
}

function readGeom(key, { defaultWidth, defaultHeight }) {
  try {
    const raw = localStorage.getItem(key);
    if (raw) {
      const g = JSON.parse(raw);
      if (g && typeof g === 'object') return clampGeom({ ...defaults(defaultWidth, defaultHeight), ...g });
    }
  } catch (_) { /* ignore */ }
  return defaults(defaultWidth, defaultHeight);
}

function defaults(w, h) { return { right: 24, bottom: 24, width: w, height: h }; }

function clampGeom(g) {
  const vw = typeof window !== 'undefined' ? window.innerWidth : 1200;
  const vh = typeof window !== 'undefined' ? window.innerHeight : 800;
  return {
    right: Math.max(0, Math.min(g.right, Math.max(0, vw - MIN_WIDTH))),
    bottom: Math.max(0, Math.min(g.bottom, Math.max(0, vh - MIN_HEIGHT))),
    width: Math.max(MIN_WIDTH, Math.min(g.width, vw - 16)),
    height: Math.max(MIN_HEIGHT, Math.min(g.height, vh - 40)),
  };
}

// ---------- Multi-turn context indicator --------------------------------

export const ContextIndicator = ({ count }) => {
  if (!count || count < 2) return null;
  return (
    <div
      className="flex items-center gap-1 px-2 py-0.5 rounded-full border border-white/10 bg-white/[0.04] text-[10px] text-white/50 self-start"
      title="Number of previous messages sent to the AI as context on the next turn"
    >
      <ArrowUp className="h-2.5 w-2.5" />
      <span>{count} of context</span>
    </div>
  );
};

// ---------- Resize corner visual ----------------------------------------

export const ResizeCorner = ({ handleProps }) => {
  const isMobile = useIsMobile();
  if (isMobile) return null;
  return (
    <div
      {...handleProps}
      title="Drag to resize"
      className="absolute top-0 left-0 w-4 h-4 cursor-nwse-resize z-10 group"
      style={{ userSelect: 'none' }}
    >
      <svg viewBox="0 0 16 16" className="w-full h-full opacity-30 group-hover:opacity-70 transition-opacity">
        <path d="M2 14 L14 2 M6 14 L14 6 M10 14 L14 10" stroke="white" strokeWidth="1.5" fill="none" strokeLinecap="round" />
      </svg>
    </div>
  );
};

// ---------- Mobile bottom-sheet drag handle -----------------------------
// A small pill at the top of the chat, similar to iOS/Android sheets.
// Purely visual — the mobile chat is fixed and dismissed via the header X.
// Renders nothing on desktop.

export const MobileSheetHandle = () => {
  const isMobile = useIsMobile();
  if (!isMobile) return null;
  return <div className="w-10 h-1 rounded-full bg-white/25 mx-auto my-1.5 shrink-0" aria-hidden="true" />;
};
