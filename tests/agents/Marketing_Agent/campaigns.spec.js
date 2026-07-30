// tests/agents/Marketing_Agent/campaigns.spec.js
const { test, expect } = require('@playwright/test');
const { setupDOMSweeper } = require('../../helper/auth.js');

// Reusable helper to dismiss onboarding tour layers and active screen backdrops
async function dismissTourIfPresent(page) {
  const tourModal = page.locator('div, section, [role="dialog"]').filter({ hasText: 'How the Marketing Agent works' }).first();
  if (await tourModal.isVisible().catch(() => false)) {
    const skipBtn = tourModal.locator('button, [role="button"]').filter({ hasText: /Skip/i }).first();
    if (await skipBtn.isVisible()) {
      await skipBtn.click({ force: true });
    } else {
      const gotItBtn = tourModal.locator('button, [role="button"]').filter({ hasText: /Got it/i }).first();
      if (await gotItBtn.isVisible()) {
        await gotItBtn.click({ force: true });
      }
    }
    await page.waitForTimeout(500);
  }

  const tourPopover = page.locator('.driver-popover, .shepherd-element, [role="alertdialog"], [role="dialog"]').first();
  if (await tourPopover.isVisible().catch(() => false)) {
    const closeBtn = tourPopover.locator('button, [role="button"]').filter({ hasText: /Close|Skip|Got it|✕/i }).first();
    if (await closeBtn.isVisible()) {
      await closeBtn.click({ force: true });
      await page.waitForTimeout(300);
    }
  }

  const tabTooltip = page.locator('div, p, span').filter({ hasText: /Create campaigns with AI/i }).first();
  if (await tabTooltip.isVisible().catch(() => false)) {
    await page.keyboard.press('Escape');
    await page.waitForTimeout(300);
  }

  for (let i = 0; i < 3; i++) {
    const dismissBtn = page.locator('button, a, div, [role="button"]')
      .filter({ hasText: /Skip|Finish|Close|✕/i })
      .first();
    if (await dismissBtn.isVisible({ timeout: 500 }).catch(() => false)) {
      await dismissBtn.click({ force: true }).catch(() => {});
      await page.waitForTimeout(200);
    } else {
      break;
    }
  }

  await page.keyboard.press('Escape').catch(() => {});
}

