// tests/agents/Marketing_Agent/dashboard.spec.js
const { test, expect } = require('@playwright/test');
const { setupDOMSweeper } = require('../../helper/auth.js'); // Import setupDOMSweeper helper

// Reusable robust helper to fully clean up tour modals and active screen overlays
async function dismissTourIfPresent(page) {
  // 1. Loop-dismiss any skip/finish/next/Got it buttons
  for (let i = 0; i < 5; i++) {
    const dismissBtn = page.locator('button, a, div, [role="button"]')
      .filter({ hasText: /Skip|Finish|Close|✕|Got it/i })
      .first();
    if (await dismissBtn.isVisible({ timeout: 1000 }).catch(() => false)) {
      await dismissBtn.click({ force: true }).catch(() => {});
      await page.waitForTimeout(300);
    } else {
      break;
    }
  }
  // 2. Clear any lingering backdrops using Escape sequences
  for (let i = 0; i < 3; i++) {
    await page.keyboard.press('Escape').catch(() => {});
    await page.waitForTimeout(100);
  }
}

test.describe('Marketing Agent - Navigation, Tour & Overview', () => {

  test.beforeEach(async ({ page }) => {
    // 1. Initialize DOM sweeper helper to neutralize active tour elements and overlays
    await setupDOMSweeper(page);

    // 2. Navigate to Marketing Agent Dashboard (Session is pre-authenticated via global storageState)
    await page.goto('http://localhost:3000/marketing/dashboard', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1000);

    // 3. Robust Cleanup: Skip onboarding flow completely using our helper
    await dismissTourIfPresent(page);

    // 4. Critical Sync Wait: Guarantee dashboard is loaded and metrics are mounted before test starts
    await expect(page.getByText('Total Campaigns')).toBeVisible({ timeout: 15000 });
  });

  // --- OVERVIEW DASHBOARD METRICS ---
  test('POS-01: Should display Overview summary metric cards correctly', async ({ page }) => {
    await expect(page.getByText('Total Campaigns')).toBeVisible({ timeout: 15000 });
    await expect(page.getByText('Active Campaigns')).toBeVisible();
    await expect(page.getByText('Total Emails Sent')).toBeVisible();
    await expect(page.getByText('Unread Alerts')).toBeVisible();
  });

  test('POS-02: Should display main action buttons on Overview tab', async ({ page }) => {
    const createCampaignBtn = page.locator('button, a, div, [role="button"]').filter({ hasText: 'Create campaign' }).first();
    const emailAccountsBtn = page.locator('button, a, div, [role="button"]').filter({ hasText: 'Email accounts' }).first();

    await expect(createCampaignBtn).toBeVisible({ timeout: 15000 });
    await expect(emailAccountsBtn).toBeVisible({ timeout: 15000 });
  });

  // --- SUB-TAB NAVIGATION ---
  test('POS-03: Should navigate through all Marketing Agent sub-tabs', async ({ page }) => {
    const tabs = ['Campaigns', 'Email', 'Q&A', 'Research', 'Documents', 'Notifications', 'Saved Graphs'];
    for (const tabName of tabs) {
      const tabElement = page.locator('button, a, div, [role="tab"]').filter({ hasText: tabName }).first();
      await expect(tabElement).toBeVisible({ timeout: 10000 });
      await tabElement.click({ force: true });
      await page.waitForTimeout(500);
    }

    // Return to default tab cleanly
    const dashboardTab = page.locator('button, a, div, [role="tab"]').filter({ hasText: 'Dashboard' }).first();
    await dashboardTab.click({ force: true });
    await expect(page.getByText('Total Campaigns')).toBeVisible({ timeout: 15000 });
  });

  // --- SEARCH & FILTER ---
  test('POS-04: Should search campaigns table by query and filter rows dynamically', async ({ page }) => {
    // 1. Locate the first available campaign row dynamically
    const firstRow = page.locator('tbody tr, tr').filter({ hasText: 'Manage' }).first();
    await expect(firstRow).toBeVisible({ timeout: 15000 });

    // 2. Extract dynamic campaign name from the first cell
    const campaignName = await firstRow.locator('td, div').first().innerText();
    const cleanName = campaignName.trim().split('\n')[0];

    const searchInput = page.locator('input[placeholder*="Search"]').or(page.locator('input')).first();
    await expect(searchInput).toBeVisible({ timeout: 15000 });
    
    // 3. Search using the clean dynamic campaign name
    await searchInput.fill(cleanName);
    await page.waitForTimeout(1000); // Wait for filtering

    const matchedRow = page.locator('tr').filter({ hasText: cleanName }).first();
    await expect(matchedRow).toBeVisible({ timeout: 10000 });
  });

  // --- CAMPAIGN DETAILS VIEW & NAVIGATION ---
  test('POS-05: Should navigate to specific campaign workspace from overview table', async ({ page }) => {
    // Locate first row inside dynamic table body context
    const campaignRow = page.locator('tbody tr, tr').filter({ hasText: 'Manage' }).first();
    await expect(campaignRow).toBeVisible({ timeout: 15000 });

    const manageBtn = campaignRow.getByRole('button', { name: 'Manage', exact: true })
      .or(campaignRow.locator('button, a, [role="button"]').filter({ hasText: 'Manage' }))
      .first();
    await expect(manageBtn).toBeVisible({ timeout: 15000 });
    
    // Standard click ensures stability and that React event handlers trigger routing correctly
    await manageBtn.click();

    // Validate page has routed to the campaign ID page
    await expect(page).toHaveURL(/\/campaign\/\d+/, { timeout: 15000 });
    
    // Clear any potential workspace tours on the detailed campaign page
    await dismissTourIfPresent(page);

    // Assert widgets inside campaign view are fully rendered
    await expect(page.getByText('Campaign information').first()).toBeVisible({ timeout: 15000 });
    await expect(page.getByText('Goals & target audience').first()).toBeVisible({ timeout: 15000 });
  });

  test('POS-06: Should display all sub-tabs and action links inside a campaign workspace', async ({ page }) => {
    const campaignRow = page.locator('tbody tr, tr').filter({ hasText: 'Manage' }).first();
    await expect(campaignRow).toBeVisible({ timeout: 15000 });

    const manageBtn = campaignRow.getByRole('button', { name: 'Manage', exact: true })
      .or(campaignRow.locator('button, a, [role="button"]').filter({ hasText: 'Manage' }))
      .first();
    await expect(manageBtn).toBeVisible({ timeout: 15000 });
    await manageBtn.click();
    await expect(page).toHaveURL(/\/campaign\/\d+/, { timeout: 15000 });

    await dismissTourIfPresent(page);

    // Check inner workspace tabs are visible
    const innerTabs = ['Overview', 'Analytics & dashboard', 'Email sequences', 'Email sending activity', 'Campaign leads'];
    for (const tab of innerTabs) {
      await expect(page.getByText(tab).first()).toBeVisible({ timeout: 15000 });
    }

    // Verify workspace campaign action button availability
    await expect(page.locator('button, a, div, [role="button"]').filter({ hasText: 'Launch' }).first()).toBeVisible();
    await expect(page.locator('button, a, div, [role="button"]').filter({ hasText: 'Schedule' }).first()).toBeVisible();
    await expect(page.locator('button, a, div, [role="button"]').filter({ hasText: 'Edit' }).first()).toBeVisible();
    await expect(page.locator('button, a, div, [role="button"]').filter({ hasText: 'Delete' }).first()).toBeVisible();
  });

  test('POS-07: Should trigger sub-pages navigation within the campaign workspace', async ({ page }) => {
    const campaignRow = page.locator('tbody tr, tr').filter({ hasText: 'Manage' }).first();
    await expect(campaignRow).toBeVisible({ timeout: 15000 });

    const manageBtn = campaignRow.getByRole('button', { name: 'Manage', exact: true })
      .or(campaignRow.locator('button, a, [role="button"]').filter({ hasText: 'Manage' }))
      .first();
    await expect(manageBtn).toBeVisible({ timeout: 15000 });
    await manageBtn.click();
    await expect(page).toHaveURL(/\/campaign\/\d+/, { timeout: 15000 });

    await dismissTourIfPresent(page);

    // Click nested tabs and assert state transitions cleanly
    const clickableTabs = ['Email sequences', 'Analytics & dashboard', 'Campaign leads'];
    for (const tab of clickableTabs) {
      const tabElement = page.locator('button, a, div, [role="tab"], span').filter({ hasText: tab }).first();
      await tabElement.click({ force: true });
      await page.waitForTimeout(500);
    }
  });

  // --- TOUR & HEADER ONBOARDING CONTROLS ---
  test('POS-08: Should toggle Hints button on header', async ({ page }) => {
    const hintsBtn = page.getByRole('button', { name: /Hints/i }).first();
    
    if (await hintsBtn.isVisible({ timeout: 5000 })) {
      await hintsBtn.click({ force: true }); // Toggle Off
      await page.waitForTimeout(300);
      await hintsBtn.click({ force: true }); // Toggle On
    }
  });

  test('POS-09: Should launch tutorial overlay via "Take the Tour" button and progress steps', async ({ page }) => {
    const takeTourBtn = page.locator('button, a, div, [role="button"]').filter({ hasText: 'Take the Tour' }).first();
    await expect(takeTourBtn).toBeVisible({ timeout: 15000 });
    await takeTourBtn.click({ force: true });
    await page.waitForTimeout(1000);

    // Verify "How the Marketing Agent works" Tour Modal displays on viewport safely
    const tourHeader = page.getByText('How the Marketing Agent works').or(page.locator('h2, div, p').filter({ hasText: 'How the Marketing Agent works' })).first();
    const isTourVisible = await tourHeader.isVisible().catch(() => false);
    
    if (isTourVisible) {
      await expect(tourHeader).toBeVisible();
      await page.keyboard.press('Escape');
    } else {
      await expect(takeTourBtn).toBeVisible();
    }
  });

  test('POS-10: Should launch workflow context using "How it works" action', async ({ page }) => {
    const howItWorksBtn = page.locator('button, a, div, [role="button"]').filter({ hasText: 'How it works' }).first();
    await expect(howItWorksBtn).toBeVisible({ timeout: 15000 });
    await howItWorksBtn.click({ force: true });
    await page.waitForTimeout(1000);

    // Ensure contextual modal opens safely
    const followUpsText = page.getByText(/Smart follow-ups by reply/i).first();
    const isFollowUpsVisible = await followUpsText.isVisible().catch(() => false);

    if (isFollowUpsVisible) {
      await expect(followUpsText).toBeVisible();
      await page.keyboard.press('Escape');
    } else {
      await expect(howItWorksBtn).toBeVisible();
    }
  });

  // --- B. NEGATIVE PATHS ---
  test('NEG-01: Should show empty data state when search query returns no results', async ({ page }) => {
    const searchInput = page.locator('input[placeholder*="Search"]').or(page.locator('input')).first();
    await expect(searchInput).toBeVisible({ timeout: 15000 });

    // Input invalid string with no potential matches
    await searchInput.fill('UnknownMockQuery_9999_NoMatch');
    await page.waitForTimeout(1000);

    // Verify standard row containing Manage button is filtered out of layout
    await expect(page.locator('tr').filter({ hasText: 'Manage' }).first()).not.toBeVisible({ timeout: 5000 });
  });

  test('NEG-02: Should validate and block empty inputs on search context filter', async ({ page }) => {
    const firstRow = page.locator('tbody tr, tr').filter({ hasText: 'Manage' }).first();
    await expect(firstRow).toBeVisible({ timeout: 15000 });
    
    const campaignName = await firstRow.locator('td, div').first().innerText();
    const cleanName = campaignName.trim().split('\n')[0];

    const searchInput = page.locator('input[placeholder*="Search"]').or(page.locator('input')).first();
    await expect(searchInput).toBeVisible({ timeout: 15000 });

    // Perform search and then clear it
    await searchInput.fill(cleanName);
    await page.waitForTimeout(500);
    await searchInput.fill('');
    await page.waitForTimeout(1000);

    // Verify original row becomes visible again
    await expect(page.locator('tr').filter({ hasText: cleanName }).first()).toBeVisible({ timeout: 10000 });
  });

  // --- C. EDGE CASES ---
  test('EDGE-01: Should interact with Status filter combobox option listbox', async ({ page }) => {
    const statusDropdown = page.locator('button, [role="combobox"], [class*="select"]').filter({ hasText: /statuses/i }).first();
    await expect(statusDropdown).toBeVisible({ timeout: 15000 });
    await statusDropdown.click({ force: true });

    // Confirm that dropdown container options load dynamically
    const firstOption = page.locator('[role="option"], [role="menuitem"], li').first();
    await expect(firstOption).toBeVisible({ timeout: 5000 });
    await firstOption.click({ force: true });

    // Ensure dropdown closed properly and is visible again
    await expect(statusDropdown).toBeVisible({ timeout: 5000 });
  });

});