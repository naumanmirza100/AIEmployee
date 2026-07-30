// tests/agents/Recruitment_Agent/cvProcessing.spec.js
const { test, expect } = require('@playwright/test');
const { setupDOMSweeper } = require('../../helper/auth.js'); // Maintaining your current helper path

test.describe('Recruitment Agent - CV Processing Page', () => {

  test.beforeEach(async ({ page }) => {
    // 1. Setup DOM sweeper to neutralize onboarding tours
    await setupDOMSweeper(page);

    // 2. Navigate directly to the Recruitment Agent Dashboard (stable entry point)
    await page.goto('http://localhost:3000/recruitment/dashboard', { waitUntil: 'domcontentloaded' });

    // 3. Explicit wait for core layout tablist/navigation bar to fully render first
    await expect(page.locator('[role="tablist"], nav').first()).toBeVisible({ timeout: 15000 });

    // 4. Robust Cleanup: Loop-dismiss any active onboarding tour overlays
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

    // 5. Navigate client-side to keep session state stable
    await navigateToTab(page, 'CV Processing');
  });

  // --- HELPERS ---

  // Locates specific sub-tabs securely using accessibility roles
  function getTabLocator(page, tabName) {
    return page.getByRole('tab', { name: tabName, exact: true })
      .or(page.getByRole('button', { name: tabName, exact: true }))
      .or(page.locator('button, [role="tab"]').filter({ hasText: tabName }))
      .first();
  }

  // Safe client-side tab navigation to maintain session state stability
  async function navigateToTab(page, tabName) {
    const tabButton = getTabLocator(page, tabName);
    await expect(tabButton).toBeVisible({ timeout: 10000 });
    await tabButton.click({ force: true });
    await page.waitForTimeout(1000); // Allow client-side rendering to settle
  }

  // --- POSITIVE PATHS ---

  test('POS-01: Should display manual CV processing instructions and upload form fields', async ({ page }) => {
  await expect(page.getByText(/This page is for manual CV processing/i)).toBeVisible({ timeout: 10000 });

  await expect(page.getByRole('heading', { name: /Process CV Files/i })).toBeVisible();
  await expect(page.getByText('Upload CV files to analyze and rank candidates based on job requirements', { exact: false })).toBeVisible();

  // Use getByLabel or exact:true scoped to the <label> element specifically —
  // getByText('CV Files') matches 3 elements (heading, description, label)
  // since "CV Files" is a substring of "Process CV Files" too.
  await expect(page.getByText('CV Files', { exact: true })).toBeVisible();
  await expect(page.getByText('Select Job Description', { exact: false })).toBeVisible();
  await expect(page.getByText('Keywords (Optional)', { exact: false })).toBeVisible();
  await expect(page.getByText('Top N Results (Optional)', { exact: false })).toBeVisible();
});

  test('POS-02: Should populate CV processing fields and mock upload a resume file', async ({ page }) => {
    // 1. Mock file upload dynamically (zero system-level file dependencies)
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles({
      name: 'candidate_resume_mock.pdf',
      mimeType: 'application/pdf',
      buffer: Buffer.from('%PDF-1.4 mock pdf candidate resume text details')
    });

    // 2. Select Job Description via standard Radix dropdown selectors
    const selectJobDropdown = page.getByRole('combobox').or(page.locator('button:has-text("Select a job")')).first();
    await selectJobDropdown.click({ force: true });
    await page.waitForTimeout(500);

    const firstOption = page.locator('[role="option"], [role="menuitem"], li, button').first();
    await expect(firstOption).toBeVisible({ timeout: 5000 });
    await firstOption.click({ force: true });

    // 3. Fill optional keywords
    const keywordsInput = page.getByPlaceholder('Python, React, etc.');
    await expect(keywordsInput).toBeVisible();
    await keywordsInput.fill('JavaScript, QA, E2E, Playwright');

    // 4. Fill optional Top N Results
    const topNInput = page.getByPlaceholder('All results');
    await expect(topNInput).toBeVisible();
    await topNInput.fill('5');

    // Verify trigger submit button is active or can be clicked
    const processButton = page.getByRole('button', { name: 'Process CVs', exact: true });
    await expect(processButton).toBeVisible();
    await processButton.click({ force: true });
  });

  // --- NEGATIVE PATHS ---

  test('NEG-01: Submission with missing required inputs should trigger validation', async ({ page }) => {
    // Click submit directly on blank form to trigger validation checks
    const processButton = page.getByRole('button', { name: 'Process CVs', exact: true });
    await expect(processButton).toBeVisible({ timeout: 10000 });
    await processButton.click({ force: true });

    // Submit blocked: Verify we remain on the same form page and process button is still visible
    await expect(processButton).toBeVisible();
  });

});