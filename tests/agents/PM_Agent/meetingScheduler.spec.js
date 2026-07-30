// tests/agents/PM_Agent/meetingScheduler.spec.js
const { test, expect } = require('@playwright/test');
const { setupDOMSweeper } = require('../../helper/auth.js');

test.describe('Project Manager Agent - Meeting Scheduler Module', () => {

  test.beforeEach(async ({ page }) => {
    await setupDOMSweeper(page);

    await page.goto('http://localhost:3000/project-manager/dashboard', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1000);

    const schedulerTab = page.locator('[role="tab"]').filter({ hasText: 'Meeting Scheduler' }).first();
    await schedulerTab.click({ force: true });

    await expect(page.getByText('Meeting Scheduler')).toBeVisible({ timeout: 15000 });
  });

  // --- POSITIVE PATHS ---
  test('POS-01: Should send a scheduling prompt to the agent', async ({ page }) => {
    const chatInput = page.getByPlaceholder(/Schedule a meeting with Sarah/i);
    await expect(chatInput).toBeVisible();

    await chatInput.fill('Schedule a meeting with Sarah and John tomorrow at 2 PM to discuss the project launch.');

    const sendBtn = page.locator('button').filter({ has: page.locator('svg') }).last();
    await sendBtn.click({ force: true });

    await page.waitForTimeout(1000);
  });

});