// tests/agents/PM_Agent/knowledgeQA.spec.js
const { test, expect } = require('@playwright/test');
const { setupDOMSweeper } = require('../../helper/auth.js');

test.describe('Project Manager Agent - Knowledge Q&A Module', () => {

  test.beforeEach(async ({ page }) => {
    await setupDOMSweeper(page);

    await page.goto('http://localhost:3000/project-manager/dashboard', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1000);

    const qaTab = page.locator('[role="tab"]').filter({ hasText: 'Knowledge Q&A' }).first();
    await qaTab.click({ force: true });

    await expect(page.getByText('Knowledge Q&A Agent')).toBeVisible({ timeout: 15000 });
  });

  // --- POSITIVE PATHS ---
  test('POS-01: Should send a text prompt to the Q&A agent', async ({ page }) => {
    const chatInput = page.getByPlaceholder(/Ask about projects, tasks, deadlines/i);
    await expect(chatInput).toBeVisible();

    await chatInput.fill('What is the deadline for the "Website Redesign" project?');

    const sendBtn = page.locator('button').filter({ has: page.locator('svg') }).last();
    await sendBtn.click({ force: true });

    await page.waitForTimeout(1000);
  });

  test('POS-02: Should interact with sidebar conversation history', async ({ page }) => {
    // 1. Click on a specific historical conversation item
    const firstHistoryItem = page.getByText('What is due this week?').first();
    
    if (await firstHistoryItem.isVisible().catch(() => false)) {
      await firstHistoryItem.click({ force: true });
      
      // 2. Wait for loading to clear the empty state welcome text (timeout: 10000ms)
      await expect(page.getByText('Select a conversation or ask a new question')).not.toBeVisible({ timeout: 10000 });
    }
  });

  test('POS-03: Should interact with sidebar "+" new conversation button', async ({ page }) => {
    // Click '+' button to create a new conversation
    const newChatBtn = page.locator('div:has-text("Conversation")').locator('button').first();
    if (await newChatBtn.isVisible()) {
      await newChatBtn.click({ force: true });
      await page.waitForTimeout(500);
    }
    
    // Verify blank conversation welcome state is visible
    await expect(page.getByText('Select a conversation or ask a new question')).toBeVisible();
  });

});