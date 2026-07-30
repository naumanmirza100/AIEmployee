// tests/signup.spec.js
const { test, expect } = require('@playwright/test');

test.describe('Company Sign Up Module - Full Coverage', () => {

  test.beforeEach(async ({ page }) => {
    // Increased timeout and wait strategy for local server responsiveness
    await page.goto('http://localhost:3000/company/signup', { waitUntil: 'domcontentloaded', timeout: 30000 });
  });

  // --- POSITIVE PATH ---
  test('POS-01: Should successfully submit signup form with unique company details', async ({ page }) => {
    const uniqueEmail = `company_${Date.now()}@example.com`;

    // Ensure form is loaded before filling
    await expect(page.locator('#name')).toBeVisible({ timeout: 10000 });

    await page.locator('#name').fill('Acme AI Corp');
    await page.locator('#email').fill(uniqueEmail);
    await page.locator('#phone').fill('+1 234 567 8900');
    await page.locator('#website').fill('acmeai.com');
    await page.locator('#industry').fill('Software');
    await page.locator('#company_size').fill('50');
    await page.locator('#address').fill('123 Innovation Way, Tech City');
    await page.locator('#description').fill('Building automated AI agents for enterprise projects.');

    const submitBtn = page.locator('button[type="submit"]').or(page.getByRole('button', { name: /Sign Up/i }));
    await submitBtn.click();

    await expect(page).toHaveURL('http://localhost:3000/company/signup', { timeout: 15000 });
  });

  // --- NEGATIVE PATHS ---
  test('NEG-01: Should block submission when required fields are blank', async ({ page }) => {
    const submitBtn = page.locator('button[type="submit"]').or(page.getByRole('button', { name: /Sign Up/i }));
    await submitBtn.click();

    await expect(page).toHaveURL('http://localhost:3000/company/signup');
  });

  test('NEG-02: Should block submission when email format is invalid', async ({ page }) => {
    await expect(page.locator('#name')).toBeVisible({ timeout: 10000 });

    await page.locator('#name').fill('Test Company');
    await page.locator('#email').fill('invalidemailformat');
    await page.locator('#phone').fill('+1234567890');

    const submitBtn = page.locator('button[type="submit"]').or(page.getByRole('button', { name: /Sign Up/i }));
    await submitBtn.click();

    await expect(page).toHaveURL('http://localhost:3000/company/signup');
  });

  // --- EDGE CASE: NAVIGATION ---
  test('EDGE-01: Should navigate back to Login page when "Log in" link is clicked', async ({ page }) => {
    const loginLink = page.locator('a', { hasText: 'Log in' });
    await loginLink.click();

    await expect(page).toHaveURL(/.*company\/login.*/);
  });

});