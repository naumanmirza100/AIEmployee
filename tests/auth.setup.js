// tests/auth.setup.js
const { test: setup, expect } = require('@playwright/test');

const authFile = 'playwright/.auth/user.json';

setup('authenticate user once', async ({ page }) => {
  // 1. Perform login
  await page.goto('http://localhost:3000/company/login', { waitUntil: 'domcontentloaded' });
  await page.locator('#email').fill('af602773@gmail.com');
  await page.locator('#password').fill('amina123');
  await page.locator('button[type="submit"]').click();

  // 2. Wait for dashboard redirect to confirm session is saved
  await expect(page).toHaveURL(/.*dashboard.*/, { timeout: 15000 });

  // 3. Save logged-in browser state (cookies & localStorage) to JSON file
  await page.context().storageState({ path: authFile });
});