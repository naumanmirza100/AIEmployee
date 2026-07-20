import React, { useState, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';

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
      const left = r.left + r.width / 2;
      const top = placement === 'bottom' ? r.bottom + 8 : r.top - 8;
      setPos({ top, left, placement });
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
          <div className="relative max-w-[240px] rounded-lg border border-[#3a295a] bg-[#161630] px-3 py-2 text-xs leading-snug text-white/85 shadow-xl">
            {tip}
            {/* Arrow pointing at the trigger */}
            <span
              className={`absolute left-1/2 -translate-x-1/2 h-2 w-2 rotate-45 bg-[#161630] border-[#3a295a] ${
                pos.placement === 'bottom'
                  ? 'bottom-full border-t border-l'
                  : 'top-full border-b border-r'
              }`}
              style={pos.placement === 'bottom' ? { marginBottom: '-4px' } : { marginTop: '-4px' }}
            />
          </div>
        </div>,
        document.body,
      )}
    </span>
  );
};

export default HoverTip;
