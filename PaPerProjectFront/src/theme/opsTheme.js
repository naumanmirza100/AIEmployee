/**
 * Operations Agent design system — single source of truth for the
 * Operations / Frontline / HR / PM dashboards.
 *
 * Use these tokens instead of hard-coded colors so future tweaks
 * (e.g. accent shift, dark mode adjustment) only need to change here.
 *
 * Accent system:
 *   AMBER  (#f59e0b) — primary accent: h2 headings, primary buttons,
 *                      stat highlights, active tab gradient.
 *   VIOLET (#8b5cf6) — secondary accent: h3 headings, sub-section dots,
 *                      info chips, secondary buttons.
 *   EMERALD (#10b981) — success / positive metric accent.
 *   ROSE   (#ef4444) — error / negative metric accent.
 *
 * Surface system (cards / panels):
 *   bg:     rgba(0, 0, 0, 0.15)       — main card body
 *   bg-alt: rgba(255, 255, 255, 0.02) — lighter inner panel
 *   border: rgba(255, 255, 255, 0.06) — default
 *   border-hover: rgba(255, 255, 255, 0.12)
 *
 * Text system:
 *   heading:        text-white
 *   heading-muted:  text-white/80
 *   body:           text-white/65
 *   body-muted:     text-white/55
 *   subtle:         text-white/30
 *   section-label:  text-white/70 uppercase tracking-wider
 */

// ── Background ──────────────────────────────────────────────
export const OPS_GRADIENT_BG =
  'linear-gradient(135deg, #020308 0%, #0a0a1a 25%, #0d0b1f 50%, #0f0a20 75%, #020308 100%)';

// ── Accent colors ───────────────────────────────────────────
export const OPS_AMBER = '#f59e0b';
export const OPS_AMBER_SOFT = 'rgba(245,158,11,0.12)';
export const OPS_AMBER_BORDER = 'rgba(245,158,11,0.28)';

export const OPS_VIOLET = '#8b5cf6';
export const OPS_VIOLET_SOFT = 'rgba(139,92,246,0.12)';
export const OPS_VIOLET_BORDER = 'rgba(139,92,246,0.28)';

export const OPS_EMERALD = '#10b981';
export const OPS_EMERALD_SOFT = 'rgba(16,185,129,0.12)';

export const OPS_ROSE = '#ef4444';
export const OPS_ROSE_SOFT = 'rgba(239,68,68,0.12)';

// ── Surface ─────────────────────────────────────────────────
export const OPS_CARD_BG = 'rgba(0,0,0,0.15)';
export const OPS_CARD_BG_LIGHT = 'rgba(255,255,255,0.02)';
export const OPS_CARD_BORDER = 'rgba(255,255,255,0.06)';
export const OPS_CARD_BORDER_HOVER = 'rgba(255,255,255,0.12)';

// ── Reusable Tailwind class strings ─────────────────────────
// A standard card: rounded, faint border, subtle background. Pair with
// `style={{ background: OPS_CARD_BG }}` for the body fill.
export const opsCardClass =
  'rounded-xl border border-white/[0.06]';

// Hoverable card variant — adds gentle border lift on hover.
export const opsCardHoverClass =
  'rounded-xl border border-white/[0.06] transition-colors hover:border-white/[0.12]';

// Lighter inner panel for grouping content inside a parent card.
export const opsInnerPanelClass =
  'rounded-lg p-3 border border-white/[0.04]';

// Standard text scales.
export const opsTextHeading = 'text-white';
export const opsTextHeadingMuted = 'text-white/80';
export const opsTextBody = 'text-white/65';
export const opsTextBodyMuted = 'text-white/55';
export const opsTextSubtle = 'text-white/30';
export const opsTextSectionLabel =
  'text-xs font-semibold text-white/70 uppercase tracking-wider';

// ── Tab styling (matches OperationsDashboard tab list) ──────
export const opsTabActiveStyle = {
  background: 'linear-gradient(90deg, #f59e0b 0%, #f97316 100%)',
  color: '#fff',
  border: '1.5px solid #f59e0b',
  boxShadow: '0 0 8px 0 #f59e0b55',
};

export const opsTabInactiveStyle = {
  background: 'rgba(60, 30, 90, 0.22)',
  color: '#cfc6e6',
  border: '1.5px solid #2d2342',
  boxShadow: 'none',
};

export const opsTabListClass =
  'inline-flex w-max min-w-full h-auto p-1 gap-1 rounded-lg bg-[#1a1333] border border-[#3a295a]';

export const opsTabListStyle = {
  boxShadow: '0 2px 12px 0 #a259ff0a',
};

// ── Page container (apply to the immediate child of DashboardNavbar) ──
export const opsContainerClass =
  'container mx-auto px-6 sm:px-10 lg:px-16 xl:px-20 py-4 sm:py-8 max-w-full overflow-x-hidden';
