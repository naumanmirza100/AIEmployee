import React, { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { X, ArrowRight, Sparkles, RotateCcw } from 'lucide-react';

/**
 * "How it works" onboarding modal — a high-level, animated walkthrough of how an
 * agent works, shown automatically the first time a user opens that agent.
 *
 * Layout is HORIZONTAL: steps flow left→right as connected nodes, and they reveal
 * one at a time like a short video — node 1 appears, ~1.4s later the connector to
 * node 2 draws in and node 2 floats up, and so on. A "Replay" control re-runs the
 * sequence; "Skip"/"Got it" close it.
 *
 * Reusable across agents — pass a title, subtitle and an ordered `steps` array.
 * "Seen" state is the caller's job (localStorage), so this stays presentational.
 *
 * steps: [{ icon?: LucideIcon, title: string, body: string }]
 */

const STEP_INTERVAL_MS = 2000; // gap between each node revealing — paced so a reader can finish each point

const HowItWorksModal = ({
  open,
  onClose,
  title,
  subtitle,
  steps = [],
  primaryLabel = 'Got it',
  accent = '#a259ff',
}) => {
  // How many steps are currently revealed (drives the staggered animation).
  const [revealed, setRevealed] = useState(0);
  const timers = useRef([]);
  const scrollRef = useRef(null);        // the horizontal scroll container
  const nodeRefs = useRef([]);           // one per node, to scroll the newest into view

  const clearTimers = () => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
  };

  const runSequence = () => {
    clearTimers();
    setRevealed(0);
    // Reveal step 0 immediately, then the rest one-by-one on an interval.
    steps.forEach((_, i) => {
      const t = setTimeout(() => setRevealed(i + 1), i * STEP_INTERVAL_MS + 150);
      timers.current.push(t);
    });
  };

  useEffect(() => {
    if (open) runSequence();
    else clearTimers();
    return clearTimers;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, steps.length]);

  // Smoothly glide the flow into view as steps reveal. Native scrollTo({smooth})
  // only fired once a node crossed the right edge, so it moved in abrupt jumps.
  // Instead we run our own eased tween over ~700ms toward centring the newest
  // node — a long, continuous glide rather than a per-step jerk. Row is
  // left-aligned (justify-start) so offsetLeft is accurate.
  useEffect(() => {
    if (!open) return;
    const container = scrollRef.current;
    if (!container) return;

    // Start of a run → snap to the left so step 1 is on screen.
    if (revealed === 0) {
      container.scrollLeft = 0;
      return;
    }

    const node = nodeRefs.current[revealed - 1];
    if (!node) return;
    if (container.scrollWidth <= container.clientWidth) return; // no overflow yet

    // DON'T centre the new node — that shoves the whole view forward and yanks
    // already-visible points off screen before they've been read. Instead scroll
    // the MINIMUM needed to bring the newest node just inside the right edge (with
    // a small trailing gap), so as many earlier points as possible stay put.
    const maxScroll = container.scrollWidth - container.clientWidth;
    const nodeRight = node.offsetLeft + node.offsetWidth;
    const viewRight = container.scrollLeft + container.clientWidth;

    // Already fully visible? Leave the scroll exactly where it is.
    if (nodeRight <= viewRight - 8) return;

    const TRAIL_GAP = 40; // hint of the next connector past the new node
    const target = Math.max(0, Math.min(nodeRight - container.clientWidth + TRAIL_GAP, maxScroll));

    const start = container.scrollLeft;
    const delta = target - start;
    if (Math.abs(delta) < 1) return;

    const DURATION = 700;
    // easeInOutCubic — slow start, quick middle, gentle stop; reads as a glide.
    const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

    let raf = 0;
    let startTs = null;
    const step = (ts) => {
      if (startTs === null) startTs = ts;
      const p = Math.min(1, (ts - startTs) / DURATION);
      container.scrollLeft = start + delta * ease(p);
      if (p < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [open, revealed]);

  if (!open) return null;

  const allRevealed = revealed >= steps.length;

  const content = (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-[9998]"
        style={{ background: 'rgba(2, 3, 8, 0.75)' }}
        onClick={onClose}
      />

      {/* Card — wide, to fit the horizontal flow */}
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="fixed z-[9999] left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-[min(1040px,calc(100vw-32px))] max-h-[calc(100vh-32px)] overflow-y-auto rounded-2xl border border-[#3a295a] bg-[#161630] shadow-2xl"
      >
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="absolute top-3 right-3 z-10 p-1.5 rounded-md text-white/50 hover:text-white hover:bg-white/10 transition"
        >
          <X className="h-4 w-4" />
        </button>

        {/* Header */}
        <div className="px-6 pt-6 pb-4 border-b border-white/10">
          <div className="flex items-center gap-2.5">
            <div
              className="h-9 w-9 rounded-lg flex items-center justify-center shrink-0"
              style={{ background: `${accent}22`, border: `1px solid ${accent}55` }}
            >
              <Sparkles className="h-4 w-4" style={{ color: accent }} />
            </div>
            <div className="min-w-0 pr-6">
              <h2 className="text-lg font-bold text-white leading-tight">{title}</h2>
              {subtitle && <p className="text-xs text-white/50 mt-0.5">{subtitle}</p>}
            </div>
          </div>
        </div>

        {/* Horizontal animated flow. On small screens it wraps; the connectors
            hide when wrapped so we never draw a line into empty space. */}
        <div ref={scrollRef} className="px-6 py-8 overflow-x-auto no-scrollbar">
          {/* Left-aligned always: the full row lives in the DOM (nodes just fade
              in), so centring it on the full width pushed step 1 off the left edge.
              justify-start keeps step 1 visible; the row scrolls right if it
              overflows. */}
          <div className="flex items-stretch gap-0 w-max justify-start">
            {steps.map((step, i) => {
              const StepIcon = step.icon;
              const isShown = i < revealed;
              const connectorShown = i < revealed - 1; // line to the NEXT node

              return (
                <React.Fragment key={i}>
                  {/* Node */}
                  <div
                    ref={(el) => { nodeRefs.current[i] = el; }}
                    className="w-[184px] shrink-0 flex flex-col items-center text-center px-1.5 transition-all duration-500 ease-out"
                    style={{
                      opacity: isShown ? 1 : 0,
                      transform: isShown ? 'translateY(0)' : 'translateY(16px)',
                    }}
                  >
                    <div
                      className="relative h-14 w-14 rounded-2xl flex items-center justify-center mb-3"
                      style={{
                        background: `linear-gradient(135deg, ${accent} 0%, #7c3aed 100%)`,
                        boxShadow: isShown ? `0 0 18px 0 ${accent}66` : 'none',
                        transition: 'box-shadow 500ms ease-out',
                      }}
                    >
                      {StepIcon
                        ? <StepIcon className="h-6 w-6 text-white" />
                        : <span className="text-lg font-bold text-white">{i + 1}</span>}
                      {/* Step number badge */}
                      <span
                        className="absolute -top-1.5 -right-1.5 h-5 w-5 rounded-full bg-[#161630] border border-white/20 text-white text-[11px] font-bold flex items-center justify-center"
                      >
                        {i + 1}
                      </span>
                    </div>
                    {/* Fixed title height (room for 2 lines) so every body starts
                        on the same baseline — keeps the row visually even. */}
                    <h3 className="text-sm font-semibold text-white leading-snug min-h-[40px] flex items-center justify-center">
                      {step.title}
                    </h3>
                    <p className="text-[12px] text-white/55 leading-relaxed mt-1">{step.body}</p>
                  </div>

                  {/* Connector to the next node — a line that grows in */}
                  {i < steps.length - 1 && (
                    <div className="hidden md:flex items-start pt-[26px] w-8 shrink-0">
                      <div className="relative h-0.5 w-full rounded-full bg-white/10 overflow-hidden">
                        <div
                          className="absolute inset-y-0 left-0 rounded-full"
                          style={{
                            background: `linear-gradient(90deg, ${accent}, #7c3aed)`,
                            width: connectorShown ? '100%' : '0%',
                            transition: 'width 450ms ease-out',
                          }}
                        />
                      </div>
                    </div>
                  )}
                </React.Fragment>
              );
            })}
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-white/10 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={onClose}
              className="text-xs text-white/45 hover:text-white/75 transition"
            >
              Skip
            </button>
            <button
              type="button"
              onClick={runSequence}
              className="inline-flex items-center gap-1.5 text-xs text-white/45 hover:text-white/75 transition"
              title="Replay the animation"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              Replay
            </button>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-semibold rounded-lg text-white transition"
            style={{
              background: `linear-gradient(90deg, ${accent} 0%, #7c3aed 100%)`,
              boxShadow: `0 0 12px 0 ${accent}55`,
              // Subtle pulse until the animation finishes, so users don't click away early.
              opacity: allRevealed ? 1 : 0.85,
            }}
          >
            {primaryLabel}
            <ArrowRight className="h-4 w-4" />
          </button>
        </div>
      </div>
    </>
  );

  // Portal to body so no ancestor transform shifts the fixed positioning.
  return createPortal(content, document.body);
};

export default HowItWorksModal;
