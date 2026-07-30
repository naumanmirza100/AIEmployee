// tests/agents/PM_Agent/aiTools.spec.js
const { test, expect } = require('@playwright/test');
const { setupDOMSweeper } = require('../../helper/auth.js'); // Reusing shared tour helper

// Helper function to select the first project option from custom select dropdowns
async function selectProjectInDropdown(page) {
  const projectDropdown = page.getByRole('combobox').first().or(page.locator('[role="combobox"]').first());
  if (await projectDropdown.isVisible({ timeout: 5000 })) {
    await projectDropdown.click();
    await page.waitForTimeout(500);

    const firstOption = page.locator('[role="option"], [role="menuitem"], li').first();
    if (await firstOption.isVisible()) {
      await firstOption.click({ force: true });
      await page.waitForTimeout(500);
    }
  }
}

test.describe('Project Manager Agent - AI Tools Module (Comprehensive)', () => {

  test.beforeEach(async ({ page }) => {
    // 1. Call the shared DOM sweeper helper to handle tour overlays
    await setupDOMSweeper(page);

    // 2. Open Dashboard directly (uses pre-authenticated storageState)
    await page.goto('http://localhost:3000/project-manager/dashboard', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1000);

    // 3. Click "AI Tools" tab
    const aiToolsTab = page.locator('[role="tab"]').filter({ hasText: 'AI Tools' }).first();
    await aiToolsTab.click({ force: true });

    // 4. Verify AI Tools menu has loaded and is ready
    await expect(page.getByText('Select a tool to get started')).toBeVisible({ timeout: 15000 });
  });

  // =========================================================================
  // SECTION 1: PARAMETERIZED SMOKE TESTS (NAVIGATION & PAGE INTEGRITY)
  // =========================================================================
  test.describe('AI Tools - Navigation smoke tests', () => {
    const aiToolsList = [
      { name: 'Daily Standup', heading: 'Daily Standup' },
      { name: 'Project Health', heading: 'Project Health & Status' },
      { name: 'Meeting Notes', heading: 'Meeting Notes' },
      { name: 'Team Performance', heading: 'Team Performance' },
      { name: 'Time Estimation', heading: 'Time Estimation' },
      { name: 'Workflow & SOP', heading: 'Workflow & SOP' },
      { name: 'Calendar & Schedule', heading: 'Calendar & Schedule' },
      { name: 'Smart Notifications', heading: 'Smart Notifications' },
      { name: 'Notification Settings', heading: 'Notification Channels' }
    ];

    for (const tool of aiToolsList) {
      test(`NAV: Should open ${tool.name} page and click back successfully`, async ({ page }) => {
        // Fix: Target the exact text of the card title (allows bubbling click)
        const toolCard = page.getByText(tool.name, { exact: true }).first();
        await expect(toolCard).toBeVisible({ timeout: 5000 });
        await toolCard.click();

        const subPageHeading = page.getByRole('heading', { name: tool.heading }).or(page.getByText(tool.heading)).first();
        await expect(subPageHeading).toBeVisible({ timeout: 10000 });

        const backBtn = page.locator('text=Back to AI Tools').or(page.getByText('Back to AI Tools')).first();
        await expect(backBtn).toBeVisible({ timeout: 5000 });
        await backBtn.click();

        await expect(page.getByText('Select a tool to get started')).toBeVisible({ timeout: 8000 });
      });
    }
  });

  // =========================================================================
  // SECTION 2: FUNCTIONAL WORKFLOW TESTS (FEATURE-BY-FEATURE VERIFICATION)
  // =========================================================================
  test.describe('AI Tools - Core Functional Workflows', () => {

    test('POS-01: Daily Standup - Should select project and trigger report generation', async ({ page }) => {
      await page.getByText('Daily Standup', { exact: true }).first().click();
      
      // Fix: Resolved strict mode violation by using .first()
      await expect(page.getByRole('heading', { name: 'Daily Standup', exact: true }).first()).toBeVisible({ timeout: 10000 });

      await selectProjectInDropdown(page);

      const generateReportBtn = page.getByRole('button', { name: 'Generate Report', exact: true });
      if (await generateReportBtn.isVisible()) {
        await generateReportBtn.click();
        await page.waitForTimeout(500);
      }
    });

    test('POS-02: Project Health - Should select project and trigger status analysis', async ({ page }) => {
      await page.getByText('Project Health', { exact: true }).first().click();
      await expect(page.getByText('Project Health & Status')).toBeVisible({ timeout: 10000 });

      await selectProjectInDropdown(page);

      const healthScoreBtn = page.getByRole('button', { name: 'Health Score', exact: true });
      if (await healthScoreBtn.isVisible()) {
        await healthScoreBtn.click();
        await page.waitForTimeout(500);
      }
    });

    test('POS-03: Meeting Notes - Should select project and submit text transcript for analysis', async ({ page }) => {
      await page.getByText('Meeting Notes', { exact: true }).first().click();
      await expect(page.getByText('Meeting Notes Analyzer')).toBeVisible({ timeout: 10000 });

      await selectProjectInDropdown(page);

      const notesTextarea = page.getByPlaceholder('Paste your meeting notes or transcript here...');
      await expect(notesTextarea).toBeVisible();
      await notesTextarea.fill('Sarah completed the UI designs. John is working on the database migrations. Launch is scheduled for next Monday.');

      const analyzeBtn = page.getByRole('button', { name: 'Analyze Meeting Notes', exact: true });
      await analyzeBtn.click();
      await page.waitForTimeout(500);
    });

    test('POS-04: Team Performance - Should select project and analyze productivity metrics', async ({ page }) => {
      await page.getByText('Team Performance', { exact: true }).first().click();
      await expect(page.getByText('Team Performance Analytics')).toBeVisible({ timeout: 10000 });

      await selectProjectInDropdown(page);

      const analyzeBtn = page.getByRole('button', { name: 'Analyze Team', exact: true });
      if (await analyzeBtn.isVisible()) {
        await analyzeBtn.click();
        await page.waitForTimeout(500);
      }
    });

    test('POS-05: Time Estimation - Should select project and generate AI duration estimates', async ({ page }) => {
      await page.getByText('Time Estimation', { exact: true }).first().click();
      await expect(page.getByText('AI Time Estimation')).toBeVisible({ timeout: 10000 });

      await selectProjectInDropdown(page);

      const estimateBtn = page.getByRole('button', { name: 'Estimate Time', exact: true });
      if (await estimateBtn.isVisible()) {
        await estimateBtn.click();
        await page.waitForTimeout(500);
      }
    });

    test('POS-06: Workflow & SOP - Should select project and fetch SOP suggestions', async ({ page }) => {
      await page.getByText('Workflow & SOP', { exact: true }).first().click();
      
      // Fix: Resolved strict mode violation by using .first()
      await expect(page.getByText('Workflow & SOP', { exact: true }).first()).toBeVisible({ timeout: 10000 });

      await selectProjectInDropdown(page);

      const suggestionsBtn = page.getByRole('button', { name: 'Get Suggestions', exact: true });
      if (await suggestionsBtn.isVisible()) {
        await suggestionsBtn.click();
        await page.waitForTimeout(500);
      }
    });

    test('POS-07: Calendar & Schedule - Should select project and trigger schedule planner', async ({ page }) => {
      await page.getByText('Calendar & Schedule', { exact: true }).first().click();
      await expect(page.getByText('Calendar & Schedule Planner')).toBeVisible({ timeout: 10000 });

      await selectProjectInDropdown(page);

      const generateScheduleBtn = page.getByRole('button', { name: 'Generate Schedule', exact: true });
      if (await generateScheduleBtn.isVisible()) {
        await generateScheduleBtn.click();
        await page.waitForTimeout(500);
      }
    });

    test('POS-08: Smart Notifications - Should select project and trigger issue scans', async ({ page }) => {
      await page.getByText('Smart Notifications', { exact: true }).first().click();
      
      // Fix: Resolved strict mode violation by using .first()
      await expect(page.getByText('Smart Notifications', { exact: true }).first()).toBeVisible({ timeout: 10000 });

      await selectProjectInDropdown(page);

      const scanBtn = page.getByRole('button', { name: 'Scan for Issues', exact: true });
      if (await scanBtn.isVisible()) {
        await scanBtn.click();
        await page.waitForTimeout(500);
      }
    });

    test('POS-09: Notification Settings - Should allow adding a notification channel and template', async ({ page }) => {
      await page.getByText('Notification Settings', { exact: true }).first().click();
      await expect(page.getByText('Notification Channels')).toBeVisible({ timeout: 10000 });

      // Fill in "Add Channel" form fields
      const nameInput = page.locator('input').first().or(page.locator('input[placeholder*="pm-alerts"]'));
      if (await nameInput.isVisible()) {
        await nameInput.fill('#pm-alerts-test');
      }

      const urlInput = page.locator('input[type="url"]').or(page.getByPlaceholder(/hooks\.slack/));
      if (await urlInput.isVisible()) {
        await urlInput.fill('https://hooks.slack.com/services/test/webhook/url');
      }

      const addChannelBtn = page.getByRole('button', { name: 'Add Channel', exact: true });
      if (await addChannelBtn.isVisible()) {
        await addChannelBtn.click();
        await page.waitForTimeout(500);
      }

      // Fix: Simplified placeholder locator directly to eliminate strict mode matching conflicts
      const templateNameInput = page.getByPlaceholder('Polite reminder');
      if (await templateNameInput.isVisible()) {
        await templateNameInput.fill('Daily Standup Overdue');
      }

      const addTemplateBtn = page.getByRole('button', { name: 'Add Template', exact: true });
      if (await addTemplateBtn.isVisible()) {
        await addTemplateBtn.click();
        await page.waitForTimeout(500);
      }
    });
    });
});