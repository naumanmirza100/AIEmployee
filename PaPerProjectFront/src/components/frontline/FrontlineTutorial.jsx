import React, { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { X, ChevronLeft, ChevronRight, GraduationCap } from 'lucide-react';
import { useToast } from '@/components/ui/use-toast';
import { useIsMobile } from './tourUtils';

const DEFAULT_STORAGE_KEY = 'frontline_tutorial_seen_v1';

export const MAIN_TOUR_STEPS = [
  {
    title: 'Welcome to Frontline Agent 👋',
    body: "This quick tour walks you through every tab and tool on this dashboard. You can skip anytime, or replay it later from the 'Take the Tour' button in the header.",
    placement: 'center',
  },
  {
    selector: '[data-tour="stats"]',
    title: 'Your daily snapshot',
    body: 'These four cards give you an at-a-glance view: total documents indexed, total tickets, tickets resolved, and how many were auto-resolved by the AI.',
    placement: 'bottom',
  },
  {
    selector: '[data-tour="tabs"]',
    title: 'Everything lives in these tabs',
    body: 'Each tab opens a different tool. We\'ll walk through them one by one.',
    placement: 'bottom',
  },
  {
    tab: 'overview',
    selector: '[data-tour-tab="overview"]',
    title: 'Overview',
    body: 'Your home base. Admin insights show SLA status, knowledge gaps, background failure queues, and meeting action items — updated every 30 days.',
    placement: 'bottom',
  },
  {
    tab: 'documents',
    selector: '[data-tour-tab="documents"]',
    title: 'Documents',
    body: 'Upload PDFs, Word files, or other knowledge sources here. The system indexes them so the AI can answer questions based on their content.',
    placement: 'bottom',
  },
  {
    tab: 'qa',
    selector: '[data-tour-tab="qa"]',
    title: 'Knowledge Q&A',
    body: 'Ask the AI any question about your documents, procedures, or policies. It answers using the indexed knowledge base, so responses are grounded in your data.',
    placement: 'bottom',
  },
  {
    tab: 'widget',
    selector: '[data-tour-tab="widget"]',
    title: 'Chat widget',
    body: 'Configure the customer-facing chat widget — appearance, behavior, and the embed snippet you paste onto your website.',
    placement: 'bottom',
  },
  {
    tab: 'tickets',
    selector: '[data-tour-tab="tickets"]',
    title: 'Tickets',
    body: 'View and manage all support tickets. The system auto-triages by priority and category, and can auto-resolve tickets that match known solutions.',
    placement: 'bottom',
  },
  {
    tab: 'handoffs',
    selector: '[data-tour-tab="handoffs"]',
    title: 'Hand-offs',
    body: 'When the AI can\'t handle a ticket, it hands off to a human. This queue shows pending hand-offs, lets you accept them, and offers AI-drafted reply suggestions.',
    placement: 'bottom',
  },
  {
    tab: 'notifications',
    selector: '[data-tour-tab="notifications"]',
    title: 'Notifications',
    body: 'Ticket updates, meeting reminders, and system alerts land here. You\'ll never miss a follow-up.',
    placement: 'bottom',
  },
  {
    tab: 'workflows',
    selector: '[data-tour-tab="workflows"]',
    title: 'Workflows',
    body: 'Automate multi-step processes and Standard Operating Procedures. Build, run, and monitor workflows without writing code.',
    placement: 'bottom',
  },
  {
    tab: 'analytics',
    selector: '[data-tour-tab="analytics"]',
    title: 'Analytics',
    body: 'Deep performance metrics: resolution rate, average response time, auto-resolution rate, and trend charts over time.',
    placement: 'bottom',
  },
  {
    tab: 'ai-graphs',
    selector: '[data-tour-tab="ai-graphs"]',
    title: 'AI Graphs',
    body: 'Visualize how the AI connects concepts across your knowledge base — great for spotting content gaps and clusters.',
    placement: 'bottom',
  },
  {
    selector: '[data-tour="replay"]',
    title: 'Need the tour again?',
    body: "Click 'Take the Tour' here anytime to replay this walkthrough. That's it — you're all set! 🎉",
    placement: 'bottom',
  },
];

const TOOLTIP_WIDTH = 380;
const TOOLTIP_HEIGHT_ESTIMATE = 220;
const MARGIN = 16;

// `tooltipH` is the tooltip's real measured height when known; before the first
// measurement we fall back to the rough estimate. Using the real height in the
// flip/clamp math keeps a tall card (long body + 12 progress dots) from
// overflowing past the bottom edge, which cut off the footer buttons.
function computePosition(rect, placement, tooltipH = TOOLTIP_HEIGHT_ESTIMATE) {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  let top = 0;
  let left = 0;
  let pl = placement;

  function place(p) {
    if (p === 'bottom') { top = rect.bottom + MARGIN; left = rect.left; }
    else if (p === 'top') { top = rect.top - tooltipH - MARGIN; left = rect.left; }
    else if (p === 'right') { top = rect.top; left = rect.right + MARGIN; }
    else if (p === 'left') { top = rect.top; left = rect.left - TOOLTIP_WIDTH - MARGIN; }
  }

  place(pl);

  if (pl === 'right' && left + TOOLTIP_WIDTH > vw - 8) { pl = 'left'; place(pl); }
  if (pl === 'left' && left < 8) { pl = 'right'; place(pl); }
  if (pl === 'bottom' && top + tooltipH > vh - 8) { pl = 'top'; place(pl); }
  if (pl === 'top' && top < 8) { pl = 'bottom'; place(pl); }

  left = Math.max(8, Math.min(left, vw - TOOLTIP_WIDTH - 8));
  // Clamp against the real height so the card never runs off the bottom. If the
  // card is taller than the viewport, pin it to the top (8px) so the header +
  // body stay visible rather than the footer being pushed off-screen.
  top = Math.max(8, Math.min(top, Math.max(8, vh - tooltipH - 8)));

  return { top, left, placement: pl };
}

export function markTutorialSeen(key = DEFAULT_STORAGE_KEY) {
  try { localStorage.setItem(key, '1'); } catch (_) { /* ignore */ }
}

export function hasSeenTutorial(key = DEFAULT_STORAGE_KEY) {
  try { return localStorage.getItem(key) === '1'; } catch (_) { return false; }
}

export function resetTutorial(key = DEFAULT_STORAGE_KEY) {
  try {
    localStorage.removeItem(key);
    localStorage.removeItem(progressKeyFor(key));
  } catch (_) { /* ignore */ }
}

// --- Resume-progress helpers ---
// Progress is a small integer: the step index the user last saw. Saved on
// every advance so an accidental close can be resumed. Cleared on Finish.
function progressKeyFor(key) { return `${key}__progress`; }

export function saveTutorialProgress(key, index) {
  try { localStorage.setItem(progressKeyFor(key), String(index)); } catch (_) { /* ignore */ }
}

export function getTutorialProgress(key) {
  try {
    const raw = localStorage.getItem(progressKeyFor(key));
    if (raw == null) return 0;
    const n = parseInt(raw, 10);
    return Number.isFinite(n) && n > 0 ? n : 0;
  } catch (_) { return 0; }
}

export function clearTutorialProgress(key) {
  try { localStorage.removeItem(progressKeyFor(key)); } catch (_) { /* ignore */ }
}

const FrontlineTutorial = ({ open, onClose, setActiveTab, steps, storageKey, siblingKeys = [] }) => {
  const stepsArr = steps && steps.length ? steps : MAIN_TOUR_STEPS;
  const storeKey = storageKey || DEFAULT_STORAGE_KEY;
  const { toast } = useToast();
  const isMobile = useIsMobile();

  const [index, setIndex] = useState(0);
  const [targetRect, setTargetRect] = useState(null);
  const [tooltipPos, setTooltipPos] = useState({ top: 0, left: 0, placement: 'bottom' });
  const [showSkipConfirm, setShowSkipConfirm] = useState(false);
  const [skipSiblings, setSkipSiblings] = useState(false);
  // Resume prompt when reopening a tour that was closed mid-way.
  const [resumePrompt, setResumePrompt] = useState(null); // null | { atIndex }
  // Interactive-step gate: when a step declares waitFor, Next is disabled
  // until the user actually does the described action.
  const [interactiveGate, setInteractiveGate] = useState(false);
  const tooltipRef = useRef(null);

  const step = stepsArr[index];
  const isFirst = index === 0;
  const isLast = index === stepsArr.length - 1;

  useEffect(() => {
    if (!open) return;
    // If the user has partial progress from a previous session, ask before
    // jumping back in. Otherwise start from step 0 as usual.
    const progress = getTutorialProgress(storeKey);
    if (progress > 0 && progress < stepsArr.length) {
      setResumePrompt({ atIndex: progress });
      setIndex(0);
    } else {
      setResumePrompt(null);
      setIndex(0);
    }
  }, [open]);

  // Persist progress on every step change so a mid-tour close can be resumed.
  useEffect(() => {
    if (!open) return;
    if (index > 0) saveTutorialProgress(storeKey, index);
  }, [index, open, storeKey]);

  // Switch tab if this step needs it
  useEffect(() => {
    if (!open || !step) return;
    if (step.tab && typeof setActiveTab === 'function') {
      setActiveTab(step.tab);
    }
    // Optional per-step side-effect for reaching UI that isn't visible by
    // default (e.g. clicking an internal sub-tab). Fires slightly after
    // any outer tab switch so the target is present.
    if (typeof step.onEnter === 'function') {
      const t = setTimeout(() => {
        try { step.onEnter(); } catch (_) { /* non-fatal */ }
      }, step.tab ? 240 : 40);
      return () => clearTimeout(t);
    }
  }, [open, index, step, setActiveTab]);

  // Interactive step: if the step declares `waitFor: { selector, event }`,
  // the Next button is disabled until the user does that action. Great for
  // "click Create Ticket to continue" style steps.
  useEffect(() => {
    if (!open || !step) { setInteractiveGate(false); return; }
    const wf = step.waitFor;
    if (!wf || !wf.selector) { setInteractiveGate(false); return; }
    setInteractiveGate(true); // block Next until fired
    const evt = wf.event || 'click';
    let cleanup = () => {};
    const attach = () => {
      const el = document.querySelector(wf.selector);
      if (!el) return false;
      const handler = () => {
        setInteractiveGate(false);
        if (wf.autoAdvance) setTimeout(() => next(), 200);
      };
      el.addEventListener(evt, handler, { once: true });
      cleanup = () => el.removeEventListener(evt, handler);
      return true;
    };
    // If the target isn't in the DOM yet, keep retrying briefly.
    if (!attach()) {
      let tries = 0;
      const t = setInterval(() => {
        if (attach() || ++tries > 40) clearInterval(t);
      }, 100);
      return () => { clearInterval(t); cleanup(); };
    }
    return () => cleanup();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, index, step]);

  // Continuously track target element position + size while the step is active.
  // The dashboard's DOM shifts a lot after tab switches (Radix commits, async
  // data arrives, layout reflows), so a one-shot measurement drifts. We poll
  // via rAF and only push new state when the rect actually changes, so React
  // won't re-render unnecessarily.
  useEffect(() => {
    if (!open || !step) {
      setTargetRect(null);
      return;
    }

    let cancelled = false;
    let rafId = null;
    let lastRect = null;
    let lastTooltipH = TOOLTIP_HEIGHT_ESTIMATE;
    let scrollAttempted = false;
    let missingFrames = 0;
    let fellBackToCenter = false;
    // If the target element hasn't appeared after ~90 frames (~1.5s @ 60fps),
    // fall back to centered display so the tour keeps moving even if a step's
    // element is conditionally rendered / inside a collapsed panel.
    const MISSING_FRAME_LIMIT = 90;

    const rectsEqual = (a, b) =>
      a && b &&
      Math.abs(a.top - b.top) < 0.5 &&
      Math.abs(a.left - b.left) < 0.5 &&
      Math.abs(a.width - b.width) < 0.5 &&
      Math.abs(a.height - b.height) < 0.5;

    const tick = () => {
      if (cancelled) return;

      if (!step.selector || step.placement === 'center' || fellBackToCenter) {
        setTargetRect(null);
        setTooltipPos((prev) => (prev.placement === 'center' ? prev : { top: 0, left: 0, placement: 'center' }));
        rafId = requestAnimationFrame(tick);
        return;
      }

      const el = document.querySelector(step.selector);
      if (!el) {
        missingFrames += 1;
        if (missingFrames >= MISSING_FRAME_LIMIT) {
          fellBackToCenter = true;
        }
        rafId = requestAnimationFrame(tick);
        return;
      }
      // Reset the miss counter once we've found the target.
      missingFrames = 0;

      const rect = el.getBoundingClientRect();

      // If the element exists but has no size (e.g. inside a collapsed
      // container), also fall back to centered so we don't draw a 0x0 ring.
      if (rect.width < 1 || rect.height < 1) {
        missingFrames += 1;
        if (missingFrames >= MISSING_FRAME_LIMIT) {
          fellBackToCenter = true;
        }
        rafId = requestAnimationFrame(tick);
        return;
      }

      // Real rendered height of the tooltip card (falls back to the estimate on
      // the very first frame, before the card has painted for this step).
      const tooltipH = tooltipRef.current
        ? tooltipRef.current.getBoundingClientRect().height
        : TOOLTIP_HEIGHT_ESTIMATE;

      // Recompute when the target moves OR when the card's height changed enough
      // to shift the clamp (e.g. a taller step just rendered).
      if (!rectsEqual(rect, lastRect) || Math.abs(tooltipH - lastTooltipH) > 1) {
        lastRect = rect;
        lastTooltipH = tooltipH;
        // Copy — DOMRect is live-ish and freezing avoids surprises
        setTargetRect({
          top: rect.top,
          left: rect.left,
          width: rect.width,
          height: rect.height,
          right: rect.right,
          bottom: rect.bottom,
        });
        setTooltipPos(computePosition(rect, step.placement || 'bottom', tooltipH));
      }

      // Scroll into view only once per step, and only if truly off-screen
      if (!scrollAttempted && (rect.top < 0 || rect.bottom > window.innerHeight)) {
        scrollAttempted = true;
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }

      rafId = requestAnimationFrame(tick);
    };

    // Small delay for tab-switch steps so Radix's active-tab commit finishes
    const startDelay = step.tab ? 220 : 0;
    const startTimer = setTimeout(() => {
      rafId = requestAnimationFrame(tick);
    }, startDelay);

    return () => {
      cancelled = true;
      clearTimeout(startTimer);
      if (rafId) cancelAnimationFrame(rafId);
    };
  }, [open, index, step]);

  // Keyboard nav
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => {
      // When the skip-confirm modal is up, Escape dismisses it instead of
      // re-opening it, and Enter confirms.
      if (showSkipConfirm) {
        if (e.key === 'Escape') { e.preventDefault(); setShowSkipConfirm(false); }
        else if (e.key === 'Enter') { e.preventDefault(); confirmSkip(); }
        return;
      }
      if (e.key === 'Escape') handleSkip();
      else if (e.key === 'ArrowRight' || e.key === 'Enter') handleNext();
      else if (e.key === 'ArrowLeft') handlePrev();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, index, showSkipConfirm]);

  const handleNext = () => {
    if (isLast) return handleFinish();
    setIndex((i) => Math.min(i + 1, stepsArr.length - 1));
  };

  const handlePrev = () => {
    setIndex((i) => Math.max(i - 1, 0));
  };

  // Open the styled confirmation modal instead of window.confirm.
  const handleSkip = () => setShowSkipConfirm(true);

  const confirmSkip = () => {
    setShowSkipConfirm(false);
    markTutorialSeen(storeKey);
    // If the user opted in, also mark every sibling tour (e.g. all tab tours
    // for this dashboard) as seen so they don't get auto-launched later.
    if (skipSiblings && Array.isArray(siblingKeys)) {
      siblingKeys.forEach((k) => { if (k && k !== storeKey) markTutorialSeen(k); });
    }
    // Skipping = user is done for now; clear progress so a later replay
    // starts fresh instead of showing a Resume prompt.
    clearTutorialProgress(storeKey);
    onClose && onClose();
  };

  const cancelSkip = () => setShowSkipConfirm(false);

  const handleFinish = () => {
    markTutorialSeen(storeKey);
    clearTutorialProgress(storeKey);
    // Little celebration + reminder that other tours can still be replayed.
    try {
      toast({
        title: 'Tour complete 🎉',
        description: 'You can replay it anytime from the "Take the Tour" button in the header, or "Tour this tab" inside any tab.',
      });
    } catch (_) { /* toaster not mounted — safe to ignore */ }
    onClose && onClose();
  };

  // Resume-prompt handlers
  const handleResume = () => {
    if (resumePrompt) setIndex(resumePrompt.atIndex);
    setResumePrompt(null);
  };
  const handleRestart = () => {
    clearTutorialProgress(storeKey);
    setIndex(0);
    setResumePrompt(null);
  };

  if (!open || !step) return null;

  const isCentered = step.placement === 'center' || !targetRect;

  const tour = (
    <>
      {/* Full-screen backdrop — ONLY for centered steps (no highlighted element).
          When a target IS highlighted, the ring's own giant box-shadow below acts
          as the backdrop-with-a-cutout. Painting a second full-screen dim here
          would also darken the highlighted area and make its content look dull. */}
      {isCentered && (
        <div
          className="fixed inset-0 z-[9998] pointer-events-auto"
          style={{ background: 'rgba(2, 3, 8, 0.72)' }}
        />
      )}

      {/* Transparent click-catcher over the dimmed area so clicks outside the
          highlight don't fall through to the app underneath. */}
      {targetRect && !isCentered && (
        <div className="fixed inset-0 z-[9997] pointer-events-auto" />
      )}

      {/* Highlight ring around target — animates smoothly between step targets */}
      {targetRect && !isCentered && (
        <div
          className="fixed z-[9999] pointer-events-none rounded-xl"
          style={{
            top: targetRect.top - 6,
            left: targetRect.left - 6,
            width: targetRect.width + 12,
            height: targetRect.height + 12,
            boxShadow: '0 0 0 3px #f59e0b, 0 0 0 9999px rgba(2,3,8,0.72)',
            animation: 'fltPulse 1.8s ease-in-out infinite',
            transition: 'top 220ms cubic-bezier(0.4, 0, 0.2, 1), left 220ms cubic-bezier(0.4, 0, 0.2, 1), width 220ms cubic-bezier(0.4, 0, 0.2, 1), height 220ms cubic-bezier(0.4, 0, 0.2, 1)',
          }}
        />
      )}

      {/* Tooltip — bottom sheet on mobile, positioned tooltip on desktop */}
      <div
        ref={tooltipRef}
        className={`fixed z-[10000] border border-[#3a295a] bg-[#161630] shadow-2xl ${
          isMobile ? 'rounded-t-2xl' : 'rounded-xl'
        }`}
        style={
          isMobile
            ? {
                left: 0,
                right: 0,
                bottom: 0,
                width: '100%',
                maxHeight: '55vh',
                overflowY: 'auto',
                padding: '0.75rem 1rem 1rem',
                transition: 'transform 220ms cubic-bezier(0.4, 0, 0.2, 1)',
              }
            : isCentered
              ? {
                  top: '50%',
                  left: '50%',
                  transform: 'translate(-50%, -50%)',
                  width: `min(${TOOLTIP_WIDTH}px, calc(100vw - 32px))`,
                  maxHeight: 'calc(100vh - 32px)',
                  overflowY: 'auto',
                  padding: '1.25rem 1.5rem',
                }
              : {
                  top: tooltipPos.top,
                  left: tooltipPos.left,
                  width: TOOLTIP_WIDTH,
                  maxWidth: 'calc(100vw - 16px)',
                  // Never let the card exceed the viewport; if a step's content is
                  // taller than the space available below its clamped top, the card
                  // scrolls internally so the Next/Back footer is always reachable.
                  maxHeight: 'calc(100vh - 16px)',
                  overflowY: 'auto',
                  padding: '1.25rem 1.5rem',
                  transition: 'top 220ms cubic-bezier(0.4, 0, 0.2, 1), left 220ms cubic-bezier(0.4, 0, 0.2, 1)',
                }
        }
      >
        {/* Mobile drag handle — visual affordance for the bottom sheet */}
        {isMobile && (
          <div className="w-10 h-1 rounded-full bg-white/20 mx-auto mb-2" aria-hidden="true" />
        )}
        {/* Close (X) */}
        <button
          type="button"
          onClick={handleSkip}
          aria-label="Skip tutorial"
          className="absolute top-2 right-2 p-1.5 rounded-md text-white/50 hover:text-white hover:bg-white/10 transition"
        >
          <X className="h-4 w-4" />
        </button>

        {/* Progress dots */}
        <div className="flex gap-1 mb-3 pr-6">
          {stepsArr.map((_, i) => (
            <div
              key={i}
              className="flex-1 h-1 rounded-full transition-colors"
              style={{
                background: i === index ? '#f59e0b' : i < index ? '#a78bfa66' : '#3a295a',
              }}
            />
          ))}
        </div>

        {/* Step counter + title */}
        <div className="flex items-center gap-2 mb-2">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-amber-400 bg-amber-400/10 border border-amber-400/30 px-2 py-0.5 rounded-full">
            Step {index + 1} of {stepsArr.length}
          </span>
        </div>
        <h3 className="text-lg font-bold text-white mb-2 pr-4">{step.title}</h3>
        <p className="text-sm text-white/70 leading-relaxed mb-4">{step.body}</p>

        {/* Interactive step waiting indicator */}
        {interactiveGate && step?.waitFor?.hint && (
          <div className="mb-3 -mt-2 flex items-center gap-2 text-xs text-amber-300 bg-amber-400/10 border border-amber-400/30 rounded-md px-2 py-1.5">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-amber-300 animate-pulse" />
            <span>{step.waitFor.hint}</span>
          </div>
        )}

        {/* Footer */}
        <div className="flex items-center justify-between gap-2">
          <button
            type="button"
            onClick={handleSkip}
            className="text-xs text-white/50 hover:text-white/80 underline underline-offset-2 transition"
          >
            Skip tutorial
          </button>
          <div className="flex items-center gap-2">
            {!isFirst && (
              <button
                type="button"
                onClick={handlePrev}
                className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-md border border-[#3a295a] bg-[#1a1333] text-white/70 hover:bg-[#231845] hover:text-white transition"
              >
                <ChevronLeft className="h-3.5 w-3.5" />
                Back
              </button>
            )}
            <button
              type="button"
              onClick={handleNext}
              disabled={interactiveGate}
              title={interactiveGate ? (step?.waitFor?.hint || 'Do the action first to continue.') : undefined}
              className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold rounded-md text-white transition disabled:opacity-50 disabled:cursor-not-allowed"
              style={{
                background: 'linear-gradient(90deg, #f59e0b 0%, #f97316 100%)',
                boxShadow: interactiveGate ? 'none' : '0 0 8px 0 #f59e0b55',
              }}
            >
              {isLast ? (
                <>
                  <GraduationCap className="h-3.5 w-3.5" />
                  Finish
                </>
              ) : (
                <>
                  Next
                  <ChevronRight className="h-3.5 w-3.5" />
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Resume prompt — shown when the tour opens and the user has partial
          progress saved from a previous session. */}
      {resumePrompt && (
        <>
          <div className="fixed inset-0 z-[10001]" style={{ background: 'rgba(2, 3, 8, 0.55)' }} />
          <div
            role="alertdialog"
            aria-modal="true"
            className="fixed z-[10002] rounded-xl border border-[#3a295a] bg-[#161630] shadow-2xl"
            style={{
              top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
              width: 'min(400px, calc(100vw - 32px))', padding: '1.25rem 1.5rem',
            }}
          >
            <div className="flex items-start gap-3 mb-3">
              <div className="shrink-0 h-9 w-9 rounded-full bg-amber-400/15 border border-amber-400/40 flex items-center justify-center">
                <GraduationCap className="h-5 w-5 text-amber-300" />
              </div>
              <div className="min-w-0">
                <h3 className="text-base font-bold text-white mb-1">Pick up where you left off?</h3>
                <p className="text-sm text-white/70 leading-relaxed">
                  You closed this tour on <span className="text-amber-300 font-semibold">step {resumePrompt.atIndex + 1}</span> of {stepsArr.length}. Resume from there, or start over from the beginning.
                </p>
              </div>
            </div>
            <div className="flex items-center justify-end gap-2 mt-4">
              <button type="button" onClick={handleRestart}
                className="px-3.5 py-1.5 text-xs font-semibold rounded-md border border-[#3a295a] bg-[#1a1333] text-white/80 hover:bg-[#231845] hover:text-white transition">
                Start over
              </button>
              <button type="button" onClick={handleResume} autoFocus
                className="inline-flex items-center gap-1 px-3.5 py-1.5 text-xs font-semibold rounded-md text-white transition"
                style={{ background: 'linear-gradient(90deg, #f59e0b 0%, #f97316 100%)', boxShadow: '0 0 8px 0 #f59e0b55' }}>
                Resume at step {resumePrompt.atIndex + 1}
              </button>
            </div>
          </div>
        </>
      )}

      {/* Skip-confirmation modal — replaces the browser's window.confirm
          with a card in the same visual language as the tour. */}
      {showSkipConfirm && (
        <>
          {/* Extra backdrop above the tour overlay so nothing behind is clickable */}
          <div
            className="fixed inset-0 z-[10001]"
            style={{ background: 'rgba(2, 3, 8, 0.55)' }}
            onClick={cancelSkip}
          />
          <div
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="flt-skip-title"
            className="fixed z-[10002] rounded-xl border border-[#3a295a] bg-[#161630] shadow-2xl"
            style={{
              top: '50%',
              left: '50%',
              transform: 'translate(-50%, -50%)',
              width: 'min(400px, calc(100vw - 32px))',
              padding: '1.25rem 1.5rem',
            }}
          >
            <div className="flex items-start gap-3 mb-3">
              <div className="shrink-0 h-9 w-9 rounded-full bg-amber-400/15 border border-amber-400/40 flex items-center justify-center">
                <span className="text-amber-300 font-bold text-lg leading-none">!</span>
              </div>
              <div className="min-w-0">
                <h3 id="flt-skip-title" className="text-base font-bold text-white mb-1">Skip this tour?</h3>
                <p className="text-sm text-white/70 leading-relaxed">
                  You can replay it anytime from the <span className="text-amber-300 font-semibold">"Take the Tour"</span> button in the header, or <span className="text-amber-300 font-semibold">"Tour this tab"</span> inside any tab.
                </p>
              </div>
            </div>
            {Array.isArray(siblingKeys) && siblingKeys.length > 0 && (
              <label className="flex items-start gap-2 mt-1 mb-2 pl-12 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={skipSiblings}
                  onChange={(e) => setSkipSiblings(e.target.checked)}
                  className="mt-0.5 h-3.5 w-3.5 accent-amber-500"
                />
                <span className="text-xs text-white/70 leading-relaxed">
                  Also skip the other <span className="text-amber-300 font-semibold">{siblingKeys.length}</span> tab tours for this dashboard. You can still replay any of them from its "Tour this tab" button.
                </span>
              </label>
            )}
            <div className="flex items-center justify-end gap-2 mt-4">
              <button
                type="button"
                onClick={cancelSkip}
                autoFocus
                className="px-3.5 py-1.5 text-xs font-semibold rounded-md border border-[#3a295a] bg-[#1a1333] text-white/80 hover:bg-[#231845] hover:text-white transition"
              >
                Continue tour
              </button>
              <button
                type="button"
                onClick={confirmSkip}
                className="inline-flex items-center gap-1 px-3.5 py-1.5 text-xs font-semibold rounded-md text-white transition"
                style={{
                  background: 'linear-gradient(90deg, #f59e0b 0%, #f97316 100%)',
                  boxShadow: '0 0 8px 0 #f59e0b55',
                }}
              >
                Skip tutorial
              </button>
            </div>
          </div>
        </>
      )}

      {/* Pulse animation keyframes */}
      <style>{`
        @keyframes fltPulse {
          0%, 100% { box-shadow: 0 0 0 3px #f59e0b, 0 0 0 9999px rgba(2,3,8,0.72); }
          50%      { box-shadow: 0 0 0 7px #f59e0b88, 0 0 0 9999px rgba(2,3,8,0.72); }
        }
      `}</style>
    </>
  );

  // Portal to <body> so no ancestor transform/filter/perspective can shift our
  // fixed-positioned elements away from the viewport origin.
  return createPortal(tour, document.body);
};

export default FrontlineTutorial;
