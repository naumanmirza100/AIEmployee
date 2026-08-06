import React from 'react';
import { Target, Upload, ArrowRight, Sparkles } from 'lucide-react';

// Shared empty-state card for PM tabs that can't do their job with no data.
// Instead of blank areas or dead dropdowns, tabs render this to steer the
// user to the one place that always works — Project Pilot — where they can
// describe or upload their way to a first project.
//
// Two variants:
//   • variant="cta"   (default) — big hero card with title + subtitle + button.
//                     Use in the main content area of a tab.
//   • variant="inline" — tighter card for smaller areas (dropdown panels,
//                        sub-tools). Same message, less visual weight.
//
// Callers pass onOpenPilot which should switch the active tab to
// 'project-pilot'. Optional `samplePrompts` renders as clickable chips; when
// clicked they call onSamplePrompt(prompt) so the parent can pre-fill Pilot.

export default function PMEmptyState({
  title = 'Start with Project Pilot',
  subtitle = 'Describe your project in plain English or upload a spec — Pilot will set it up for you.',
  buttonLabel = 'Open Project Pilot',
  icon: Icon = Target,
  variant = 'cta',
  samplePrompts = [],
  onOpenPilot,
  onSamplePrompt,
  className = '',
}) {
  const isInline = variant === 'inline';

  return (
    <div
      className={`rounded-2xl border border-cyan-400/25 bg-gradient-to-br from-cyan-500/[0.06] to-violet-500/[0.04] ${
        isInline ? 'p-5' : 'p-8 md:p-10'
      } ${className}`}
    >
      <div className={`flex ${isInline ? 'flex-row items-start gap-4' : 'flex-col items-center text-center gap-4'}`}>
        <div
          className={`rounded-xl flex items-center justify-center shrink-0 ${
            isInline ? 'h-10 w-10' : 'h-14 w-14'
          }`}
          style={{
            background: 'linear-gradient(135deg, rgba(6,182,212,0.18), rgba(139,92,246,0.12))',
            boxShadow: '0 0 20px rgba(6,182,212,0.15)',
          }}
        >
          <Icon className={`text-cyan-300 ${isInline ? 'h-5 w-5' : 'h-7 w-7'}`} />
        </div>

        <div className={`flex-1 ${isInline ? '' : 'max-w-lg'}`}>
          <h3 className={`font-semibold text-white ${isInline ? 'text-base' : 'text-lg md:text-xl'}`}>{title}</h3>
          <p className={`text-white/60 mt-1.5 ${isInline ? 'text-sm' : 'text-sm md:text-base leading-relaxed'}`}>{subtitle}</p>

          {samplePrompts.length > 0 && (
            <div className={`flex flex-wrap gap-2 mt-4 ${isInline ? '' : 'justify-center'}`}>
              {samplePrompts.map((prompt, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => {
                    onSamplePrompt?.(prompt);
                    onOpenPilot?.();
                  }}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-white/[0.08] bg-white/[0.03] text-xs text-white/70 hover:bg-white/[0.08] hover:text-white hover:border-white/20 transition"
                >
                  <Sparkles className="h-3 w-3 text-cyan-300" />
                  <span className="truncate max-w-[240px]">{prompt}</span>
                </button>
              ))}
            </div>
          )}

          {onOpenPilot && (
            <button
              type="button"
              onClick={onOpenPilot}
              className={`inline-flex items-center gap-2 rounded-lg font-semibold text-white transition ${
                isInline ? 'mt-4 px-3.5 py-2 text-sm' : 'mt-5 px-5 py-2.5 text-sm md:text-base'
              }`}
              style={{
                background: 'linear-gradient(90deg, #06b6d4 0%, #8b5cf6 100%)',
                boxShadow: '0 6px 20px rgba(6,182,212,0.25)',
              }}
            >
              <Target className={`${isInline ? 'h-4 w-4' : 'h-4 w-4 md:h-5 md:w-5'}`} />
              {buttonLabel}
              <ArrowRight className={`${isInline ? 'h-4 w-4' : 'h-4 w-4 md:h-5 md:w-5'}`} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// Convenience: an "upload" variant for tabs that need documents, not projects.
// Uses the Upload icon and a different default message.
export function PMEmptyStateUpload(props) {
  return (
    <PMEmptyState
      icon={Upload}
      title="Upload a document to get started"
      subtitle="Once a document is indexed, you can ask questions about it or have Pilot summarise it for you."
      buttonLabel="Open Project Pilot"
      {...props}
    />
  );
}
