// tests/login.spec.js
const { test, expect } = require('@playwright/test');

test.describe('Company Login Module - Full Coverage', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto('http://localhost:3000/company/login', { waitUntil: 'domcontentloaded' });
  });

  // --- POSITIVE PATH ---
  test('POS-01: Should log in successfully with valid credentials', async ({ page }) => {
    await page.locator('#email').fill('af602773@gmail.com');      // Replace with valid email
    await page.locator('#password').fill('amina123'); // Replace with valid password

    const submitBtn = page.locator('button[type="submit"]');
    await expect(submitBtn).toBeEnabled();

    await Promise.all([
      page.waitForURL(/.*dashboard.*/, { timeout: 15000 }),
      submitBtn.click()
    ]);

    await expect(page).toHaveURL(/.*dashboard.*/);
  });

  // --- NEGATIVE PATHS ---
  test('NEG-01: Should fail to log in with incorrect password', async ({ page }) => {
    await page.locator('#email').fill('YOUR_REAL_LOCAL_EMAIL');
    await page.locator('#password').fill('WrongPassword123!');

    await page.locator('button[type="submit"]').click();
    await expect(page).toHaveURL('http://localhost:3000/company/login');
  });

  test('NEG-02: Should block form submission when fields are blank', async ({ page }) => {
    await page.locator('button[type="submit"]').click();
    await expect(page).toHaveURL('http://localhost:3000/company/login');
  });

  // --- EDGE CASES ---
  test('EDGE-01: Password field should toggle text visibility when eye icon is clicked', async ({ page }) => {
    const passwordInput = page.locator('#password');
    await passwordInput.fill('SecretPass123');

    await expect(passwordInput).toHaveAttribute('type', 'password');

    const eyeIconBtn = page.locator('button').filter({ has: page.locator('svg') }).first();
    if (await eyeIconBtn.isVisible()) {
      await eyeIconBtn.click();
      await expect(passwordInput).toHaveAttribute('type', 'text');
    }
  });

  test('EDGE-02: Should navigate to Forgot Password page when link is clicked', async ({ page }) => {
    await page.getByRole('button', { name: 'Forgot password?' }).click();
    await expect(page.getByRole('heading', { name: 'Reset Password' })).toBeVisible({ timeout: 10000 });
  });

  test('EDGE-03: Should navigate to Sign Up page when "Sign up" link is clicked', async ({ page }) => {
    // Robust locator using text match instead of strict role link
    await page.locator('text=Sign up').click();
    await expect(page).toHaveURL(/.*signup.*/);
  });

});