import React from 'react';
import { Monitor, Moon, Sun } from 'lucide-react';

import { useTheme } from '@/theme/ThemeProvider';

/**
 * Light / dark switcher.
 *
 * Two shapes from one component:
 *   <ThemeToggle />              — a single button that flips light ⇄ dark.
 *   <ThemeToggle variant="menu" />— three options including "System", for
 *                                   settings screens where the choice should
 *                                   be explicit.
 */
export function ThemeToggle({ variant = 'button', className = '' }) {
  const { theme, isDark, setTheme, toggleTheme } = useTheme();

  if (variant === 'menu') {
    const options = [
      { value: 'light', label: 'Light', Icon: Sun },
      { value: 'dark', label: 'Dark', Icon: Moon },
      { value: 'system', label: 'System', Icon: Monitor },
    ];
    return (
      <div
        role="radiogroup"
        aria-label="Colour theme"
        className={`inline-flex items-center gap-1 rounded-lg border border-border bg-muted/40 p-1 ${className}`}
      >
        {options.map(({ value, label, Icon }) => (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={theme === value}
            onClick={() => setTheme(value)}
            className={`flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors
              ${theme === value
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground'}`}
          >
            <Icon className="h-3.5 w-3.5" />
            {label}
          </button>
        ))}
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={toggleTheme}
      // The label says what the click does, not what is currently showing —
      // that is what a screen-reader user needs to hear.
      aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      className={`h-8 w-8 shrink-0 flex items-center justify-center rounded-md
        text-muted-foreground hover:text-foreground hover:bg-accent transition-colors ${className}`}
    >
      {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </button>
  );
}

export default ThemeToggle;
