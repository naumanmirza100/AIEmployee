import React from 'react';

// Render an HTML email body. Single path: sandboxed iframe with the
// `#er` wrapper + flattenBackgrounds() machinery below, which already
// converts each email to dark-theme on render. Earlier we had a second
// "plain reply" path that rendered HTML inline in the dark theme —
// looked good for handwritten replies but stripped <style> blocks from
// transactional/GPT marketing emails, which dropped their footers and
// made superficially-similar emails render differently. Going through
// one path keeps the rendering consistent across every email type.
export const HtmlBody = ({ html }) => {
  const ref = React.useRef(null);

  // Resize aggressively: initial pass + ResizeObserver on the body +
  // <img> load listeners. Without the observer we'd ship the iframe at
  // its initial measured height and any late-loading image (almost
  // every transactional mail) would push content past it, leaving an
  // ugly internal scrollbar. We instead grow the iframe to match
  // content so the *outer* panel handles the scrolling.
  React.useEffect(() => {
    const iframe = ref.current;
    if (!iframe) return undefined;
    // Holds the MutationObserver so flattenBackgrounds() can pause it while
    // it mutates styles — otherwise its own edits re-trigger the observer,
    // which re-runs flatten, forever (a CPU-pinning loop that made the tab
    // "unresponsive"). Declared here so both closures can reach it.
    let mo;
    // Guard against resize thrashing: only touch iframe.style.height when
    // the new height actually differs by more than a pixel. ResizeObserver
    // fires on our own height writes, so an unconditional write looped.
    let lastHeight = 0;
    const resize = () => {
      try {
        const doc = iframe.contentDocument;
        if (!doc) return;
        // Prefer body's actual content height. documentElement.scrollHeight
        // includes the iframe's viewport minimum (~150-180px), so an empty
        // or short email would otherwise size to that minimum and leave a
        // big empty box. Fall back to documentElement only when body
        // hasn't rendered yet (initial load race).
        const bodyH = Math.max(doc.body?.scrollHeight || 0, doc.body?.offsetHeight || 0);
        const docH = Math.max(doc.documentElement?.scrollHeight || 0, doc.documentElement?.offsetHeight || 0);
        const next = bodyH > 0 ? bodyH : docH;
        if (next > 0 && Math.abs(next - lastHeight) > 1) {
          lastHeight = next;
          iframe.style.height = `${next + 8}px`;
        }
      } catch {
        // Cross-origin sandbox can throw — just leave whatever default height we set.
      }
    };
    // Force-strip every element's background by walking the DOM. This
    // is the only way to beat inline `style="background:#000 !important"`
    // (which CSS overrides, even with !important + ID specificity,
    // can't reach because inline !important sits at the top of the
    // cascade for the author origin). We also yank legacy `bgcolor` /
    // `background` HTML attributes and remove email-internal <style>
    // tags so they can't repaint after we strip.
    const flattenBackgrounds = () => {
      try {
        const doc = iframe.contentDocument;
        if (!doc) return;
        const root = doc.getElementById('er') || doc.body;
        if (!root) return;
        // Pause the MutationObserver while WE mutate — otherwise the
        // style/attribute writes below are themselves mutations that wake
        // the observer, which calls flattenBackgrounds again, looping
        // forever and freezing the tab. Reconnect in the finally block.
        if (mo) mo.disconnect();
        // Drop any <style> inside the email body — its rules would
        // otherwise repaint backgrounds (especially on hover/media
        // queries we can't predict). Our wrapper <style> in <head>
        // stays untouched.
        root.querySelectorAll('style').forEach((s) => s.remove());
        const all = [root, ...root.querySelectorAll('*')];
        all.forEach((el) => {
          el.style.setProperty('background-color', 'transparent', 'important');
          el.style.setProperty('background-image', 'none', 'important');
          el.style.setProperty('background', 'transparent', 'important');
          if (el.hasAttribute && el.hasAttribute('bgcolor')) el.removeAttribute('bgcolor');
          if (el.hasAttribute && el.hasAttribute('background')) el.removeAttribute('background');
        });
      } catch {
        // sandboxed cross-origin or torn-down doc: nothing we can do
      } finally {
        // Re-arm the observer for genuinely new nodes (lazy blocks, pixels)
        // now that our own edits are done and won't be seen as changes.
        try {
          const doc = iframe.contentDocument;
          if (mo && doc && doc.body) {
            mo.observe(doc.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['style', 'bgcolor', 'background'] });
          }
        } catch {
          // ignore — observer just won't re-arm
        }
      }
    };
    flattenBackgrounds();
    resize();
    let ro;
    let imgs = [];
    try {
      const doc = iframe.contentDocument;
      if (doc && typeof ResizeObserver !== 'undefined') {
        ro = new ResizeObserver(resize);
        if (doc.documentElement) ro.observe(doc.documentElement);
        if (doc.body) ro.observe(doc.body);
      }
      // Watch for late-injected nodes (web pixels, lazy-loaded blocks)
      // and re-flatten so they can't sneak a black bg back in.
      if (doc && typeof MutationObserver !== 'undefined' && doc.body) {
        mo = new MutationObserver(() => { flattenBackgrounds(); resize(); });
        mo.observe(doc.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['style', 'bgcolor', 'background'] });
      }
      if (doc) {
        imgs = Array.from(doc.images || []);
        imgs.forEach((img) => {
          if (!img.complete) img.addEventListener('load', resize, { once: true });
        });
      }
    } catch {
      // sandboxed cross-origin: rely on the timed retries below
    }
    // Timed retries for the cases the observer can't see (e.g. fonts
    // settling, web-pixel beacons that don't fire load events).
    const t1 = setTimeout(() => { flattenBackgrounds(); resize(); }, 150);
    const t2 = setTimeout(() => { flattenBackgrounds(); resize(); }, 600);
    const t3 = setTimeout(() => { flattenBackgrounds(); resize(); }, 1500);
    return () => {
      clearTimeout(t1); clearTimeout(t2); clearTimeout(t3);
      if (ro) ro.disconnect();
      if (mo) mo.disconnect();
      imgs.forEach((img) => img.removeEventListener('load', resize));
    };
  }, [html]);

  // Force dark mode on every email by aggressively overriding their
  // styles, and keep the iframe fully transparent so the parent
  // panel's bg-black/40 over the page gradient shows through — that's
  // what makes the email viewer feel like part of the dashboard
  // instead of a separate "darker black" island.
  // The email body is wrapped in <div id="er"> so our overrides can
  // use `#er, #er *` and reach specificity (1,0,1). Without the ID
  // any email-internal `<style>` rule with a class or element
  // selector (e.g. `body{background:#000}` or `.wrapper{...}`) would
  // beat our universal selector — !important doesn't override
  // specificity, only same-specificity ties.
  const wrapped = `<!doctype html><html><head><meta charset="utf-8"><base target="_blank"><style>
    html,body{margin:0;padding:0;background:transparent !important;color:#e4e4e7 !important;font-family:-apple-system,Segoe UI,Roboto,sans-serif;font-size:14px;line-height:1.5;color-scheme:dark;scrollbar-width:none !important;-ms-overflow-style:none !important;}
    html::-webkit-scrollbar,body::-webkit-scrollbar,*::-webkit-scrollbar{display:none !important;width:0 !important;height:0 !important;}
    body{padding:0;}
    #er,#er *,#er *::before,#er *::after{background-color:transparent !important;background-image:none !important;color:#e4e4e7 !important;box-shadow:none !important;}
    #er [bgcolor]{background-color:transparent !important;}
    #er a,#er a *{color:#7dd3fc !important;text-decoration:underline;}
    #er img{max-width:100%;height:auto;background-color:transparent !important;}
    #er hr{border-color:rgba(255,255,255,0.15) !important;}
    #er blockquote{border-left:2px solid rgba(255,255,255,0.2) !important;padding-left:10px;color:#a1a1aa !important;}
  </style></head><body><div id="er">${html || ''}</div></body></html>`;

  // No wrapper chrome — render the iframe directly so the email reads
  // as part of the dashboard, not a "document" sitting on a tray.
  return (
    <iframe
      ref={ref}
      title="Email body"
      sandbox="allow-popups allow-popups-to-escape-sandbox allow-same-origin"
      srcDoc={wrapped}
      style={{ width: '100%', minHeight: '10px', border: 0, background: 'transparent', display: 'block', colorScheme: 'dark' }}
      onLoad={() => {
        const iframe = ref.current;
        if (!iframe) return;
        try {
          const doc = iframe.contentDocument;
          if (doc) {
            // Same body-first sizing as the resize() effect — picking
            // documentElement here gave empty mail a 150-200px viewport
            // minimum and a big empty box.
            const bodyH = doc.body?.scrollHeight || 0;
            const docH = doc.documentElement?.scrollHeight || 0;
            const h = bodyH > 0 ? bodyH : docH;
            if (h > 0) iframe.style.height = `${h + 8}px`;
          }
        } catch { }
      }}
    />
  );
};
