// tests/agents/Recruitment_Agent/Dashboard.spec.js
const { test, expect } = require('@playwright/test');
const { setupDOMSweeper } = require('../../helper/auth.js'); // Adjust relative path based on file directory

test.describe('Recruitment Agent - Navigation, Dashboard, Job Descriptions & Analytics', () => {

  test.beforeEach(async ({ page }) => {
    // 1. Setup DOM sweeper to neutralize onboarding tours
    await setupDOMSweeper(page);

    // 2. Navigate directly to the Recruitment Agent Dashboard (entry point)
    await page.goto('http://localhost:3000/recruitment/dashboard', { waitUntil: 'domcontentloaded' });

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

  // --- HELPERS FOR HANDLING AUTO-POPUP DIALOGS & NAVIGATION ---
  
  // Locates specific tab links securely using strict accessibility roles
  function getTabLocator(page, tabName) {
    if (tabName === 'Dashboard') {
      return page.locator('main, #root, body').locator('button, a, [role="tab"]').filter({ hasText: /^Dashboard$/ }).nth(1);
    }
    return page.getByRole('tab', { name: tabName, exact: true })
      .or(page.getByRole('button', { name: tabName, exact: true }))
      .or(page.getByRole('link', { name: tabName, exact: true }))
      .or(page.locator('button, a, div[role="button"]').filter({ hasText: new RegExp(`^${tabName}$`) }))
      .first();
  }

  // Safe client-side tab navigation to maintain local session states and handle tab-specific tours
  async function navigateToTab(page, tabName) {
    const tabButton = getTabLocator(page, tabName);
    await expect(tabButton).toBeVisible({ timeout: 10000 });
    await tabButton.click({ force: true });
    await page.waitForTimeout(1000); // Wait for client-side routing to fully settle

    // Dismiss any dynamic tutorials that pop up when loading the new tab
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
  }

  // Ensures the AI Modal is open (handles both auto-popup and manual click states)
  async function ensureAIModalOpen(page) {
    const modal = page.locator('div[role="dialog"], .modal, div').filter({ hasText: 'Create Job with AI' }).first();
    // Wait a brief moment for the page to initialize and render any auto-popups
    await page.waitForTimeout(1000);
    if (await modal.isVisible().catch(() => false)) {
      return;
    }
    const btn = page.locator('button, a, div[role="button"]').filter({ hasText: /Create Job with AI/i }).first();
    await expect(btn).toBeVisible({ timeout: 10000 });
    await btn.click({ force: true });
    await expect(modal).toBeVisible({ timeout: 10000 });
  }

  // Dismisses the AI Modal if it automatically popped up to clear the background
  async function dismissAIModalIfOpen(page) {
    const modal = page.locator('div[role="dialog"], .modal, div').filter({ hasText: 'Create Job with AI' }).first();
    // Wait for auto-popup state to reveal itself before dismiss checks
    if (await modal.isVisible({ timeout: 3000 }).catch(() => false)) {
      const cancelBtn = modal.getByRole('button', { name: 'Cancel', exact: true });
      const closeXBtn = modal.locator('button').filter({ hasText: '✕' }).or(modal.locator('.close-btn, .close-icon')).first();
      
      if (await cancelBtn.isVisible().catch(() => false)) {
        await cancelBtn.click({ force: true });
      } else if (await closeXBtn.isVisible().catch(() => false)) {
        await closeXBtn.click({ force: true });
      } else {
        await page.keyboard.press('Escape');
      }
      await expect(modal).not.toBeVisible({ timeout: 5000 });
    }
  }

  // --- OVERVIEW DASHBOARD METRICS ---
  test('POS-01: Should display Dashboard summary KPI cards correctly', async ({ page }) => {
    await expect(page.getByText('Total CVs Processed').first()).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('Active Jobs').first()).toBeVisible();
    await expect(page.getByText('Total Interviews').first()).toBeVisible();
    await expect(page.getByText('Pending Interviews').first()).toBeVisible();
  });

  // --- SUB-TAB NAVIGATION ---
  test('POS-02: Should navigate through all Recruitment Agent sub-tabs', async ({ page }) => {
    const tabsList = [
      'Dashboard',
      'Analytics',
      'Job Descriptions',
      'CV Processing',
      'AI Questions',
      'Candidates',
      'Interviews',
      'Saved Prompts',
      'API Tester',
      'Settings'
    ];

    for (const tab of tabsList) {
      const tabButton = getTabLocator(page, tab);
      await expect(tabButton).toBeVisible({ timeout: 5000 });
      await tabButton.click({ force: true });
      await page.waitForTimeout(300); 
    }
  });

  // --- JOB DESCRIPTION CREATION FLOWS ---
  test('POS-03: Create Job with AI - Happy Path', async ({ page }) => {
    await navigateToTab(page, 'Job Descriptions');
    
    // Check auto-popup status
    await ensureAIModalOpen(page);

    const promptInput = page.getByPlaceholder('e.g. MERN Stack Developer, 5+ years, MongoDB, Express, React, Node.js, RESTful APIs, remote...');
    await expect(promptInput).toBeVisible();
    await promptInput.fill('Senior QA Automation Engineer, Playwright, JavaScript, CI/CD, remote');

    const generateButton = page.getByRole('button', { name: 'Generate job description', exact: true });
    await generateButton.click({ force: true });

    // Verify AI generation finishes and successfully populates the manual form fields
    const descTextarea = page.getByPlaceholder('Enter job description...');
    await expect(descTextarea).toBeVisible({ timeout: 20000 });
  });

  test('POS-04: Create Job Manually - Set dates & Save', async ({ page }) => {
    await navigateToTab(page, 'Job Descriptions');
    
    // Clear auto-popup modal blocking click flow
    await dismissAIModalIfOpen(page);

    const createManuallyBtn = page.getByRole('button', { name: '+ Create Job Description', exact: true })
      .or(page.locator('button').filter({ hasText: 'Create Job Description' }));
    await expect(createManuallyBtn).toBeVisible({ timeout: 10000 });
    await createManuallyBtn.click({ force: true });

    const statusToggle = page.locator('button[role="switch"], input[type="checkbox"]').first();
    await statusToggle.click({ force: true });

    const quickSetInput = page.getByPlaceholder('e.g. 30');
    await quickSetInput.fill('45');

    const setDatesButton = page.getByRole('button', { name: 'Set dates', exact: true });
    await setDatesButton.click({ force: true });

    const openDateInput = page.getByPlaceholder('Select open date');
    const closeDateInput = page.getByPlaceholder('Select close date');
    await expect(openDateInput).toBeVisible({ timeout: 10000 });
    await expect(closeDateInput).toBeVisible({ timeout: 10000 });

    const descriptionTextarea = page.getByPlaceholder('Enter job description...');
    const requirementsTextarea = page.getByPlaceholder('Enter job requirements...');

    await descriptionTextarea.fill('This is a manually created job description for automated verification.');
    await requirementsTextarea.fill('Must have clean coding practices, E2E testing focus, and a strong automation background.');

    const saveButton = page.getByRole('button', { name: 'Save', exact: true });
    await saveButton.click({ force: true });

    await expect(saveButton).not.toBeVisible({ timeout: 10000 });
  });

  test('POS-05: Create Job Manually - Transition from AI Modal to Manual Form', async ({ page }) => {
    await navigateToTab(page, 'Job Descriptions');
    
    await ensureAIModalOpen(page);

    const manualTransitionBtn = page.getByRole('button', { name: 'Create manually', exact: true });
    await manualTransitionBtn.click({ force: true });

    await expect(page.getByPlaceholder('e.g. MERN Stack Developer, 5+ years, MongoDB, Express, React, Node.js, RESTful APIs, remote...')).not.toBeVisible();
    await expect(page.getByPlaceholder('Enter job description...')).toBeVisible();
  });

  // --- ANALYTICS TESTS ---
  test('POS-06: Should display overview metrics and chart sections in Analytics', async ({ page }) => {
    await navigateToTab(page, 'Analytics');

    // Validate Summary metrics cards
    await expect(page.getByText('Conversion Rate').first()).toBeVisible({ timeout: 15000 });
    await expect(page.getByText('Avg Role Fit Score').first()).toBeVisible({ timeout: 15000 });
    await expect(page.getByText('9.5%').first()).toBeVisible();
    await expect(page.getByText('0%').first()).toBeVisible();

    // Verify visualization graphs are present
    await expect(page.getByText('Recruitment Funnel').first()).toBeVisible();
    await expect(page.getByText('CVs by Decision').first()).toBeVisible();
    await expect(page.getByText('CVs Over Time').first()).toBeVisible();
  });

  test('POS-07: Should interact with filters, selects and export actions in Analytics', async ({ page }) => {
    await navigateToTab(page, 'Analytics');

    const days30Button = page.locator('button, a, div, li').filter({ hasText: /^30 days$/ }).first();
    await expect(days30Button).toBeVisible({ timeout: 10000 });
    await days30Button.click({ force: true });
    await page.waitForTimeout(300);

    const jobDropdown = page.getByRole('button', { name: 'All Jobs' }).or(page.locator('button:has-text("All Jobs")')).first();
    await jobDropdown.click({ force: true });
    await page.waitForTimeout(500);

    // Resilient job option selection targeting dynamic labels
    const optionSelection = page.locator('[role="option"], [role="menuitem"], li, button').filter({ hasText: /Senior Platform|All Jobs/ }).first();
    await expect(optionSelection).toBeVisible({ timeout: 5000 });
    await optionSelection.click({ force: true });

    const exportCandidatesBtn = page.locator('button, a, div').filter({ hasText: /^Export Candidates$/ }).first();
    await expect(exportCandidatesBtn).toBeVisible({ timeout: 10000 });
    await exportCandidatesBtn.click({ force: true });
  });

  // --- NEGATIVE VALIDATIONS ---
  test('NEG-01: Create Job with AI - Negative Validation (Empty prompt)', async ({ page }) => {
    await navigateToTab(page, 'Job Descriptions');

    await ensureAIModalOpen(page);

    const promptInput = page.getByPlaceholder('e.g. MERN Stack Developer, 5+ years, MongoDB, Express, React, Node.js, RESTful APIs, remote...');
    await promptInput.clear();

    const generateButton = page.getByRole('button', { name: 'Generate job description', exact: true });
    await generateButton.click({ force: true });

    // Verify dialog remains open on failure validation state
    const modalContainer = page.locator('div[role="dialog"], .modal, div').filter({ hasText: 'Create Job with AI' }).first();
    await expect(modalContainer).toBeVisible();
  });

  test('NEG-02: Create Job Manually - Negative Validation (Empty description blocks save)', async ({ page }) => {
    await navigateToTab(page, 'Job Descriptions');

    await dismissAIModalIfOpen(page);

    const createManuallyBtn = page.getByRole('button', { name: '+ Create Job Description', exact: true })
      .or(page.locator('button').filter({ hasText: 'Create Job Description' }));
    await createManuallyBtn.click({ force: true });

    const descriptionTextarea = page.getByPlaceholder('Enter job description...');
    await descriptionTextarea.clear();

    const saveButton = page.getByRole('button', { name: 'Save', exact: true });
    await saveButton.click({ force: true });

    // Assert validation keeps modal visible
    await expect(saveButton).toBeVisible();
  });

  // --- EDGE CASES ---
  test('EDGE-01: Should dismiss job description modals via cancel buttons', async ({ page }) => {
    await navigateToTab(page, 'Job Descriptions');

    // Dismiss manual creation modal
    await dismissAIModalIfOpen(page);

    const createManuallyBtn = page.getByRole('button', { name: '+ Create Job Description', exact: true })
      .or(page.locator('button').filter({ hasText: 'Create Job Description' }));
    await createManuallyBtn.click({ force: true });

    const cancelBtn = page.getByRole('button', { name: 'Cancel', exact: true });
    await cancelBtn.click({ force: true });
    await expect(cancelBtn).not.toBeVisible({ timeout: 5000 });

    // Dismiss AI modal via Escape key
    const createWithAIButton = page.getByRole('button', { name: 'Create Job with AI', exact: true });
    await createWithAIButton.click({ force: true });
    await page.keyboard.press('Escape');
    await expect(page.locator('div[role="dialog"], .modal').filter({ hasText: 'Create Job with AI' }).first()).not.toBeVisible({ timeout: 5000 });
  });

});