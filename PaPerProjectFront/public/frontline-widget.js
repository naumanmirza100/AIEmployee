/**
 * Frontline Chat Widget - embeddable on any site
 * Usage: <script src="https://YOUR_APP_ORIGIN/frontline-widget.js" data-key="YOUR_WIDGET_KEY" data-base="https://YOUR_APP_ORIGIN"></script>
 * Optional: data-base defaults to script's origin
 */
(function () {
  var script = document.currentScript;
  var key = (script && script.getAttribute('data-key')) || '';
  var base = (script && script.getAttribute('data-base')) || (script && script.src && script.src.replace(/\/[^/]*$/, '')) || '';

  if (!key) {
    console.warn('Frontline widget: data-key is required');
    return;
  }

  var iframeSrc = base + '/embed/chat?key=' + encodeURIComponent(key);
  var open = false;
  var container = null;
  var iframe = null;
  var button = null;

  function toggle() {
    open = !open;
    if (container) container.style.display = open ? 'block' : 'none';
    if (iframe) iframe.src = open ? iframeSrc : '';
  }

  function create() {
    container = document.createElement('div');
    container.id = 'frontline-widget-container';
    container.style.cssText = 'display:none;position:fixed;bottom:80px;right:20px;width:380px;max-width:calc(100vw - 40px);height:520px;max-height:80vh;z-index:2147483647;box-shadow:0 4px 24px rgba(0,0,0,0.15);border-radius:12px;overflow:hidden;background:#fff;';

    iframe = document.createElement('iframe');
    iframe.src = iframeSrc;
    iframe.style.cssText = 'width:100%;height:100%;border:0;';
    container.appendChild(iframe);

    button = document.createElement('button');
    button.setAttribute('type', 'button');
    button.setAttribute('aria-label', 'Open chat');
    button.style.cssText = 'position:fixed;bottom:20px;right:20px;width:56px;height:56px;border-radius:50%;border:none;background:#0f172a;color:#fff;cursor:pointer;z-index:2147483646;box-shadow:0 4px 12px rgba(0,0,0,0.2);display:flex;align-items:center;justify-content:center;transition:transform 0.2s;';
    button.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>';
    button.onmouseover = function () { this.style.transform = 'scale(1.05)'; };
    button.onmouseout = function () { this.style.transform = 'scale(1)'; };
    button.onclick = toggle;

    document.body.appendChild(container);
    document.body.appendChild(button);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', create);
  } else {
    create();
  }
})();
