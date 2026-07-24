import React, { useState, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';

// Tooltip bubble width. Fixed (not max-width) so edge-clamping math is exact and
// the text never gets squeezed into a thin column near a screen edge.
const TOOLTIP_W = 240;

/**
 * HoverTip — a small, themed tooltip shown on hover / keyboard focus.
 *
 * Self-contained (no Radix / external dep). Wrap any button or element and pass a
 * `tip` string; the bubble appears above it on hover, matching the dashboard's
 * dark theme. It's portalled to <body> and fixed-positioned from the trigger's
 * rect, so an ancestor's overflow can't clip it.
 *
 * The wrapper is an inline-flex span, so it sits inline like the element it wraps
 * (fine for buttons / toolbar items). Do NOT use it to wrap a Radix TabsTrigger —
 * that breaks the tab grid / keyboard nav; for those, put hover handlers on the
 * trigger itself (see MarketingDashboard's tab tooltips).
 *
 * Usage:
 *   <HoverTip tip="Refresh the list">
 *     <Button …>Refresh</Button>
 *   </HoverTip>
 *
 * Props:
 *   tip       — tooltip text (falsy = render children with no tooltip)
 *   placement — 'top' (default) | 'bottom'
 *   delay     — ms before showing (default 120)
 *   className — extra classes on the inline wrapper span
 */
const HoverTip = ({ tip, children, placement = 'top', delay = 120, className = '' }) => {
  const [pos, setPos] = useState(null); // { top, left, placement } or null = hidden
  const wrapRef = useRef(null);
  const timer = useRef(null);

  const show = useCallback(() => {
    clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      const el = wrapRef.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      const anchorX = r.left + r.width / 2;       // trigger's true centre
      const top = placement === 'bottom' ? r.bottom + 8 : r.top - 8;

      // Clamp the tooltip's centre so its full width (TOOLTIP_W) stays inside the
      // viewport with an 8px margin. Without this, a trigger near the right/left
      // edge pushed the bubble off-screen and the browser squeezed it into a thin,
      // tall column (one word per line). `arrowShift` re-aligns the arrow to the
      // trigger even after the bubble has been nudged inward.
      const vw = window.innerWidth;
      const half = TOOLTIP_W / 2;
      const clampedX = Math.max(half + 8, Math.min(anchorX, vw - half - 8));
      const arrowShift = anchorX - clampedX;      // px to move the arrow off-centre

      setPos({ top, left: clampedX, arrowShift, placement });
    }, delay);
  }, [delay, placement]);

  const hide = useCallback(() => {
    clearTimeout(timer.current);
    setPos(null);
  }, []);

  if (!tip) return children;

  return (
    <span
      ref={wrapRef}
      className={`inline-flex ${className}`}
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocusCapture={show}
      onBlurCapture={hide}
    >
      {children}
      {pos && createPortal(
        <div
          role="tooltip"
          className={`fixed z-[10000] pointer-events-none -translate-x-1/2 ${
            pos.placement === 'bottom' ? '' : '-translate-y-full'
          }`}
          style={{ top: pos.top, left: pos.left }}
        >
          <div
            className="relative w-max rounded-lg border border-[#3a295a] bg-[#161630] px-3 py-2 text-xs leading-snug text-white/85 shadow-xl"
            style={{ maxWidth: TOOLTIP_W }}
          >
            {tip}
            {/* Arrow points at the trigger. When the bubble was nudged inward to
                stay on-screen, arrowShift moves the arrow back over the trigger. */}
            <span
              className={`absolute left-1/2 h-2 w-2 rotate-45 bg-[#161630] border-[#3a295a] ${
                pos.placement === 'bottom'
                  ? 'bottom-full border-t border-l'
                  : 'top-full border-b border-r'
              }`}
              style={{
                transform: `translateX(calc(-50% + ${pos.arrowShift || 0}px)) rotate(45deg)`,
                ...(pos.placement === 'bottom' ? { marginBottom: '-4px' } : { marginTop: '-4px' }),
              }}
            />
          </div>
        </div>,
        document.body,
      )}
    </span>
  );
};

export default HoverTip;
