// tests/helpers/tour.js

/**
 * Injects a background DOM sweeper inside the browser context to automatically
 * detect and delete any tour modals, backdrops, and onboarding overlays as they mount.
 * @param {import('@playwright/test').Page} page - Playwright page object
 */
async function setupDOMSweeper(page) {
  await page.addInitScript(() => {
    const sweeper = setInterval(() => {
      // 1. Find and remove any high z-index fixed backdrop overlays
      document.querySelectorAll('div').forEach(div => {
        const style = window.getComputedStyle(div);
        if (style.position === 'fixed' && parseInt(style.zIndex) > 9000) {
          div.remove();
        }
      });

      // 2. Find and remove any containers containing tour/tutorial elements
      document.querySelectorAll('div, section, dialog').forEach(el => {
        const text = el.textContent || '';
        if (
          text.includes('Skip tutorial') || 
          text.includes('Welcome to Project Pilot') || 
          text.includes('Overview tab') ||
          text.includes('Skip this tour')
        ) {
          el.remove();
        }
      });
    }, 100);

    // Stop sweeper after 15 seconds to conserve browser resources
    setTimeout(() => clearInterval(sweeper), 15000);
  });
}

module.exports = { setupDOMSweeper };