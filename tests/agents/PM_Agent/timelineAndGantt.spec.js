// tests/agents/PM_Agent/timelineAndGantt.spec.js
const { test, expect } = require('@playwright/test');
const { setupDOMSweeper } = require('../../helper/auth.js');

test.describe('Project Manager Agent - Timeline & Gantt Module', () => {

  test.beforeEach(async ({ page }) => {
    await setupDOMSweeper(page);

    await page.goto('http://localhost:3000/project-manager/dashboard', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1000);

    const timelineTab = page.locator('[role="tab"]').filter({ hasText: 'Timeline & Gantt' }).first();
    await timelineTab.click({ force: true });

    await expect(page.getByText('Timeline & Gantt Agent')).toBeVisible({ timeout: 15000 });
  });

 // --- POSITIVE PATH ---
  test('POS-01: Should select a project and trigger action buttons', async ({ page }) => {
    // 1. Locate and click the combobox normally (allows React state to bind)
    const projectDropdown = page.getByRole('combobox');
    await expect(projectDropdown).toBeVisible({ timeout: 10000 });
    await projectDropdown.click(); // Standard click (No force: true)
    await page.waitForTimeout(1000); // Give the popover time to render

    // 2. Wait for the options dropdown to load using the flat selector
    const firstOption = page.locator('[role="option"], [role="menuitem"], [role="listbox"] div, li').first();
    await expect(firstOption).toBeVisible({ timeout: 8000 });
    await firstOption.click(); // Standard click
    await page.waitForTimeout(500);

    // 3. Trigger action buttons (using exact matching to bypass "!" hint icons)
    const createTimelineBtn = page.getByRole('button', { name: 'Create Timeline', exact: true });
    if (await createTimelineBtn.isVisible()) {
      await createTimelineBtn.click();
    }
    await page.waitForTimeout(300);

    const ganttBtn = page.getByRole('button', { name: 'Generate Gantt Chart', exact: true });
    if (await ganttBtn.isVisible()) {
      await ganttBtn.click();
    }
    await page.waitForTimeout(300);

    const deadlinesBtn = page.getByRole('button', { name: 'Check Deadlines', exact: true });
    if (await deadlinesBtn.isVisible()) {
      await deadlinesBtn.click();
    }
    await page.waitForTimeout(300);
  });
});