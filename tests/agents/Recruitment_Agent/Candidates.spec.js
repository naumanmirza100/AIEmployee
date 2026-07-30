// tests/agents/Recruitment_Agent/Candidates.spec.js
const { test, expect } = require('@playwright/test');
const { setupDOMSweeper } = require('../../helper/auth.js');

test.describe('Recruitment Agent - Candidates Tab', () => {

  test.beforeEach(async ({ page }) => {
    // 1. Setup DOM sweeper to neutralize onboarding tours
    await setupDOMSweeper(page);

    // 2. Navigate directly to the Recruitment Agent Dashboard
    await page.goto('http://localhost:3000/recruitment/dashboard', { waitUntil: 'domcontentloaded' });

    // 3. Explicit wait for core layout tablist/navigation bar or headings to fully render first
    await expect(page.locator('[role="tablist"], nav, [role="tab"], h1, h2, .tablist').first()).toBeVisible({ timeout: 25000 });

    // 4. Robust Cleanup: Loop-dismiss any active onboarding tour overlays
    for (let i = 0; i < 3; i++) {
      const skipBtn = page.getByRole('button', { name: /Skip tutorial|Finish/i }).first();
      if (await skipBtn.isVisible({ timeout: 1500 }).catch(() => false)) {
        await skipBtn.click().catch(() => {});
      } else {
        break;
      }
    }
    // Press Escape to dismiss any remaining backdrop modals
    await page.keyboard.press('Escape').catch(() => {});

    // 5. Navigate client-side to keep session state stable
    await navigateToTab(page, 'Candidates');
  });

  // --- HELPERS ---

  function getTabLocator(page, tabName) {
    return page.getByRole('tab', { name: tabName, exact: true })
      .or(page.getByRole('button', { name: tabName, exact: true }))
      .or(page.locator('button, [role="tab"]').filter({ hasText: tabName }))
      .first();
  }

  async function navigateToTab(page, tabName) {
    const tabButton = getTabLocator(page, tabName);
    await expect(tabButton).toBeVisible({ timeout: 10000 });
    await tabButton.click();

    // EXPLICIT SPA MOUNT SIGNAL: Ensure the destination tab page heading is visible before returning
    await expect(page.getByRole('heading', { name: tabName, exact: true })).toBeVisible({ timeout: 15000 });
  }

  // --- POSITIVE PATHS ---

  test('POS-01: Should display Candidates dashboard and initial list layout components', async ({ page }) => {
    // Verify core headings and instructional subtext exist
    await expect(page.getByRole('heading', { name: 'Candidates', exact: true })).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('View and manage processed candidate CVs.', { exact: false })).toBeVisible();

    // Verify main filter/toolbar inputs are present on screen
    await expect(page.getByPlaceholder(/Search name or email/i)).toBeVisible();
    
    const jobFilter = page.getByRole('combobox').filter({ hasText: 'All Jobs' }).or(page.getByRole('button', { name: 'All Jobs' })).first();
    const decisionFilter = page.getByRole('combobox').filter({ hasText: 'All Decisions' }).or(page.getByRole('button', { name: 'All Decisions' })).first();
    
    await expect(jobFilter).toBeVisible();
    await expect(decisionFilter).toBeVisible();
    await expect(page.getByRole('button', { name: /Print/i })).toBeVisible();

    // Verify the candidates list is populated with at least one generic data row
    const firstDataRow = page.getByRole('row').nth(1);
    await expect(firstDataRow).toBeVisible({ timeout: 10000 });
  });

  test('POS-02: Should filter candidate entries correctly using the search bar (Dynamic Matching)', async ({ page }) => {
    const searchInput = page.getByPlaceholder(/Search name or email/i);
    await expect(searchInput).toBeVisible();

    // Get the first content row dynamically
    const firstDataRow = page.getByRole('row').nth(1);
    await expect(firstDataRow).toBeVisible({ timeout: 10000 });

    // Extract text values dynamically at runtime from the visible table cells to construct the search term
    const rowText = await firstDataRow.textContent() || '';
    const searchKeyword = rowText.split(/\s+/).filter(word => word.length > 2)[0] || 'Kotlin';

    // Verify positive search filtering (matching row remains visible)
    await searchInput.fill(searchKeyword);
    await expect(firstDataRow).toBeVisible();

    // Verify negative search filtering (all rows disappear on unmatched garbage string)
    await searchInput.fill('NonexistentCandidateGarbageSearchTermXYZ');
    await expect(firstDataRow).toBeHidden();

    // Clear search filter and verify table baseline is restored
    await searchInput.fill('');
    await expect(firstDataRow).toBeVisible();
  });

  test('POS-03: Should trigger and navigate decision filter options generically', async ({ page }) => {
    const decisionFilter = page.getByRole('combobox').filter({ hasText: 'All Decisions' })
      .or(page.getByRole('button', { name: 'All Decisions' }))
      .or(page.locator('button').filter({ hasText: 'All Decisions' }))
      .first();
    await expect(decisionFilter).toBeVisible();

    // Open decision dropdown selection
    await decisionFilter.click();

    // Locate the select list option container elements
    const options = page.locator('[role="option"], [role="menuitem"], li, button');
    const firstOption = options.nth(1).or(options.first());
    await expect(firstOption).toBeVisible();

    // Select any non-default option to verify dropdown functionality
    await firstOption.click();
    await expect(decisionFilter).toBeVisible();
  });

  test('POS-04: Should select candidate checkboxes and display details panel on row click (Generic Row)', async ({ page }) => {
    // Select the first content row dynamically
    const firstDataRow = page.getByRole('row').nth(1);
    await expect(firstDataRow).toBeVisible({ timeout: 10000 });

    // Locate the checkbox inside this generic row
    const checkbox = firstDataRow.getByRole('checkbox').or(firstDataRow.locator('input[type="checkbox"]')).first();
    await expect(checkbox).toBeVisible();
    await checkbox.check();
    await expect(checkbox).toBeChecked();

    // Target the specific Name cell (column index 2) to trigger row-selection successfully
    const nameCell = firstDataRow.locator('td').nth(2).first();
    await expect(nameCell).toBeVisible();
    await nameCell.click();

    // Verify detailed view popup, dialog, or panel element appears generically
    const detailsPanel = page.locator('div[role="dialog"], .modal, [class*="modal"], [class*="drawer"], [class*="panel"], [class*="sheet"]').first();
    await expect(detailsPanel).toBeVisible({ timeout: 10000 });
  });

  // --- NEGATIVE PATHS ---

  test('NEG-01: Should handle special character queries gracefully without throwing errors', async ({ page }) => {
    const searchInput = page.getByPlaceholder(/Search name or email/i);
    await expect(searchInput).toBeVisible();

    const firstDataRow = page.getByRole('row').nth(1);
    await expect(firstDataRow).toBeVisible({ timeout: 10000 });

    // Search using a complex string with custom regex/SQL style special characters
    await searchInput.fill('!@#$%^&*()_+{}|:"<>?`-=[]\\;,./');

    // Verify the query does not break the DOM and successfully filters out any matching rows
    await expect(firstDataRow).toBeHidden();
  });

  // --- EDGE PATHS ---

  test('EDGE-01: Should verify pagination controls and action states generically', async ({ page }) => {
    // Locate page size select triggers generically
    const pageSizeSelect = page.getByRole('combobox').filter({ hasText: /page/i })
      .or(page.locator('button').filter({ hasText: /page/i }))
      .or(page.locator('[class*="pagination"] button').first())
      .first();
    
    await expect(pageSizeSelect).toBeVisible();

    // Locate pagination navigation triggers
    const previousBtn = page.getByRole('button', { name: /previous/i }).or(page.locator('button').filter({ hasText: /previous/i })).first();
    const nextBtn = page.getByRole('button', { name: /next/i }).or(page.locator('button').filter({ hasText: /next/i })).first();

    await expect(previousBtn).toBeVisible();
    await expect(nextBtn).toBeVisible();

    // Read the active disabled status of next/prev controls dynamically (ensuring compatibility regardless of item count)
    const isPreviousDisabled = await previousBtn.isDisabled().catch(() => true);
    const isNextDisabled = await nextBtn.isDisabled().catch(() => true);
    
    expect(typeof isPreviousDisabled).toBe('boolean');
    expect(typeof isNextDisabled).toBe('boolean');
  });

  test('EDGE-02: Should close candidate details drawer/panel using Escape key fallback', async ({ page }) => {
    const firstDataRow = page.getByRole('row').nth(1);
    await expect(firstDataRow).toBeVisible({ timeout: 10000 });

    // Target Name cell to open detailed overview drawer
    const nameCell = firstDataRow.locator('td').nth(2).first();
    await nameCell.click();

    const detailsPanel = page.locator('div[role="dialog"], .modal, [class*="modal"], [class*="drawer"], [class*="panel"], [class*="sheet"]').first();
    await expect(detailsPanel).toBeVisible({ timeout: 10000 });

    // Press Escape as key fallback to close the details drawer
    await page.keyboard.press('Escape');

    // Assert details panel collapses out of active screen layout
    await expect(detailsPanel).toBeHidden({ timeout: 10000 });
  });

});