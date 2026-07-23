import React, { useEffect, useState } from 'react';
import { Helmet } from 'react-helmet';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useToast } from '@/components/ui/use-toast';
import { companyAuthService } from '@/services';
import { Building2, Loader2, LogIn, Eye, EyeOff, KeyRound, ArrowLeft, MailCheck, Check, AlertCircle } from 'lucide-react';

const SESSION_NOTICES = {
  expired: 'You were signed out because this account was logged out somewhere else. Please log in again.',
  inactive: 'This account is no longer active. Contact your administrator for access.',
};

const CompanyLoginPage = () => {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [searchParams, setSearchParams] = useSearchParams();

  // Set when an expired session bounced us here (?session=expired|inactive).
  const [sessionNotice, setSessionNotice] = useState(
    () => SESSION_NOTICES[searchParams.get('session')] || '',
  );

  // Drop the query param so a refresh doesn't keep replaying the notice.
  useEffect(() => {
    if (!searchParams.get('session')) return;
    const next = new URLSearchParams(searchParams);
    next.delete('session');
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);

  // 'login' or 'forgot'. Within 'forgot', step is 'email' | 'otp' | 'reset'.
  const [mode, setMode] = useState('login');
  const [forgotStep, setForgotStep] = useState('email');

  const [formData, setFormData] = useState({
    email: '',
    password: '',
  });
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  // Forgot-password flow state
  const [resetEmail, setResetEmail] = useState('');
  const [otp, setOtp] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [showNewPassword, setShowNewPassword] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();

    try {
      setLoading(true);
      const response = await companyAuthService.loginCompany(formData.email, formData.password);

      if (response.status === 'success') {
        if (response.data.user) {
          localStorage.setItem('company_user', JSON.stringify(response.data.user));
        }

        toast({
          title: 'Welcome back!',
          description: `Logged in as ${response.data.user.fullName}`,
        });

        navigate('/company/dashboard');
      }
    } catch (error) {
      toast({
        title: 'Login Failed',
        description: error.message || 'Invalid email or password',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  // Step 1: request OTP
  const handleRequestOtp = async (e) => {
    e.preventDefault();
    try {
      setLoading(true);
      const res = await companyAuthService.requestPasswordReset(resetEmail);
      toast({
        title: 'Check your email',
        description: res.message || 'If an account exists, a verification code has been sent.',
      });
      setForgotStep('otp');
    } catch (error) {
      toast({
        title: 'Error',
        description: error.message || 'Failed to send verification code',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  // Step 2: verify OTP
  const handleVerifyOtp = async (e) => {
    e.preventDefault();
    try {
      setLoading(true);
      await companyAuthService.verifyResetOtp(resetEmail, otp.trim());
      toast({ title: 'Code verified', description: 'Now set your new password.' });
      setForgotStep('reset');
    } catch (error) {
      toast({
        title: 'Invalid code',
        description: error.message || 'The code is invalid or expired',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  // Step 3: reset password
  const handleResetPassword = async (e) => {
    e.preventDefault();
    if (newPassword.length < 8) {
      toast({
        title: 'Weak password',
        description: 'Password must be at least 8 characters long',
        variant: 'destructive',
      });
      return;
    }
    try {
      setLoading(true);
      await companyAuthService.resetPassword(resetEmail, otp.trim(), newPassword);
      toast({
        title: 'Password reset',
        description: 'You can now log in with your new password.',
      });
      // Return to login, prefill the email.
      setFormData({ email: resetEmail, password: '' });
      backToLogin();
    } catch (error) {
      toast({
        title: 'Error',
        description: error.message || 'Failed to reset password',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  const openForgot = () => {
    setResetEmail(formData.email || '');
    setOtp('');
    setNewPassword('');
    setForgotStep('email');
    setMode('forgot');
  };

  const backToLogin = () => {
    setMode('login');
    setForgotStep('email');
    setOtp('');
    setNewPassword('');
  };

  const renderLogin = () => (
    <>
      <CardHeader className="text-center">
        <Building2 className="h-12 w-12 mx-auto text-primary mb-4" />
        <CardTitle>Company Login</CardTitle>
        <CardDescription>
          Sign in to manage your job postings and applications
        </CardDescription>
      </CardHeader>
      <CardContent>
        {sessionNotice && (
          <div className="mb-4 flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 p-3">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
            <p className="text-sm text-amber-200">{sessionNotice}</p>
          </div>
        )}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="email">Email Address</Label>
            <Input
              id="email"
              type="email"
              value={formData.email}
              onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              required
              placeholder="your@email.com"
            />
          </div>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label htmlFor="password">Password</Label>
              <button
                type="button"
                onClick={openForgot}
                className="text-xs font-medium text-primary hover:underline"
              >
                Forgot password?
              </button>
            </div>
            <div className="relative">
              <Input
                id="password"
                type={showPassword ? 'text' : 'password'}
                value={formData.password}
                onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                required
                placeholder="Enter your password"
                className="pr-10"
              />
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                tabIndex={-1}
              >
                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>
          <Button type="submit" className="w-full" disabled={loading}>
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Signing in...
              </>
            ) : (
              <>
                <LogIn className="h-4 w-4 mr-2" />
                Sign In
              </>
            )}
          </Button>
        </form>

        <div className="mt-4 text-center text-sm text-muted-foreground">
          Don't have an account?{' '}
          <button
            type="button"
            onClick={() => navigate('/company/signup')}
            className="font-medium text-primary hover:underline"
          >
            Sign up
          </button>
        </div>
      </CardContent>
    </>
  );

  // 1 → 2 → 3 progress indicator for the reset flow.
  const renderStepper = () => {
    const steps = [
      { key: 'email', label: 'Email' },
      { key: 'otp', label: 'Verify' },
      { key: 'reset', label: 'Password' },
    ];
    const currentIndex = steps.findIndex((s) => s.key === forgotStep);

    return (
      <div className="flex items-center justify-center gap-1 mt-4">
        {steps.map((step, index) => {
          const isComplete = index < currentIndex;
          const isActive = index === currentIndex;
          return (
            <React.Fragment key={step.key}>
              <div className="flex flex-col items-center gap-1">
                <div
                  className={
                    'flex h-8 w-8 items-center justify-center rounded-full text-sm font-semibold transition-colors ' +
                    (isComplete
                      ? 'bg-primary text-primary-foreground'
                      : isActive
                      ? 'bg-primary text-primary-foreground ring-4 ring-primary/20'
                      : 'bg-muted text-muted-foreground')
                  }
                >
                  {isComplete ? <Check className="h-4 w-4" /> : index + 1}
                </div>
                <span
                  className={
                    'text-[11px] font-medium ' +
                    (isActive || isComplete ? 'text-foreground' : 'text-muted-foreground')
                  }
                >
                  {step.label}
                </span>
              </div>
              {index < steps.length - 1 && (
                <div
                  className={
                    'h-0.5 w-8 sm:w-12 mb-4 rounded transition-colors ' +
                    (index < currentIndex ? 'bg-primary' : 'bg-muted')
                  }
                />
              )}
            </React.Fragment>
          );
        })}
      </div>
    );
  };

  const renderForgot = () => (
    <>
      <CardHeader className="text-center">
        <KeyRound className="h-12 w-12 mx-auto text-primary mb-4" />
        <CardTitle>Reset Password</CardTitle>
        {renderStepper()}
        <CardDescription className="pt-2">
          {forgotStep === 'email' && 'Enter your account email to receive a verification code.'}
          {forgotStep === 'otp' && `Enter the 6-digit code we sent to ${resetEmail}.`}
          {forgotStep === 'reset' && 'Choose a new password for your account.'}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {forgotStep === 'email' && (
          <form onSubmit={handleRequestOtp} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="resetEmail">Email Address</Label>
              <Input
                id="resetEmail"
                type="email"
                value={resetEmail}
                onChange={(e) => setResetEmail(e.target.value)}
                required
                placeholder="your@email.com"
              />
            </div>
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? (
                <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Sending code...</>
              ) : (
                <><MailCheck className="h-4 w-4 mr-2" />Send Code</>
              )}
            </Button>
          </form>
        )}

        {forgotStep === 'otp' && (
          <form onSubmit={handleVerifyOtp} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="otp">Verification Code</Label>
              <Input
                id="otp"
                inputMode="numeric"
                maxLength={6}
                value={otp}
                onChange={(e) => setOtp(e.target.value.replace(/\D/g, ''))}
                required
                placeholder="123456"
                className="tracking-[0.5em] text-center text-lg"
              />
            </div>
            <Button type="submit" className="w-full" disabled={loading || otp.length !== 6}>
              {loading ? (
                <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Verifying...</>
              ) : (
                'Verify Code'
              )}
            </Button>
            <button
              type="button"
              onClick={handleRequestOtp}
              disabled={loading}
              className="w-full text-xs text-muted-foreground hover:text-primary"
            >
              Didn't get it? Resend code
            </button>
          </form>
        )}

        {forgotStep === 'reset' && (
          <form onSubmit={handleResetPassword} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="newPassword">New Password</Label>
              <div className="relative">
                <Input
                  id="newPassword"
                  type={showNewPassword ? 'text' : 'password'}
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  required
                  placeholder="At least 8 characters"
                  className="pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowNewPassword((v) => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  tabIndex={-1}
                >
                  {showNewPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? (
                <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Resetting...</>
              ) : (
                'Reset Password'
              )}
            </Button>
          </form>
        )}

        <button
          type="button"
          onClick={backToLogin}
          className="mt-4 flex items-center justify-center gap-1 w-full text-sm text-muted-foreground hover:text-primary"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to login
        </button>
      </CardContent>
    </>
  );

  return (
    <>
      <Helmet>
        <title>Company Login | Pay Per Project</title>
      </Helmet>
      <div className="min-h-screen bg-background flex items-center justify-center p-4">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="w-full max-w-md"
        >
          <Card>
            {mode === 'login' ? renderLogin() : renderForgot()}
          </Card>
        </motion.div>
      </div>
    </>
  );
};

export default CompanyLoginPage;
