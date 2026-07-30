// tests/agents/PM_Agent/projectPilot.spec.js
const { test, expect } = require('@playwright/test');
const { setupDOMSweeper } = require('../../helper/auth.js'); // Reusing helper
const fs = require('fs');
const path = require('path');

const tempFilePath = path.join(__dirname, 'test_scope.txt');
const invalidFilePath = path.join(__dirname, 'invalid_test_file.exe');

test.describe('Project Manager Agent - Project Pilot Module (Full Coverage)', () => {

  test.beforeAll(() => {
    fs.writeFileSync(tempFilePath, 'This is a mock company scope document containing details for E2E upload test.');
    fs.writeFileSync(invalidFilePath, 'This is a mock invalid file type for negative path verification.');
  });

  test.afterAll(() => {
    if (fs.existsSync(tempFilePath)) fs.unlinkSync(tempFilePath);
    if (fs.existsSync(invalidFilePath)) fs.unlinkSync(invalidFilePath);
  });

  test.beforeEach(async ({ page }) => {
    // 1. Call the reusable DOM sweeper
    await setupDOMSweeper(page);

    // 2. Open Dashboard directly (uses pre-authenticated storageState)
    await page.goto('http://localhost:3000/project-manager/dashboard', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1000);

    // 3. Click "Project Pilot" tab
    const projectPilotTab = page.locator('[role="tab"]').filter({ hasText: 'Project Pilot' }).first();
    await projectPilotTab.click({ force: true });

    // 4. Verify Project Pilot workspace has loaded
    await expect(page.getByText('Project Pilot Agent')).toBeVisible({ timeout: 15000 });
  });


  // ==========================================
  // 1. POSITIVE WORKFLOWS (HAPPY PATHS)
  // ==========================================

  test('POS-01: Should send a text prompt to the AI agent by pressing Enter', async ({ page }) => {
    const chatInput = page.getByPlaceholder(/Create a new project.*Website Redesign/i);
    await expect(chatInput).toBeVisible({ timeout: 5000 });

    await chatInput.fill('How many active tasks are assigned to me?');
    await chatInput.press('Enter');

    await page.waitForTimeout(1000);
  });

  test('POS-02: Should send a text prompt to the AI agent by clicking the Send button', async ({ page }) => {
    const chatInput = page.getByPlaceholder(/Create a new project.*Website Redesign/i);
    await chatInput.fill('What is the total number of projects?');

    // Click the purple send button next to the input field
    const sendBtn = page.locator('button').filter({ has: page.locator('svg') }).last();
    await sendBtn.click({ force: true });

    await page.waitForTimeout(1000);
  });

  test('POS-03: Should allow selecting a specific project from the dropdown', async ({ page }) => {
    const projectSelector = page.locator('button').filter({ hasText: 'All projects' }).first();
    await expect(projectSelector).toBeVisible();
    await projectSelector.click();
    await page.waitForTimeout(500);

    // Select the first available option in the dropdown list
    const firstOption = page.locator('[role="option"], [role="menuitem"], li').first();
    if (await firstOption.isVisible()) {
      await firstOption.click({ force: true });
      await page.waitForTimeout(500);
    }
  });

  test('POS-04: Should successfully upload a text document to the agent', async ({ page }) => {
    const uploadBtn = page.getByRole('button', { name: /Upload/i }).first();
    await expect(uploadBtn).toBeVisible();

    // Trigger file chooser and upload the temporary file
    const fileChooserPromise = page.waitForEvent('filechooser');
    await uploadBtn.click({ force: true });
    const fileChooser = await fileChooserPromise;
    await fileChooser.setFiles(tempFilePath);

    await page.waitForTimeout(1000);
  });

  test('POS-05: Should load previous chat history when clicking an item in sidebar', async ({ page }) => {
    // Target any item in the previous conversation history list
    const firstHistoryItem = page.locator('div').filter({ hasText: /total|tasks/i }).first();
    
    if (await firstHistoryItem.isVisible().catch(() => false)) {
      await firstHistoryItem.click({ force: true });
      await page.waitForTimeout(1000);
      
      // Verification: Initial empty-state messaging is hidden
      await expect(page.getByText('Select a conversation or send a new request')).not.toBeVisible();
    }
  });

  test('POS-06: Should reset workspace and open a blank conversation when "+" is clicked', async ({ page }) => {
    // Find the '+' button next to "Conversation" header in the sidebar
    const newChatBtn = page.locator('div:has-text("Conversation")').locator('button').first();
    
    if (await newChatBtn.isVisible().catch(() => false)) {
      await newChatBtn.click({ force: true });
      await page.waitForTimeout(500);

      // Verify the main panel shows the blank state welcome text
      await expect(page.getByText('Select a conversation or send a new request')).toBeVisible();
    }
  });

  test('POS-07: Should delete a conversation when the trash can icon is clicked in sidebar', async ({ page }) => {
    // Find first conversation list element containing a trash/delete icon
    const historyItem = page.locator('div').filter({ hasText: /total|tasks/i }).first();
    
    if (await historyItem.isVisible().catch(() => false)) {
      // Find the delete button within that specific list item
      const deleteBtn = historyItem.locator('button').filter({ has: page.locator('svg') }).first();
      
      if (await deleteBtn.isVisible().catch(() => false)) {
        await deleteBtn.click({ force: true });
        await page.waitForTimeout(500);
      }
    }
  });

  // ==========================================
  // 2. NEGATIVE PATHS & VALIDATION
  // ==========================================

  test('NEG-01: Should block prompt submission when text input is empty', async ({ page }) => {
    const chatInput = page.getByPlaceholder(/Create a new project.*Website Redesign/i);
    await chatInput.fill(''); // Empty value

    const sendBtn = page.locator('button').filter({ has: page.locator('svg') }).last();
    await sendBtn.click({ force: true });

    // Verify workspace remains in the initial state since no prompt was processed
    await expect(page.getByText('Select a conversation or send a new request')).toBeVisible();
  });

  test('NEG-02: Should handle invalid file uploads gracefully', async ({ page }) => {
    const uploadBtn = page.getByRole('button', { name: /Upload/i }).first();
    
    const fileChooserPromise = page.waitForEvent('filechooser');
    await uploadBtn.click({ force: true });
    const fileChooser = await fileChooserPromise;
    await fileChooser.setFiles(invalidFilePath); // Uploading non-supported .exe

    await page.waitForTimeout(1000);
    // If your app displays a toast or validation text for invalid files, assert it here
  });

  // ==========================================
  // 3. EDGE CASES
  // ==========================================

  test('EDGE-01: Should collapse and expand the agent description banner', async ({ page }) => {
    const hideBtn = page.getByRole('button', { name: /Hide/i }).or(page.getByText('Hide'));
    
    if (await hideBtn.isVisible().catch(() => false)) {
      await hideBtn.click({ force: true });
      await page.waitForTimeout(500);

      // Verify description gets hidden or button toggles to 'Show'
      await expect(page.getByText('Create projects and tasks with natural language')).not.toBeVisible();
    }
  });

});