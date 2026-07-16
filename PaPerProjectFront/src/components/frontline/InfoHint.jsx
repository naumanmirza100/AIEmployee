import React, { useState, useRef, useEffect, useLayoutEffect, createContext, useContext, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { useToast } from '@/components/ui/use-toast';

const POPOVER_WIDTH = 320;
const POPOVER_HEIGHT_ESTIMATE = 140;
const MARGIN = 10;

const HINTS_ENABLED_KEY = 'frontline_hints_enabled_v1';

// Read the persisted preference. Default = enabled.
function readEnabled() {
  try {
    const raw = localStorage.getItem(HINTS_ENABLED_KEY);
    if (raw === null) return true;
    return raw === '1';
  } catch (_) {
    return true;
  }
}

// Shared context so every <InfoHint /> and the header toggle stay in sync
// without having to lift a shared parent state to every anchor site.
const HintsContext = createContext({
  enabled: true,
  setEnabled: () => {},
  toggle: () => {},
});

export function HintsProvider({ children }) {
  const [enabled, setEnabledState] = useState(readEnabled);
  const { toast } = useToast();
  // Suppress the initial-mount toast; only fire on genuine user toggles.
  const isFirstToggle = useRef(true);

  const setEnabled = useCallback((next) => {
    setEnabledState((prev) => {
      const val = typeof next === 'function' ? next(prev) : !!next;
      try { localStorage.setItem(HINTS_ENABLED_KEY, val ? '1' : '0'); } catch (_) { /* ignore */ }
      // Fire a brief confirmation toast so the flip is discoverable.
      if (!isFirstToggle.current && val !== prev) {
        try {
          toast({
            title: val ? 'Hints on' : 'Hints off',
            description: val
              ? 'The ! help icons are visible on every element.'
              : 'The ! help icons are hidden. Click the toggle again to show them.',
          });
        } catch (_) { /* toaster not mounted */ }
      }
      isFirstToggle.current = false;
      return val;
    });
  }, [toast]);

  const toggle = useCallback(() => setEnabled((v) => !v), [setEnabled]);

  return (
    <HintsContext.Provider value={{ enabled, setEnabled, toggle }}>
      {children}
    </HintsContext.Provider>
  );
}

export function useHints() {
  return useContext(HintsContext);
}

// Small "!" badge that opens a tutorial-style card explaining what an
// element does. Rendered inline; the popover portals to <body> so no
// ancestor transform/filter/perspective can shift it.
const InfoHint = ({ title, body, className = '' }) => {
  const { enabled } = useHints();
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState({ top: 0, left: 0, placement: 'bottom' });
  const btnRef = useRef(null);
  const popRef = useRef(null);

  // When hints are turned off, close any lingering popover so it can't
  // outlive the toggle, and render nothing at the anchor site.
  useEffect(() => { if (!enabled && open) setOpen(false); }, [enabled, open]);

  const computePos = () => {
    if (!btnRef.current) return;
    const r = btnRef.current.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    // Prefer below the icon, centered on it. Fall back to above if it clips.
    let top = r.bottom + MARGIN;
    let placement = 'bottom';
    if (top + POPOVER_HEIGHT_ESTIMATE > vh - 8) {
      top = r.top - POPOVER_HEIGHT_ESTIMATE - MARGIN;
      placement = 'top';
    }
    let left = r.left + r.width / 2 - POPOVER_WIDTH / 2;
    left = Math.max(8, Math.min(left, vw - POPOVER_WIDTH - 8));
    top = Math.max(8, top);

    setPos({ top, left, placement });
  };

  useLayoutEffect(() => {
    if (!open) return;
    computePos();
  }, [open]);

  useEffect(() => {
    if (!open) return;

    const onKey = (e) => {
      if (e.key === 'Escape') setOpen(false);
    };
    const onClick = (e) => {
      if (btnRef.current && btnRef.current.contains(e.target)) return;
      if (popRef.current && popRef.current.contains(e.target)) return;
      setOpen(false);
    };
    const onScroll = () => computePos();

    window.addEventListener('keydown', onKey);
    window.addEventListener('mousedown', onClick);
    window.addEventListener('resize', onScroll);
    window.addEventListener('scroll', onScroll, true);

    return () => {
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('mousedown', onClick);
      window.removeEventListener('resize', onScroll);
      window.removeEventListener('scroll', onScroll, true);
    };
  }, [open]);

  // Bail out AFTER all hooks are declared — this preserves hook order
  // when the toggle flips (React would otherwise throw
  // "Rendered more hooks than during the previous render").
  if (!enabled) return null;

  return (
    <>
      <button
        ref={btnRef}
        type="button"
        aria-label={title ? `What is: ${title}` : 'What does this do?'}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setOpen((v) => !v);
        }}
        className={`inline-flex items-center justify-center h-5 w-5 shrink-0 rounded-full border border-amber-400/50 bg-amber-400/10 text-amber-300 hover:bg-amber-400/25 hover:text-amber-200 hover:border-amber-400/70 transition text-[11px] font-bold leading-none cursor-pointer ${className}`}
      >
        !
      </button>

      {open && createPortal(
        <div
          ref={popRef}
          role="dialog"
          className="fixed z-[10000] rounded-xl border border-[#3a295a] bg-[#161630] shadow-2xl px-4 py-3"
          style={{
            top: pos.top,
            left: pos.left,
            width: POPOVER_WIDTH,
            maxWidth: 'calc(100vw - 16px)',
          }}
        >
          <button
            type="button"
            onClick={() => setOpen(false)}
            aria-label="Close"
            className="absolute top-1.5 right-1.5 p-1 rounded-md text-white/50 hover:text-white hover:bg-white/10 transition"
          >
            <X className="h-3.5 w-3.5" />
          </button>
          {title && (
            <div className="flex items-center gap-2 mb-1.5 pr-6">
              <span className="inline-flex items-center justify-center h-4 w-4 rounded-full bg-amber-400/20 text-amber-300 text-[10px] font-bold leading-none">
                !
              </span>
              <h4 className="text-sm font-bold text-white leading-tight">{title}</h4>
            </div>
          )}
          <p className="text-xs text-white/70 leading-relaxed whitespace-pre-wrap">{body}</p>
        </div>,
        document.body
      )}
    </>
  );
};

export default InfoHint;
