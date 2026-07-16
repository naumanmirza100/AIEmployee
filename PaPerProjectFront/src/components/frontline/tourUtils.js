// Small shared utilities for the tour-hint system used by Frontline / HR / PM.
// Keeps per-dashboard files thin.

import { useState, useEffect } from 'react';
import { hasSeenTutorial } from './FrontlineTutorial';

// --- Mobile viewport detection ------------------------------------------
// Matches Tailwind's `sm` breakpoint. Everything below 640px is treated
// as "mobile" for the tour + chat bottom-sheet modes.

const MOBILE_QUERY = '(max-width: 640px)';

export function useIsMobile() {
  const [isMobile, setIsMobile] = useState(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return false;
    return window.matchMedia(MOBILE_QUERY).matches;
  });
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    const mq = window.matchMedia(MOBILE_QUERY);
    const onChange = (e) => setIsMobile(e.matches);
    // Older browsers used addListener; keep both for safety.
    if (mq.addEventListener) mq.addEventListener('change', onChange);
    else mq.addListener(onChange);
    return () => {
      if (mq.removeEventListener) mq.removeEventListener('change', onChange);
      else mq.removeListener(onChange);
    };
  }, []);
  return isMobile;
}

// --- First-login "Take the Tour" spotlight ---------------------------------
// Fires a one-time pulse animation on the header button so users notice it
// exists after they close the auto-launched tour. Keyed per dashboard so
// each dashboard shows its own spotlight independently.

export function shouldSpotlightTour(spotlightKey) {
  try { return localStorage.getItem(`${spotlightKey}__spotlight_seen`) !== '1'; }
  catch (_) { return false; }
}

export function markSpotlightSeen(spotlightKey) {
  try { localStorage.setItem(`${spotlightKey}__spotlight_seen`, '1'); }
  catch (_) { /* ignore */ }
}

// --- Tour-available badge ---
// A tab shows a small unread dot until the user has seen its per-tab tour.

export function tourAvailable(storageKey) {
  return !hasSeenTutorial(storageKey);
}

// --- Contextual hover-to-launch ---
// A tab whose tour hasn't been seen offers to launch itself if the user
// hovers on it for N ms without clicking. Returns onMouseEnter/onMouseLeave
// handlers you can spread on the tab trigger.

export function makeHoverLaunchHandlers({ tourStorageKey, onLaunch, delayMs = 3000 }) {
  let timer = null;
  return {
    onMouseEnter: () => {
      if (!tourStorageKey || !onLaunch) return;
      if (!tourAvailable(tourStorageKey)) return;
      clearTimeout(timer);
      timer = setTimeout(() => onLaunch(), delayMs);
    },
    onMouseLeave: () => { clearTimeout(timer); },
    // Cancel the timer if the user actually clicks — the click is the
    // real intent, no need to nag them with the tour after.
    onClick: () => { clearTimeout(timer); },
  };
}
