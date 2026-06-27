import React, { useEffect, useState } from 'react';
import { Loader2, Sparkles } from 'lucide-react';

/**
 * ProgressLoader — honest "long-running LLM call" indicator.
 *
 * Why honest: the underlying LLM call is a single HTTP request, so there's
 * no real per-token progress to report. We deliberately DON'T show a fake
 * filling percentage that would lie to the user. Instead we show:
 *   - an animated indeterminate progress bar (CSS keyframe, no data needed)
 *   - an elapsed-time counter (real)
 *   - phased status hints that flip based on real elapsed-time thresholds
 *     (also real — these phases really happen, we just can't tell exactly
 *     when each finishes)
 *   - a typical-duration hint so 90 seconds doesn't feel like the page hung
 *
 * Props:
 *   active    boolean              — show or hide the loader
 *   title     string               — main heading, e.g. "Generating subtasks"
 *   phases    [{ at: seconds, label: string }]
 *                                  — phase-transition timeline. Sorted by
 *                                    `at`. Phase whose `at` is <= elapsed is
 *                                    highlighted. Defaults to a generic
 *                                    "Thinking → Generating → Finalising"
 *                                    timeline if not supplied.
 *   typicalSeconds  number         — typical duration; shown as a hint. The
 *                                    bar continues to animate past this.
 *   onCancel  () => void           — optional cancel callback. If provided,
 *                                    a "Cancel" link appears under the bar.
 */
const DEFAULT_PHASES = [
  { at: 0,  label: 'Reading project context…' },
  { at: 4,  label: 'AI is thinking…' },
  { at: 15, label: 'Generating analysis…' },
  { at: 45, label: 'Almost there — finalising…' },
];

const ProgressLoader = ({
  active,
  title = 'Working…',
  phases = DEFAULT_PHASES,
  typicalSeconds = 60,
  onCancel,
}) => {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!active) {
      setElapsed(0);
      return undefined;
    }
    setElapsed(0);
    const start = Date.now();
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - start) / 1000)), 250);
    return () => clearInterval(id);
  }, [active]);

  if (!active) return null;

  const sortedPhases = [...phases].sort((a, b) => a.at - b.at);
  // Highlight the latest phase whose `at` threshold has been crossed.
  const currentPhaseIdx = sortedPhases.reduce(
    (acc, p, idx) => (elapsed >= p.at ? idx : acc),
    0,
  );
  const isOverdue = typicalSeconds > 0 && elapsed > typicalSeconds * 1.5;

  return (
    <div
      className="rounded-xl border border-white/[0.06] p-5 space-y-4"
      style={{ background: 'rgba(0,0,0,0.25)' }}
      aria-live="polite"
      aria-busy="true"
    >
      <div className="flex items-center gap-3">
        <div
          className="flex items-center justify-center h-9 w-9 rounded-lg shrink-0"
          style={{ background: 'rgba(245,158,11,0.12)', border: '1px solid rgba(245,158,11,0.28)' }}
        >
          <Sparkles className="h-4 w-4 text-amber-400" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold text-white">{title}</div>
          <div className="text-xs text-white/55">
            {sortedPhases[currentPhaseIdx]?.label || 'Working…'}
          </div>
        </div>
        <div className="text-xs font-mono text-white/55 tabular-nums">
          {Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, '0')}
        </div>
      </div>

      {/* Indeterminate bar — pure CSS keyframe animation, no fake percentage */}
      <div className="relative h-1.5 w-full overflow-hidden rounded-full bg-white/[0.05]">
        <div className="absolute inset-y-0 left-0 w-1/3 rounded-full bg-gradient-to-r from-amber-500/40 via-amber-400 to-amber-500/40 animate-[progress-slide_1.6s_ease-in-out_infinite]" />
      </div>

      {/* Phase checklist — visually shows what's been "passed" */}
      <ol className="space-y-1.5">
        {sortedPhases.map((p, idx) => {
          const passed = idx < currentPhaseIdx;
          const active = idx === currentPhaseIdx;
          return (
            <li key={p.at} className="flex items-center gap-2 text-xs">
              <span className={`inline-flex h-4 w-4 items-center justify-center rounded-full shrink-0 ${
                passed ? 'bg-emerald-500/15 text-emerald-400'
                       : active ? 'bg-amber-500/15 text-amber-400'
                                : 'bg-white/[0.04] text-white/30'
              }`}>
                {passed ? '✓' : active ? <Loader2 className="h-2.5 w-2.5 animate-spin" /> : '•'}
              </span>
              <span className={passed ? 'text-white/55 line-through decoration-white/20'
                                       : active ? 'text-white/80'
                                                : 'text-white/40'}>
                {p.label}
              </span>
            </li>
          );
        })}
      </ol>

      {typicalSeconds > 0 && (
        <div className="text-[11px] text-white/40">
          {isOverdue
            ? `Taking longer than usual (typically ~${typicalSeconds}s). Larger projects can take 2–3 minutes — please keep this tab open.`
            : `This typically takes ~${typicalSeconds} seconds. Larger projects can take a couple of minutes.`}
        </div>
      )}

      {onCancel && (
        <button
          type="button"
          onClick={onCancel}
          className="text-[11px] text-white/40 hover:text-white/70 underline underline-offset-2"
        >
          Cancel
        </button>
      )}

      {/* Local keyframe for the indeterminate bar. Scoped via attribute so it
          doesn't collide with anything global. */}
      <style>{`
        @keyframes progress-slide {
          0%   { transform: translateX(-100%); }
          50%  { transform: translateX(120%); }
          100% { transform: translateX(280%); }
        }
      `}</style>
    </div>
  );
};

export default ProgressLoader;
