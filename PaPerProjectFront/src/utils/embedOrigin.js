// The embed pages (/embed/chat, /embed/form) run in a frame on a customer's website, but their requests go out
// from this site, so the server only ever saw this site's address and could not check it against the
// customer's list of allowed websites. These tell it the address of the page the frame sits on, as the browser
// reports it to the frame: `ancestorOrigins`, or the referrer where that is missing (Firefox).

/** The origin of the page this frame is in; '' when not in a frame, 'unknown' when the browser will not say. */
export const parentOrigin = () => {
  if (typeof window === 'undefined' || window.parent === window) return '';
  try {
    const list = window.location.ancestorOrigins;
    if (list && list.length) return list[0];
  } catch (e) { /* not available */ }
  try {
    if (document.referrer) return new URL(document.referrer).origin;
  } catch (e) { /* not a URL */ }
  return 'unknown';
};

/** `url` with `parent_origin` added, when this page is in a frame. */
export const withParentOrigin = (url) => {
  const origin = parentOrigin();
  if (!origin) return url;
  return `${url}${url.includes('?') ? '&' : '?'}parent_origin=${encodeURIComponent(origin)}`;
};
