import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';

/**
 * Light / dark theme for the whole app.
 *
 * Three states, not two: 'light', 'dark' and 'system'. 'system' follows the
 * operating system and keeps following it — someone whose laptop switches to
 * dark at sunset gets the same here, without having to come back and change a
 * setting.
 *
 * The class goes on <html> because Tailwind is configured with
 * `darkMode: ["class"]`. The same class is applied by the inline script in
 * index.html before first paint, so the page never flashes the wrong theme;
 * this provider takes over from there and keeps them in step.
 */

const STORAGE_KEY = 'ppp-theme';
const ThemeContext = createContext(null);

function systemPrefersDark() {
  return typeof window !== 'undefined'
    && window.matchMedia
    && window.matchMedia('(prefers-color-scheme: dark)').matches;
}

function readStoredTheme() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === 'light' || stored === 'dark' || stored === 'system') return stored;
  } catch (_) {
    // Private browsing, blocked storage — fall through to the default.
  }
  return 'system';
}

function applyTheme(theme) {
  const root = document.documentElement;
  const dark = theme === 'dark' || (theme === 'system' && systemPrefersDark());
  root.classList.toggle('dark', dark);
  // Keeps native controls (scrollbars, date pickers, autofill) in step.
  root.style.colorScheme = dark ? 'dark' : 'light';
  return dark;
}

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(readStoredTheme);
  const [isDark, setIsDark] = useState(() => (
    theme === 'dark' || (theme === 'system' && systemPrefersDark())
  ));

  useEffect(() => {
    setIsDark(applyTheme(theme));
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch (_) {
      // Not fatal — the theme still applies for this page load.
    }
  }, [theme]);

  // Follow the OS while the choice is 'system'.
  useEffect(() => {
    if (theme !== 'system' || !window.matchMedia) return undefined;
    const query = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = () => setIsDark(applyTheme('system'));
    query.addEventListener('change', onChange);
    return () => query.removeEventListener('change', onChange);
  }, [theme]);

  const value = useMemo(() => ({
    theme,                                   // 'light' | 'dark' | 'system'
    isDark,                                  // what is actually showing
    setTheme: setThemeState,
    toggleTheme: () => setThemeState(isDark ? 'light' : 'dark'),
  }), [theme, isDark]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error('useTheme must be used inside <ThemeProvider>');
  }
  return ctx;
}

export default ThemeProvider;
