// tests/agents/Recruitment_Agent/Analytics.spec.js
const { test, expect } = require('@playwright/test');
const { setupDOMSweeper } = require('../../helper/auth.js'); // Keeping your current helper import

test.describe('Recruitment Agent - Analytics Overview', () => {

  test.beforeEach(async ({ page }) => {
    // 1. Setup DOM sweeper to neutralize onboarding tours/overlays
    await setupDOMSweeper(page);

    // 2. Navigate to the stable entry point of the agent workspace
    await page.goto('http://localhost:3000/recruitment/dashboard', { waitUntil: 'domcontentloaded' });

    // 3. Dismiss any active onboarding tour overlays
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

    // 4. Perform client-side navigation to the Analytics tab safely
    const analyticsTab = page.getByRole('tab', { name: 'Analytics', exact: true })
      .or(page.getByRole('button', { name: 'Analytics', exact: true }))
      .first();
    await expect(analyticsTab).toBeVisible({ timeout: 10000 });
    await analyticsTab.click({ force: true });
    await page.waitForTimeout(1000); // Allow time for client-side content to mount
  });

  // --- ANALYTICS SUMMARY KPI CARDS ---
  test('POS-01: Should display Analytics summary stat cards accurately', async ({ page }) => {
    await expect(page.getByText('Conversion Rate').first()).toBeVisible({ timeout: 15000 });
    await expect(page.getByText('Avg Role Fit Score').first()).toBeVisible({ timeout: 15000 });

    await expect(page.getByText('9.5%').first()).toBeVisible();
    await expect(page.getByText('0%').first()).toBeVisible();
  });

  // --- FILTER & CONFIGURATION CONTROLS ---
  test('POS-02: Should toggle timeframe periods and trigger job dropdown', async ({ page }) => {
    // Highly resilient timeframe selector matching any element containing exact text
    const days30Btn = page.locator('button, a, div, li').filter({ hasText: /^30 days$/ }).first();
    const days90Btn = page.locator('button, a, div, li').filter({ hasText: /^90 days$/ }).first();
    
    await expect(days30Btn).toBeVisible({ timeout: 15000 });
    await days30Btn.click({ force: true });
    await page.waitForTimeout(500);

    await expect(days90Btn).toBeVisible({ timeout: 10000 });
    await days90Btn.click({ force: true });
    await page.waitForTimeout(500);

    // Dynamic dropdown interaction avoiding selection strict-mode failures
    const jobDropdown = page.getByRole('combobox').or(page.locator('button:has-text("All Jobs")')).first();
    await jobDropdown.click({ force: true });
    await page.waitForTimeout(500);

    const dropdownItem = page.locator('[role="option"], [role="menuitem"], li, button').filter({ hasText: /Senior Platform|All Jobs/ }).first();
    await expect(dropdownItem).toBeVisible({ timeout: 5000 });
    await dropdownItem.click({ force: true });
  });

  // --- REPORT EXPORTS ---
  test('POS-03: Should trigger report exports successfully', async ({ page }) => {
    const exportCandidatesBtn = page.locator('button, a, div').filter({ hasText: /^Export Candidates$/ }).first();
    const exportInterviewsBtn = page.locator('button, a, div').filter({ hasText: /^Export Interviews$/ }).first();

    await expect(exportCandidatesBtn).toBeVisible({ timeout: 15000 });
    await expect(exportInterviewsBtn).toBeVisible({ timeout: 10000 });

    await exportCandidatesBtn.click({ force: true });
    await page.waitForTimeout(300);

    await exportInterviewsBtn.click({ force: true });
    await page.waitForTimeout(300);
  });

  // --- DATA GRAPH RENDER VERIFICATIONS ---
  test('POS-04: Should display Recruitment Funnel dropdown analytics', async ({ page }) => {
    await expect(page.getByText('Recruitment Funnel').first()).toBeVisible({ timeout: 15000 });
    await expect(page.getByText('Candidate drop-off at each stage').first()).toBeVisible();

    await expect(page.getByText('Applied', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('Screened', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('Shortlisted', { exact: true }).first()).toBeVisible();
  });

  test('POS-05: Should load Decision Distribution and Time Series trends', async ({ page }) => {
    await expect(page.getByText('CVs by Decision').first()).toBeVisible({ timeout: 15000 });
    await expect(page.getByText('Distribution of candidate decisions').first()).toBeVisible();

    await expect(page.getByText('CVs Over Time').first()).toBeVisible({ timeout: 15000 });
    await expect(page.getByText('Daily cv processing trend').first()).toBeVisible();
  });

  test('POS-06: Should render Interview Status and Scheduling timelines', async ({ page }) => {
    await expect(page.getByText('Interviews by Status').first()).toBeVisible({ timeout: 15000 });

    await expect(page.getByText('Interviews Over Time').first()).toBeVisible({ timeout: 15000 });
    await expect(page.getByText('Daily interview scheduling trend').first()).toBeVisible();
  });

});