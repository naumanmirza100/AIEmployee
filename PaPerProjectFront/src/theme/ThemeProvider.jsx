import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

/**
 * Light / dark theme for the whole app.
 *
 * Dark unless the visitor has picked otherwise. Their pick is saved in this
 * browser and used on every later visit.
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

// Written only when the visitor picks a theme, so "nothing stored" really
// means "never chose" and gets the default.
const STORAGE_KEY = 'ppp-theme-choice';
// Earlier builds wrote the theme here on every visit, 'system' included,
// whether or not anyone chose it. Only 'light' and 'dark' there were real
// choices (the toggle offered nothing else), so those are still honoured.
const LEGACY_KEY = 'ppp-theme';
const DEFAULT_THEME = 'dark';
const ThemeContext = createContext(null);

function systemPrefersDark() {
  return typeof window !== 'undefined'
    && window.matchMedia
    && window.matchMedia('(prefers-color-scheme: dark)').matches;
}

function readStoredTheme() {
  try {
    const chosen = localStorage.getItem(STORAGE_KEY);
    if (chosen === 'light' || chosen === 'dark' || chosen === 'system') return chosen;
    const legacy = localStorage.getItem(LEGACY_KEY);
    if (legacy === 'light' || legacy === 'dark') return legacy;
  } catch (_) {
    // Private browsing, blocked storage — fall through to the default.
  }
  return DEFAULT_THEME;
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
  }, [theme]);

  // Only a real choice is saved. Saving on every load, as this used to, made
  // the default indistinguishable from a choice and pinned everyone to it.
  const setTheme = useCallback((next) => {
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch (_) {
      // Not fatal — the theme still applies for this visit.
    }
    setThemeState(next);
  }, []);

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
    setTheme,
    toggleTheme: () => setTheme(isDark ? 'light' : 'dark'),
  }), [theme, isDark, setTheme]);

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
