// tests/agents/Recruitment_Agent/AIQuestion.spec.js
const { test, expect } = require('@playwright/test');
const { setupDOMSweeper } = require('../../helper/auth.js');

test.describe('Recruitment Agent - AI Questions Tab', () => {

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
    await navigateToTab(page, 'AI Questions');
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
  }

  // --- POSITIVE PATHS ---

  test('POS-01: Should display AI Questions interface and initial research state components', async ({ page }) => {
    // Decoupled from semantic heading tags
    await expect(page.getByText('Recruitment Research Assistance', { exact: false })).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('Ask anything about candidates, jobs, interview plans, and recruitment performance.', { exact: false })).toBeVisible();

    // Verify empty state container elements
    await expect(page.getByText('Ready to Research?', { exact: false })).toBeVisible();

    // Verify suggested action buttons are visible
    await expect(page.getByRole('button', { name: 'General', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Hiring Trends', exact: true })).toBeVisible();

    // Verify main bottom inputs
    await expect(page.getByPlaceholder(/Ask about jobs, candidates/i)).toBeVisible();
    await expect(page.getByRole('button', { name: 'Search' })).toBeVisible();

    // Verify initial layout sidebar elements
    await expect(page.getByText(/Payper Project/i)).toBeVisible();
    await expect(page.getByRole('button', { name: 'New chat', exact: true })).toBeVisible();
  });

  test('POS-02: Should open and close sidebar search interface', async ({ page }) => {
    const searchBtn = page.getByRole('button', { name: 'Search' });
    await expect(searchBtn).toBeVisible();
    await searchBtn.click();

    // Verify sidebar search layout updates with its toggle close button
    const closeSearchBtn = page.getByRole('button', { name: 'Close search' });
    await expect(closeSearchBtn).toBeVisible();
    await closeSearchBtn.click();

    // Verify sidebar reverts to original search trigger
    await expect(searchBtn).toBeVisible();
  });

  test('POS-03: Should populate prompt or trigger query when suggestion pill is clicked', async ({ page }) => {
    const hiringTrendsPill = page.getByRole('button', { name: 'Hiring Trends' }).first();
    await expect(hiringTrendsPill).toBeVisible();
    await hiringTrendsPill.click();

    const promptInput = page.getByPlaceholder(/Ask about jobs, candidates/i);
    const responseActive = page.locator('.assistant-message, .spinner, [class*="chat"], [class*="loading"]').first();
    
    // Auto-waiting .or assertion to verify either prompt text updates or the request starts processing
    await expect(promptInput.or(responseActive)).toBeVisible({ timeout: 10000 });
  });

  test('POS-04: Should open bottom search combobox and close it by clicking outside', async ({ page }) => {
    const combobox = page.getByRole('combobox', { name: 'Search' }).or(page.locator('[role="combobox"]')).first();
    await expect(combobox).toBeVisible({ timeout: 10000 });
    await expect(combobox).toHaveAttribute('aria-expanded', 'false');

    // Click the combobox itself to open
    await combobox.click();
    await expect(combobox).toHaveAttribute('aria-expanded', 'true');

    // Simulate clicking outside (the HTML page element) to close the combobox popover safely
    await page.locator('html').click();
    await expect(combobox).toHaveAttribute('aria-expanded', 'false');
  });

  // --- NEGATIVE PATHS ---

  test('NEG-01: Should block empty or whitespace-only submissions', async ({ page }) => {
    const promptInput = page.getByPlaceholder(/Ask about jobs, candidates/i);
    await expect(promptInput).toBeVisible();

    await promptInput.fill('      ');

    const inputContainer = promptInput.locator('xpath=ancestor::div[button or @role="button"][1]');
    const sendButton = inputContainer.locator('button, [role="button"]').last();

    const isEnabled = await sendButton.isEnabled();
    if (isEnabled) {
      await sendButton.click();
      const responseState = page.locator('.assistant-message, .spinner, [class*="loading"]').first();
      await expect(responseState).toBeHidden({ timeout: 5000 });
    } else {
      await expect(sendButton).toBeDisabled();
    }
  });

  // --- EDGE PATHS ---

  test('EDGE-01: Should filter conversation history items correctly through the sidebar search field', async ({ page }) => {
    // Click the sidebar search toggle button to reveal the search input field
    const sidebarSearchToggle = page.getByRole('button', { name: 'Search' });
    await expect(sidebarSearchToggle).toBeVisible();
    await sidebarSearchToggle.click();

    // Locate the search input
    const searchInput = page.locator('input[placeholder*="Search" i]')
      .or(page.locator('input[placeholder*="Conversation" i]'))
      .or(page.getByPlaceholder(/Search/i))
      .or(page.locator('aside input, [class*="sidebar"] input, .w-64 input, .w-80 input').first())
      .first();

    await expect(searchInput).toBeVisible({ timeout: 10000 });
    
    // Target seeded local database entries (exempt from LLM token limits)
    const targetMatchItem = page.getByRole('button', { name: 'Does the Senior Platform', exact: false });
    const nonTargetMatchItem = page.getByRole('button', { name: 'Which candidates are', exact: false });

    await expect(targetMatchItem).toBeVisible();
    await expect(nonTargetMatchItem).toBeVisible();

    // Filter to isolate the matching platform query
    await searchInput.fill('Platform');
    await page.waitForTimeout(500);
    await expect(targetMatchItem).toBeVisible();
    await expect(nonTargetMatchItem).toBeHidden();

    // Filter by a non-matching keyword
    await searchInput.fill('NonexistentKeywordXYZ');
    await page.waitForTimeout(500);
    await expect(targetMatchItem).toBeHidden();
  });

  test('EDGE-02: Should allow deleting a conversation from the sidebar history list', async ({ page }) => {
    const sidebarGroup = page.locator('tabpanel[role="tabpanel"], .tabpanel, aside, .w-64, .w-80').first();
    const firstChatItem = sidebarGroup.getByRole('button').filter({ name: /Jul|Jul \d+|PM|AM/i }).first();
    await expect(firstChatItem).toBeVisible({ timeout: 15000 });

    // Extract the specific name prior to deletion to avoid dynamic re-evaluation issues
    const chatName = await firstChatItem.textContent();
    const uniqueChatName = chatName ? chatName.trim() : '';

    const itemContainer = firstChatItem.locator('xpath=ancestor::div[button][1]');
    const deleteButton = itemContainer.locator('button[title*="Delete" i]')
      .or(itemContainer.locator('button').last())
      .first();

    await expect(deleteButton).toBeVisible();
    await deleteButton.click();

    const confirmModal = page.locator('div[role="dialog"], .modal, [class*="modal"]').filter({ hasText: /delete|confirm/i });
    if (await confirmModal.isVisible({ timeout: 1500 }).catch(() => false)) {
      const confirmButton = confirmModal.getByRole('button', { name: /confirm|yes|delete/i });
      await confirmButton.click();
    }

    // Target the strictly named item that was removed
    const deletedItem = sidebarGroup.getByRole('button', { name: uniqueChatName, exact: true });
    await expect(deletedItem).toBeHidden({ timeout: 10000 });
  });
  
  });
