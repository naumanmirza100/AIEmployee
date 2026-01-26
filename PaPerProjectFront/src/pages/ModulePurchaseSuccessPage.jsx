import React, { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { CheckCircle2, Home, LayoutDashboard, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { getCompanyUser } from '@/services/companyAuthService';
import { verifySession } from '@/services/modulePurchaseService';

const ModulePurchaseSuccessPage = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const sessionId = searchParams.get('session_id');
  const [verifying, setVerifying] = useState(!!sessionId);
  const [verified, setVerified] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    localStorage.removeItem('company_purchased_modules');
  }, []);

  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    (async () => {
      try {
        await verifySession(sessionId);
        if (!cancelled) {
          setVerified(true);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) {
          setError(e?.message || 'Could not verify payment.');
          setVerified(false);
        }
      } finally {
        if (!cancelled) setVerifying(false);
      }
    })();
    return () => { cancelled = true; };
  }, [sessionId]);

  const isCompanyUser = !!getCompanyUser();

  if (verifying) {
    return (
      <div className="min-h-[60vh] flex flex-col items-center justify-center px-4 py-16">
        <Loader2 className="h-12 w-12 animate-spin text-primary mb-4" />
        <p className="text-muted-foreground">Activating your module…</p>
      </div>
    );
  }

  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center px-4 py-16">
      <div className="max-w-md w-full text-center space-y-6">
        <div className="inline-flex items-center justify-center w-20 h-20 rounded-full bg-green-100 dark:bg-green-900/30">
          <CheckCircle2 className="h-12 w-12 text-green-600 dark:text-green-400" />
        </div>
        <div>
          <h1 className="text-2xl md:text-3xl font-bold text-foreground mb-2">
            Payment successful
          </h1>
          <p className="text-muted-foreground">
            {error
              ? 'Your payment was received. We could not activate your module automatically—please go to your dashboard or contact support.'
              : 'Your module has been activated. You can access it from your dashboard.'}
          </p>
          {error && (
            <p className="mt-2 text-sm text-amber-600 dark:text-amber-400">{error}</p>
          )}
        </div>
        {sessionId && !error && (
          <p className="text-xs text-muted-foreground font-mono">
            Session: {sessionId.slice(0, 20)}…
          </p>
        )}
        <div className="flex flex-col sm:flex-row gap-3 justify-center pt-4">
          {isCompanyUser && (
            <Button
              onClick={() => navigate('/company/dashboard')}
              className="gap-2"
              size="lg"
            >
              <LayoutDashboard className="h-4 w-4" />
              Go to Dashboard
            </Button>
          )}
          <Button
            variant={isCompanyUser ? 'outline' : 'default'}
            onClick={() => navigate('/')}
            className="gap-2"
            size="lg"
          >
            <Home className="h-4 w-4" />
            Back to Home
          </Button>
        </div>
      </div>
    </div>
  );
};

export default ModulePurchaseSuccessPage;
