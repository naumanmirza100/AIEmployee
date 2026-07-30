// tests/forgotpassword.spec.js
const { test, expect } = require('@playwright/test');

test.describe('Forgot / Reset Password Module - Full Coverage', () => {

  test.beforeEach(async ({ page }) => {
    await page.goto('http://localhost:3000/company/login', { waitUntil: 'domcontentloaded' });
    
    // Click "Forgot password?" button to start the flow
    const forgotBtn = page.getByRole('button', { name: 'Forgot password?' });
    await forgotBtn.click();
  });

  // --- POSITIVE PATH: FULL 3-STEP FLOW ---
  test('POS-01: Should successfully complete the 3-step password reset flow', async ({ page }) => {
    // STEP 1: Enter email and send code
    const emailInput = page.locator('#resetEmail').or(page.getByPlaceholder('your@email.com'));
    await emailInput.fill('af602773@gmail.com'); // Replace with a real local email
    
    await page.getByRole('button', { name: 'Send Code' }).click();

    // Wait for Step 2 UI transition (checking for text)
    await expect(page.getByText(/Enter the 6-digit code/i)).toBeVisible({ timeout: 10000 });

    // STEP 2: Enter OTP / Verification Code (Ask dev for backend mock code if not 123456)
    const otpInput = page.locator('#otp').or(page.getByPlaceholder('1 2 3 4 5 6'));
    await otpInput.fill('123456'); 

    await page.getByRole('button', { name: 'Verify Code' }).click();

    // STEP 3: Enter New Password
    const newPasswordInput = page.locator('#newPassword').or(page.getByPlaceholder('At least 8 characters'));
    await expect(newPasswordInput).toBeVisible({ timeout: 10000 });
    await newPasswordInput.fill('NewSecurePassword123!');

    await page.getByRole('button', { name: 'Reset Password' }).click();

    // STEP 4: Verification - Verify it returns to Company Login screen
    await expect(page.getByRole('heading', { name: 'Company Login' })).toBeVisible({ timeout: 10000 });
  });

  // --- NEGATIVE PATHS ---
  test('NEG-01: Should block submission when email field is blank in Step 1', async ({ page }) => {
    await page.getByRole('button', { name: 'Send Code' }).click();

    // Verify user remains on Step 1 (OTP text does NOT appear)
    await expect(page.getByText(/Enter the 6-digit code/i)).not.toBeVisible();
  });

  test('NEG-02: Should fail verification when an invalid OTP is entered in Step 2', async ({ page }) => {
    // Step 1: Submit email
    const emailInput = page.locator('#resetEmail').or(page.getByPlaceholder('your@email.com'));
    await emailInput.fill('YOUR_REAL_LOCAL_EMAIL');
    await page.getByRole('button', { name: 'Send Code' }).click();

    // Wait for Step 2 text to appear before looking for OTP field
    await expect(page.getByText(/Enter the 6-digit code/i)).toBeVisible({ timeout: 10000 });

    // Step 2: Fill invalid OTP
    const otpInput = page.locator('#otp').or(page.getByPlaceholder('1 2 3 4 5 6'));
    await otpInput.fill('000000'); // Intentionally wrong OTP

    await page.getByRole('button', { name: 'Verify Code' }).click();

    // Verify user remains on Step 2 (New password field does NOT appear)
    await expect(page.locator('#newPassword')).not.toBeVisible();
  });

  // --- EDGE CASE: NAVIGATION ---
  test('EDGE-01: Should navigate back to Login screen when "Back to login" is clicked', async ({ page }) => {
    const backToLoginBtn = page.getByText('Back to login');
    await backToLoginBtn.click();

    await expect(page.getByRole('heading', { name: 'Company Login' })).toBeVisible();
  });

});