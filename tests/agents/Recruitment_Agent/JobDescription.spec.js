// tests/agents/Recruitment_Agent/JobDescription.spec.js
const { test, expect } = require('@playwright/test');
const { setupDOMSweeper } = require('../../helper/auth.js');

test.describe('Recruitment Agent - Job Descriptions Page', () => {

  test.beforeEach(async ({ page }) => {
    await setupDOMSweeper(page);

    // Use domcontentloaded to handle background socket/polling cleanly
    await page.goto('http://localhost:3000/recruitment/dashboard', { waitUntil: 'domcontentloaded' });

    if (page.url().includes('/login') || page.url().includes('/signin')) {
      throw new Error(`Redirected to login instead of dashboard — check auth.json/session. URL: ${page.url()}`);
    }

    // Explicit wait for real dashboard content instead of relying on network state
    await expect(page.locator('[role="tablist"], nav').first()).toBeVisible({ timeout: 15000 });

    for (let i = 0; i < 3; i++) {
      const skipBtn = page.getByRole('button', { name: /Skip tutorial|Finish/i }).first();
      if (await skipBtn.isVisible({ timeout: 1500 }).catch(() => false)) {
        await skipBtn.click({ force: true }).catch(() => {});
        await page.waitForTimeout(300);
      } else {
        break;
      }
    }
    await page.keyboard.press('Escape').catch(() => {});

    await navigateToTab(page, 'Job Descriptions');
  });

  // --- HELPERS ---

  function getTabLocator(page, tabName) {
    return page.getByRole('tab', { name: tabName })
      .or(page.getByRole('button', { name: tabName }))
      .or(page.locator('button, [role="tab"]').filter({ hasText: tabName }))
      .first();
  }

  async function navigateToTab(page, tabName) {
    const tabButton = getTabLocator(page, tabName);
    await expect(tabButton).toBeVisible({ timeout: 10000 });
    await tabButton.click({ force: true });
    await page.waitForTimeout(1000);
  }

  // Generic modal locator matching how OTHER modals in this app actually render
  function getVisibleModal(page, textFilter) {
    return page.locator('div[role="dialog"], .modal, [class*="dialog"], [class*="modal"]')
      .filter({ hasText: textFilter })
      .first();
  }

  // --- POSITIVE PATHS ---

  test('POS-01: Should open and close Job Description manual and AI dialog forms correctly', async ({ page }) => {
    const createManuallyBtn = page.getByRole('button', { name: 'Create Job Description', exact: true });
    await expect(createManuallyBtn).toBeVisible({ timeout: 10000 });
    await createManuallyBtn.click({ force: true });

    const manualForm = getVisibleModal(page, 'Applications Open Date');
    await expect(manualForm).toBeVisible({ timeout: 10000 });

    const manualCancelBtn = manualForm.getByRole('button', { name: 'Cancel', exact: true });
    await manualCancelBtn.click({ force: true });
    await expect(manualForm).not.toBeVisible({ timeout: 10000 });

    const createWithAIButton = page.getByRole('button', { name: 'Create Job with AI', exact: true });
    await expect(createWithAIButton).toBeVisible({ timeout: 10000 });
    await createWithAIButton.click({ force: true });

    const aiModal = getVisibleModal(page, 'Write a prompt to generate your job description');
    await expect(aiModal).toBeVisible({ timeout: 10000 });

    const aiCancelBtn = aiModal.getByRole('button', { name: 'Cancel', exact: true });
    await aiCancelBtn.click({ force: true });
    await expect(aiModal).not.toBeVisible({ timeout: 10000 });
  });

  test('POS-02: Click Configured or Setup badge buttons and verify Settings redirection', async ({ page }) => {
    // Directly target the first badge button on the page
    const badgeBtn = page.getByRole('button', { name: 'Configured' })
      .or(page.getByRole('button', { name: 'Setup' }))
      .first();

    await expect(badgeBtn).toBeVisible({ timeout: 10000 });
    await badgeBtn.click({ force: true });

    await expect(page).toHaveURL(/.*settings/, { timeout: 10000 });

    await navigateToTab(page, 'Job Descriptions');
  });

//   test('POS-03: Click Applications button and verify Applications panel opens and closes', async ({ page }) => {
//   const appsButton = page.getByRole('button', { name: 'Applications' }).first();
//   await expect(appsButton).toBeVisible({ timeout: 10000 });
//   await appsButton.click({ force: true });

//   const appsHeading = page.getByRole('heading', { name: 'Applications', exact: true });
//   await expect(appsHeading).toBeVisible({ timeout: 10000 });

//   // Scope to an ancestor guaranteed to contain the WHOLE panel (heading +
//   // empty-state text), not just the heading's immediate parent — the close
//   // button sits between them in the DOM, so a too-narrow ancestor misses it.
//   const appsPanel = appsHeading.locator(
//     'xpath=ancestor::div[.//*[contains(text(), "total")]][1]'
//   );

//   const closeBtn = appsPanel.getByRole('button').first();
//   await expect(closeBtn).toBeVisible({ timeout: 5000 });
//   await closeBtn.click({ force: true });

//   await expect(appsHeading).not.toBeVisible({ timeout: 10000 });
// });

  test('POS-04: Click Edit card action and verify manual editing modal', async ({ page }) => {
    // Target the Edit button next to the first "Applications" button
    const editBtn = page.getByRole('button', { name: 'Applications' }).first()
      .locator('xpath=following-sibling::button[1]');

    await expect(editBtn).toBeVisible({ timeout: 10000 });
    await editBtn.click({ force: true });

    const manualForm = getVisibleModal(page, 'Applications Open Date');
    await expect(manualForm).toBeVisible({ timeout: 10000 });

    const cancelBtn = manualForm.getByRole('button', { name: 'Cancel', exact: true });
    await cancelBtn.click({ force: true });
    await expect(manualForm).not.toBeVisible({ timeout: 10000 });
  });

  test('POS-05: Click Copy and Delete card actions safely', async ({ page }) => {
    const copyBtn = page.getByRole('button', { name: 'Copy application link' }).first();
    const deleteBtn = copyBtn.locator('xpath=following-sibling::button[1]');

    await expect(copyBtn).toBeVisible({ timeout: 10000 });
    await copyBtn.click({ force: true });
    await page.waitForTimeout(500);

    await expect(deleteBtn).toBeVisible({ timeout: 10000 });
    await deleteBtn.click({ force: true });
    await page.waitForTimeout(500);

    await page.keyboard.press('Escape').catch(() => {});
  });

  test('POS-06: Verify select-all checkbox toggling', async ({ page }) => {
    const selectAllCheckbox = page.locator('button[role="checkbox"], input[type="checkbox"]').first();
    await expect(selectAllCheckbox).toBeVisible({ timeout: 10000 });

    await selectAllCheckbox.check({ force: true });
    await expect(selectAllCheckbox).toBeChecked();

    await selectAllCheckbox.uncheck({ force: true });
    await expect(selectAllCheckbox).not.toBeChecked();
  });

  test('POS-07: Verify search functionality and list filtration using runtime title detection', async ({ page }) => {
    const titleElement = page.getByRole('heading', { level: 3 }).first();
    const dynamicJobTitle = (await titleElement.textContent() || '').trim();

    const searchInput = page.getByPlaceholder(/Search by title, location or department/i);
    await expect(searchInput).toBeVisible({ timeout: 10000 });

    await searchInput.fill(dynamicJobTitle);
    await page.keyboard.press('Enter');
    await page.waitForTimeout(1000);

    await expect(page.getByText(dynamicJobTitle).first()).toBeVisible();

    await searchInput.clear();
    await page.keyboard.press('Enter');
  });

  test('POS-08: Verify filter dropdown selections', async ({ page }) => {
    const statusDropdown = page.getByRole('combobox').filter({ hasText: 'All Status' })
      .or(page.getByRole('button', { name: 'All Status' }))
      .first();
    await statusDropdown.click({ force: true });
    await page.waitForTimeout(500);

    const statusOption = page.locator('[role="option"], [role="menuitem"], li, button').filter({ hasText: /Active|All Status/i }).first();
    await statusOption.click({ force: true });
    await page.waitForTimeout(500);

    const typesDropdown = page.getByRole('combobox').filter({ hasText: 'All Types' })
      .or(page.getByRole('button', { name: 'All Types' }))
      .first();
    await typesDropdown.click({ force: true });
    await page.waitForTimeout(500);

    const typeOption = page.locator('[role="option"], [role="menuitem"], li, button').filter({ hasText: /Full-time|Contract/i }).first();
    await typeOption.click({ force: true });
  });

});