// tests/agents/projectManager/overviewAndNavigation.spec.js
const { test, expect } = require('@playwright/test');
const { loginUser } = require('../../helper/auth.js'); // Import reusable login helper

test.describe('Project Manager Agent - Navigation, Tour & Overview', () => {

  test.beforeEach(async ({ page }) => {
    // 1. Log in using reusable helper
    await loginUser(page, { email: 'af602773@gmail.com', password: 'amina123' });

    // 2. Navigate to Project Manager Agent Dashboard
    await page.goto('http://localhost:3000/project-manager/dashboard', { waitUntil: 'domcontentloaded' });

    // 3. Robust Cleanup: Loop-dismiss any active onboarding tour overlays
    for (let i = 0; i < 3; i++) {
      const skipBtn = page.getByRole('button', { name: /Skip tutorial|Finish/i }).first();
      if (await skipBtn.isVisible({ timeout: 1500 }).catch(() => false)) {
        await skipBtn.click({ force: true }).catch(() => {});
        await page.waitForTimeout(300);
      } else {
        break;
      }
    }
    // Press Escape to dismiss any remaining backdrop modals
    await page.keyboard.press('Escape').catch(() => {});
  });

  // --- OVERVIEW DASHBOARD METRICS ---
  test('POS-01: Should display Overview summary metric cards correctly', async ({ page }) => {
    // Generous timeout to allow React metrics to finish loading
    await expect(page.getByText('Total Projects')).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('Active Projects')).toBeVisible();
    
    // Exact match to avoid strict mode violation with "In planning phase"
    await expect(page.getByText('Planning', { exact: true })).toBeVisible();
    
    await expect(page.getByText('Completed')).toBeVisible();
  });

  test('POS-02: Should display feature cards on Overview tab', async ({ page }) => {
    await expect(page.getByRole('button', { name: /Project Pilot/i }).first()).toBeVisible({ timeout: 10000 });
    await expect(page.getByRole('button', { name: /Task Prioritization/i }).first()).toBeVisible();
    await expect(page.getByRole('button', { name: /Knowledge Q&A/i }).first()).toBeVisible();
    await expect(page.getByRole('button', { name: /Timeline & Gantt/i }).first()).toBeVisible();
    await expect(page.getByRole('button', { name: /AI Tools/i }).first()).toBeVisible();
  });

  // --- SUB-TAB NAVIGATION ---
  test('POS-03: Should navigate through all Project Manager sub-tabs', async ({ page }) => {
    // Role-based tab locators with force click to prevent backdrop block
    await page.getByRole('tab', { name: /Create Project/i }).click({ force: true });
    await page.waitForTimeout(300);

    await page.getByRole('tab', { name: /Create Task/i }).click({ force: true });
    await page.waitForTimeout(300);

    await page.getByRole('tab', { name: /Project Pilot/i }).click({ force: true });
    await page.waitForTimeout(300);

    await page.getByRole('tab', { name: /Task Prioritization/i }).click({ force: true });
    await page.waitForTimeout(300);

    await page.getByRole('tab', { name: /Knowledge Q&A/i }).click({ force: true });
    await page.waitForTimeout(300);

    await page.getByRole('tab', { name: /Timeline & Gantt/i }).click({ force: true });
    await page.waitForTimeout(300);

    await page.getByRole('tab', { name: /Meeting Scheduler/i }).click({ force: true });
    await page.waitForTimeout(300);

    await page.getByRole('tab', { name: /AI Tools/i }).click({ force: true });
    await page.waitForTimeout(300);

    // Return to Overview
    await page.getByRole('tab', { name: /Overview/i }).click({ force: true });
    await expect(page.getByText('Total Projects')).toBeVisible({ timeout: 10000 });
  });

  // --- TOUR & HINTS FEATURE TESTS ---
  test('POS-04: Should toggle Hints button on header', async ({ page }) => {
    const hintsBtn = page.getByRole('button', { name: /Hints/i }).first();
    
    if (await hintsBtn.isVisible({ timeout: 5000 })) {
      await hintsBtn.click({ force: true }); // Toggle Off
      await page.waitForTimeout(300);
      await hintsBtn.click({ force: true }); // Toggle On
    }
  });

  test('POS-05: Should launch tour via "Take the Tour" button and step through steps', async ({ page }) => {
    const takeTourBtn = page.getByRole('button', { name: 'Take the Tour' });
    await takeTourBtn.click({ force: true });

    // Verify Tour Modal opens
    await expect(page.getByText(/Welcome to Project Pilot/i)).toBeVisible({ timeout: 10000 });

    // Click Next button
    const nextBtn = page.getByRole('button', { name: 'Next' }).first();
    await nextBtn.click({ force: true });

    // Dismiss tour
    await page.getByRole('button', { name: /Skip tutorial|Finish/i }).first().click({ force: true });
  });

  test('POS-06: Should trigger "Tour this tab" button', async ({ page }) => {
    const tourTabBtn = page.getByRole('button', { name: 'Tour this tab' });
    if (await tourTabBtn.isVisible({ timeout: 5000 })) {
      await tourTabBtn.click({ force: true });
      await page.waitForTimeout(500);
    }
  });

});