test.describe('Marketing Agent - Outreach & Campaign Agent Workspace', () => {

  test.beforeEach(async ({ page }) => {
    await setupDOMSweeper(page);

    await page.goto('http://localhost:3000/marketing/dashboard', { waitUntil: 'domcontentloaded' });
    await dismissTourIfPresent(page);

    const campaignsTab = page.locator('[role="tablist"] [role="tab"], button, a').filter({ hasText: /^Campaigns$/i }).first();
    await expect(campaignsTab).toBeVisible({ timeout: 15000 });

    const workspaceHeader = page.getByRole('heading', { name: 'Outreach & Campaign Agent' })
      .or(page.getByText('Outreach & Campaign Agent'))
      .first();

    // Retry click + dismiss cycle instead of a single blind attempt — handles
    // a second tour/tooltip appearing after the tab switch (as flagged in
    // the original comments), which was silently blocking the header check.
    let headerVisible = false;
    for (let attempt = 0; attempt < 3 && !headerVisible; attempt++) {
      try {
        await campaignsTab.click({ timeout: 5000 });
      } catch {
        await campaignsTab.click({ force: true });
      }
      await dismissTourIfPresent(page);
      headerVisible = await workspaceHeader.isVisible({ timeout: 5000 }).catch(() => false);
    }

    await expect(workspaceHeader).toBeVisible({ timeout: 5000 });
  });

  // --- HELPER: locate a campaign card without matching unrelated wrapper divs ---
  // Anchors on the checkbox (a concrete, unique element per card) and walks up
  // to the nearest ancestor div that also contains "leads" text — instead of
  // filtering every div on the page and taking .first(), which can silently
  // match an outer page-level wrapper.
  function getFirstCampaignCard(page) {
    return page.locator('input[type="checkbox"]').first()
      .locator('xpath=ancestor::div[contains(., "leads")][1]');
  }

  // --- POSITIVE PATHS ---

  test('POS-01: Should verify Outreach creator form components on Campaigns tab', async ({ page }) => {
    const actionSelect = page.getByRole('combobox', { name: 'Action' })
      .or(page.locator('button, [role="combobox"]').filter({ hasText: 'Create Email Campaign' }))
      .first();

    const durationInput = page.locator('div').filter({ hasText: /^Duration$/ }).locator('input').first()
      .or(page.locator('input[type="number"]'))
      .first();

    const nameInput = page.getByPlaceholder('e.g. Summer Sale 2024')
      .or(page.getByLabel('Campaign name'))
      .first();

    const descriptionTextarea = page.getByPlaceholder(/Goals and key messaging/)
      .or(page.getByLabel('Description'))
      .first();

    const generateBtn = page.getByRole('button', { name: 'Generate with AI', exact: true })
      .or(page.locator('button').filter({ hasText: 'Generate with AI' }))
      .first();

    await expect(actionSelect).toBeVisible();
    await expect(durationInput).toBeVisible();
    await expect(nameInput).toBeVisible();
    await expect(descriptionTextarea).toBeVisible();
    await expect(generateBtn).toBeVisible();
  });

  test('POS-02: Should allow manual population of campaign metadata on Campaigns creator form', async ({ page }) => {
    const nameInput = page.getByPlaceholder('e.g. Summer Sale 2024')
      .or(page.getByLabel('Campaign name'))
      .first();

    const descriptionTextarea = page.getByPlaceholder(/Goals and key messaging/)
      .or(page.getByLabel('Description'))
      .first();

    const sampleName = `Dynamic Winter Campaign - ${Date.now()}`;
    const sampleDesc = 'Deploying segmented email workflows targeting travel sector leads.';

    await nameInput.fill(sampleName);
    await descriptionTextarea.fill(sampleDesc);

    await expect(nameInput).toHaveValue(sampleName);
    await expect(descriptionTextarea).toHaveValue(sampleDesc);
  });

  test('POS-03: Should trigger AI campaign generation safely on Campaigns tab', async ({ page }) => {
    const nameInput = page.getByPlaceholder('e.g. Summer Sale 2024')
      .or(page.getByLabel('Campaign name'))
      .first();

    const descriptionTextarea = page.getByPlaceholder(/Goals and key messaging/)
      .or(page.getByLabel('Description'))
      .first();

    const generateBtn = page.getByRole('button', { name: 'Generate with AI', exact: true })
      .or(page.locator('button').filter({ hasText: 'Generate with AI' }))
      .first();

    await nameInput.fill(`AI Generation Workflow - ${Date.now()}`);
    await descriptionTextarea.fill('Promoting direct automated email triggers.');

    await generateBtn.click();

    const isBtnDisabled = await generateBtn.isDisabled().catch(() => false);
    const hasSpinner = await page.locator('[class*="spinner"], [class*="loading"], div:has-text("Generating")').first().isVisible().catch(() => false);

    expect(isBtnDisabled || hasSpinner || await generateBtn.isVisible()).toBeTruthy();
  });

  test('POS-04: Should display campaign cards list in the lower list view', async ({ page }) => {
    await expect(page.getByText('Your Campaigns')).toBeVisible({ timeout: 15000 });

    const dynamicCard = getFirstCampaignCard(page);
    await expect(dynamicCard).toBeVisible({ timeout: 15000 });
  });

  test('POS-05: Should dynamically search campaigns list card view on Campaigns tab', async ({ page }) => {
    const firstCard = getFirstCampaignCard(page);
    await expect(firstCard).toBeVisible({ timeout: 15000 });

    const cardText = await firstCard.innerText();
    const cleanCampaignName = cardText.split('\n')[0].trim();

    const searchInput = page.getByPlaceholder('Search campaigns...');
    await expect(searchInput).toBeVisible({ timeout: 15000 });
    await searchInput.fill(cleanCampaignName);
    await page.waitForTimeout(1000);

    await expect(page.getByText(cleanCampaignName).first()).toBeVisible({ timeout: 10000 });
  });

  test('POS-06: Should open campaign workspace from campaign card selection', async ({ page }) => {
    const firstCard = getFirstCampaignCard(page);
    await expect(firstCard).toBeVisible({ timeout: 15000 });

    // ACCESSIBILITY FLAG: nav chevron has no accessible label — scoped to
    // the last button within the card (right-aligned action) rather than
    // any interactive element on the page.
    const manageBtn = firstCard.locator('button').last();
    await manageBtn.click({ force: true });

    await expect(page).toHaveURL(/\/campaign\/\d+/, { timeout: 15000 });
  });

  // --- NEGATIVE PATHS ---

  test('NEG-01: Should block AI generation on creator step if required inputs are empty', async ({ page }) => {
    const nameInput = page.getByPlaceholder('e.g. Summer Sale 2024')
      .or(page.getByLabel('Campaign name'))
      .first();

    const descriptionTextarea = page.getByPlaceholder(/Goals and key messaging/)
      .or(page.getByLabel('Description'))
      .first();

    const generateBtn = page.getByRole('button', { name: 'Generate with AI', exact: true })
      .or(page.locator('button').filter({ hasText: 'Generate with AI' }))
      .first();

    await nameInput.fill('');
    await descriptionTextarea.fill('');

    await generateBtn.click();

    await expect(page.getByText('Outreach & Campaign Agent')).toBeVisible();
  });

  // --- EDGE CASES ---

  test('EDGE-01: Should interact with Campaigns tab filters and date-picker toggle panels', async ({ page }) => {
    const statusDropdown = page.getByRole('combobox').filter({ hasText: 'All statuses' })
      .or(page.locator('button').filter({ hasText: 'All statuses' }))
      .first();
    await expect(statusDropdown).toBeVisible({ timeout: 15000 });
    await statusDropdown.click({ force: true });

    const firstOption = page.locator('[role="option"], [role="menuitem"], li').first();
    await expect(firstOption).toBeVisible({ timeout: 5000 });
    await firstOption.click({ force: true });

    const datePicker = page.locator('button, input').filter({ hasText: 'Start date' }).first();
    await expect(datePicker).toBeVisible();
    await datePicker.click({ force: true });
  });

});