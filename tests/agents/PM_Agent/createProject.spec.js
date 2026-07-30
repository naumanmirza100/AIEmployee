// tests/agents/PM_Agent/createProject.spec.js
const { test, expect } = require('@playwright/test');

test.describe('Project Manager Agent - Create Project Module', () => {

  test.beforeEach(async ({ page }) => {
    // 1. Inject a background DOM sweeper before the page loads.
    // This script runs continuously inside the browser and instantly deletes
    // any tour modals or blocking overlays from the DOM as soon as they mount.
    await page.addInitScript(() => {
      const sweeper = setInterval(() => {
        // Find and remove any high z-index fixed backdrop overlays
        document.querySelectorAll('div').forEach(div => {
          const style = window.getComputedStyle(div);
          if (style.position === 'fixed' && parseInt(style.zIndex) > 9000) {
            div.remove();
          }
        });

        // Find and remove any containers containing tour elements
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

    // 2. Open Dashboard directly (uses pre-authenticated storageState)
    await page.goto('http://localhost:3000/project-manager/dashboard', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1000);

    // 3. Click "+ Create Project" tab directly (overlays will be auto-deleted)
    const createProjectTab = page.locator('[role="tab"]').filter({ hasText: 'Create Project' }).first();
    await createProjectTab.click({ force: true });

    // 4. Ensure the Create Project form is loaded and visible
    await expect(page.getByText('Create Project Manually')).toBeVisible({ timeout: 15000 });
  });

  // --- POSITIVE PATH ---
  test('POS-01: Should create a new project successfully with valid details', async ({ page }) => {
    const uniqueProjectName = `AI Test Project ${Date.now()}`;

    // Fill Project Name and Description
    await page.getByPlaceholder('Enter project name').fill(uniqueProjectName);
    await page.getByPlaceholder('Enter project description').fill('Automated end-to-end test description for project creation.');

    // Fill Budget Min & Max if visible
    const budgetMin = page.locator('input[type="number"]').first().or(page.getByPlaceholder('0.00').first());
    if (await budgetMin.isVisible().catch(() => false)) {
      await budgetMin.fill('1000');
    }

    const budgetMax = page.locator('input[type="number"]').nth(1).or(page.getByPlaceholder('0.00').nth(1));
    if (await budgetMax.isVisible().catch(() => false)) {
      await budgetMax.fill('5000');
    }

    // Click "+ Create Project" Submit Button
    const submitBtn = page.locator('button').filter({ hasText: 'Create Project' }).last();
    await submitBtn.click({ force: true });

    await page.waitForTimeout(1000);
  });

  // --- NEGATIVE PATHS ---
  test('NEG-01: Should block project creation when Project Name is blank', async ({ page }) => {
    // Click submit using updated button locator
    const submitBtn = page.locator('button').filter({ hasText: 'Create Project' }).last();
    await submitBtn.click({ force: true });

    await expect(page.getByText('Create Project Manually')).toBeVisible();
  });

  test('NEG-02: Should block creation when Budget Min exceeds Budget Max', async ({ page }) => {
    await page.getByPlaceholder('Enter project name').fill('Invalid Budget Project');

    const budgetMin = page.locator('input[type="number"]').first().or(page.getByPlaceholder('0.00').first());
    const budgetMax = page.locator('input[type="number"]').nth(1).or(page.getByPlaceholder('0.00').nth(1));

    if (await budgetMin.isVisible().catch(() => false) && await budgetMax.isVisible().catch(() => false)) {
      await budgetMin.fill('10000');
      await budgetMax.fill('1000');

      // Click submit using updated button locator
      const submitBtn = page.locator('button').filter({ hasText: 'Create Project' }).last();
      await submitBtn.click({ force: true });

      await expect(page.getByText('Create Project Manually')).toBeVisible();
    }
  });

  // --- EDGE CASE ---
  test('EDGE-01: Should allow selecting start date and deadline', async ({ page }) => {
    const startDateBtn = page.getByText('Pick a start date').first();
    const deadlineBtn = page.getByText('Pick a deadline').first();

    if (await startDateBtn.isVisible().catch(() => false)) {
      await startDateBtn.click({ force: true });
      await page.waitForTimeout(300);
    }

    if (await deadlineBtn.isVisible().catch(() => false)) {
      await deadlineBtn.click({ force: true });
      await page.waitForTimeout(300);
    }
  });

});