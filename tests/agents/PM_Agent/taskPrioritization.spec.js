// tests/agents/PM_Agent/taskPrioritization.spec.js
const { test, expect } = require('@playwright/test');
const { setupDOMSweeper } = require('../../helper/auth.js'); // Adjust path to helpers folder

test.describe('Project Manager Agent - Task Prioritization Module', () => {

  test.beforeEach(async ({ page }) => {
    // 1. Setup DOM sweeper to handle tours
    await setupDOMSweeper(page);

    // 2. Open Dashboard directly (uses saved auth state)
    await page.goto('http://localhost:3000/project-manager/dashboard', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1000);

    // 3. Click "Task Prioritization" tab
    const taskTab = page.locator('[role="tab"]').filter({ hasText: 'Task Prioritization' }).first();
    await taskTab.click({ force: true });

    // 4. Verify the agent workspace is loaded
    await expect(page.getByText('Task Prioritization Agent')).toBeVisible({ timeout: 15000 });

    // 5. Select a project so action buttons are enabled across all tests
    const projectDropdown = page.locator('button[role="combobox"]').first();
    await expect(projectDropdown).toBeVisible({ timeout: 10000 });
    await projectDropdown.click();
    await page.waitForTimeout(500);

    const firstOption = page.locator('[role="option"], [role="menuitem"], li').first();
    if (await firstOption.isVisible()) {
      await firstOption.click({ force: true });
      await page.waitForTimeout(1000); // Allow enabled state styles to apply to buttons
    }
  });

  // --- POSITIVE PATHS ---
  test('POS-01: Should verify a project is selected in the dropdown', async ({ page }) => {
    const projectDropdown = page.locator('button[role="combobox"]').first();
    await expect(projectDropdown).not.toContainText('Select a project');
  });

  test('POS-02: Should verify all agent action buttons are enabled initially', async ({ page }) => {
    // Verify all buttons are enabled at the start of the test
    const prioritizeBtn = page.getByRole('button', { name: 'Prioritize & Order Tasks', exact: true });
    const bottlenecksBtn = page.getByRole('button', { name: 'Find Bottlenecks', exact: true });
    const delegationBtn = page.getByRole('button', { name: 'Suggest Delegation', exact: true });
    const subtasksBtn = page.getByRole('button', { name: 'Generate Subtasks', exact: true });

    await expect(prioritizeBtn).toBeEnabled({ timeout: 5000 });
    await expect(bottlenecksBtn).toBeEnabled();
    await expect(delegationBtn).toBeEnabled();
    await expect(subtasksBtn).toBeEnabled();
  });

  test('POS-03: Should trigger the prioritization workflow successfully', async ({ page }) => {
    const prioritizeBtn = page.getByRole('button', { name: 'Prioritize & Order Tasks', exact: true });
    await expect(prioritizeBtn).toBeEnabled({ timeout: 5000 });
    await prioritizeBtn.click({ force: true });

    // Verify loading/processing state appears on screen
    await expect(page.getByText(/Prioritising & ordering tasks/i)).toBeVisible({ timeout: 5000 });
  });

});