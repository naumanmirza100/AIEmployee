# Theming: light and dark

The app supports **light**, **dark** and **system** (follow the OS). Tailwind is
configured with `darkMode: ["class"]`, so everything hangs off a single `dark`
class on `<html>`.

- `src/theme/ThemeProvider.jsx` owns the choice, persists it to `localStorage`
  under `ppp-theme`, and keeps following the OS while the choice is `system`.
- The inline script in `index.html` applies the class **before first paint**, so
  the page never flashes the wrong theme. If you change the storage key, change
  it in both places.
- `src/components/common/ThemeToggle.jsx` is the switcher. `<ThemeToggle />` is
  a single light/dark button; `<ThemeToggle variant="menu" />` offers all three
  options for a settings screen.

## Writing themed components

Use the semantic tokens, never a literal colour:

| Instead of | Use |
|---|---|
| `bg-[var(--panel-1)]`, `bg-black` | `bg-background`, `bg-card`, `bg-popover` |
| `text-white` | `text-foreground` |
| `text-white/50`, `text-gray-400` | `text-muted-foreground` |
| `border-white/10`, `border-gray-700` | `border-border` |
| `bg-white/5`, `hover:bg-white/10` | `bg-muted`, `hover:bg-accent` |

**`white` and `black` are theme tokens now, not literal colours.** Tailwind's
`white` is remapped in `tailwind.config.js` to `hsl(var(--surface-invert))`, so
the ~4,000 existing `text-white`, `bg-white/5` and `border-white/10` classes
resolve to near-black in light mode and real white in dark mode without any
call site changing. `black` is remapped the same way via `--surface-base`.

That means **`text-white` no longer guarantees white.** When a colour must stay
fixed regardless of theme, use the escape hatches:

| Use | When |
|---|---|
| `text-pure-white` | Text on a solid coloured or gradient button/badge |
| `bg-pure-black` | Modal scrims and full-viewport overlays |

Inline styles can't take a class, so they read CSS variables instead:

| Variable | Role |
|---|---|
| `var(--app-page-bg)` | Full-page background behind an agent dashboard |
| `var(--app-hero-bg)` | Banner strip at the top of a dashboard |
| `var(--panel-1..4)` | Panel / card fills |
| `var(--line-1..3)` | Borders and dividers |
| `var(--text-soft)` | Muted body text |
| `var(--brand-600)` | Brand colour — #427CF5 light, #7C3AED dark |
| `var(--brand-accent)` | Lighter half of the brand gradients |
| `var(--sfc-xxxxxx)` | Auto-generated per-panel surfaces, named after their original dark hex |

Every one of these is defined twice in `index.css`: once under `:root` (light)
and once under `.dark`. The `.dark` values are the original hardcoded colours,
so dark mode is unchanged.

## What is converted so far

Done: the app shell (`DashboardNavbar`, `AgentSidebar`, `AgentBreadcrumb`,
`Logo`), `components/common/`, `components/ui/`, and all the agent dashboards —
PM, HR, Frontline, Marketing, Recruitment, Operations, Exec-Meeting, AI-SDR,
Reply Draft and Admin. No hardcoded dark surface colours remain in `src/`.

Deliberately left dark: the public job-application page
(`pages/JobApplicationPage.jsx`), which is a standalone candidate-facing page
outside the app shell and has no theme toggle.

Semantic colours (amber `#f59e0b`, emerald `#10b981`, red `#ef4444`, the greys
`#6b7280`/`#9ca3af`) are intentionally untouched — they read on both themes.
