/**
 * Whether a chat page's history panel starts open.
 *
 * The panels are 16 to 18rem wide. On a phone that left the chat 60 to 75px, so its question box was squeezed and
 * stuck out of the page (found 4 Nov 2026). Below 768px the panel starts closed; its button still opens it.
 *
 * Use as `useState(sidePanelStartsOpen)`.
 */
export const sidePanelStartsOpen = () =>
  typeof window === 'undefined' || !window.matchMedia || window.matchMedia('(min-width: 768px)').matches;
