// Company → Billing → "Update card".
//
// Card entry happens here rather than on Stripe's hosted portal. The PAN is still
// never ours: <PaymentElement> is an iframe served from Stripe's own origin, so the
// number never enters this app's DOM or reaches our servers and the integration
// stays PCI SAQ A — the same tier as redirecting out. What we gain is that the
// customer never leaves the product to change a card.
//
// Flow: POST /modules/setup-intent → confirmSetup in the iframe → POST
// /modules/payment-method to promote the new card to default. That last call is not
// optional: Stripe attaches the card during confirmSetup but points nothing at it,
// so skipping it would leave every running subscription on the old card.

import React, { useMemo, useState } from 'react';
import { loadStripe } from '@stripe/stripe-js';
import {
  Elements, PaymentElement, useStripe, useElements,
} from '@stripe/react-stripe-js';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { useToast } from '@/components/ui/use-toast';
import { Loader2, Lock, AlertTriangle } from 'lucide-react';
import ErrorBoundary from '@/components/common/ErrorBoundary';
import { createSetupIntent, setDefaultPaymentMethod } from '@/services/modulePurchaseService';

// loadStripe must not run per render — each call re-fetches Stripe.js. Cache by key
// so a test→live key swap still produces a fresh instance.
//
// The catch matters: a cached REJECTED promise would poison every later attempt for
// the life of the page, so one blocked request (offline, ad-blocker, bad key) would
// mean the dialog never works again until a reload. Drop the entry instead and
// resolve to null, which the dialog renders as an explicit failure state.
const stripeCache = new Map();
const getStripe = (publishableKey) => {
  if (!publishableKey) return null;
  if (!stripeCache.has(publishableKey)) {
    stripeCache.set(
      publishableKey,
      loadStripe(publishableKey).catch((err) => {
        stripeCache.delete(publishableKey);
        console.error('Stripe.js failed to load:', err);
        return null;
      }),
    );
  }
  return stripeCache.get(publishableKey);
};

// The dashboard shell is dark (#120d22); Elements defaults to a light theme and
// would otherwise render as a white slab inside the modal.
const APPEARANCE = {
  theme: 'night',
  variables: {
    colorPrimary: '#7c3aed',
    colorBackground: '#1a1430',
    colorText: '#e9e6f5',
    colorDanger: '#f87171',
    borderRadius: '8px',
    fontSizeBase: '14px',
  },
};

/** Inner form — must be a child of <Elements> to reach the Stripe hooks. */
const CardForm = ({ hasExistingCard, onDone, onCancel }) => {
  const stripe = useStripe();
  const elements = useElements();
  const { toast } = useToast();
  const [submitting, setSubmitting] = useState(false);
  const [ready, setReady] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!stripe || !elements || submitting) return;

    setSubmitting(true);
    try {
      // redirect: 'if_required' keeps non-3DS cards — the majority — inside the
      // modal. Only a card whose issuer demands SCA leaves the page, and it comes
      // back to return_url where BillingOverview finishes the promotion step.
      const { error, setupIntent } = await stripe.confirmSetup({
        elements,
        confirmParams: {
          return_url: `${window.location.origin}/company/dashboard/billing`,
        },
        redirect: 'if_required',
      });

      if (error) {
        toast({
          title: 'Card not saved',
          description: error.message || 'Please check the details and try again.',
          variant: 'destructive',
        });
        return;
      }

      // Anything other than success is a state the customer cannot act on from the
      // status code, so log the detail and show them a plain retry message.
      if (setupIntent?.status !== 'succeeded') {
        console.warn('SetupIntent ended in status:', setupIntent?.status);
        toast({
          title: 'Card not saved',
          description: 'Please try again.',
          variant: 'destructive',
        });
        return;
      }

      await setDefaultPaymentMethod(setupIntent.payment_method);
      toast({
        title: hasExistingCard ? 'Card updated' : 'Card saved',
        description: 'Future charges will use this card.',
      });
      onDone();
    } catch (err) {
      console.error('Failed to save card:', err);
      toast({
        title: 'Card not saved',
        description: 'Something went wrong. Please try again.',
        variant: 'destructive',
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {/* layout must be one of 'tabs' | 'accordion' | 'auto'. Anything else makes
          Stripe.js throw an IntegrationError while the element mounts, which — with
          no error boundary above this route — used to unmount the whole app. */}
      <PaymentElement onReady={() => setReady(true)} options={{ layout: 'tabs' }} />

      {!ready && (
        <div className="flex items-center justify-center py-6">
          <Loader2 className="h-5 w-5 animate-spin text-primary" />
        </div>
      )}

      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Lock className="h-3 w-3 shrink-0" />
        Card details go directly to Stripe and are never stored on our servers.
      </p>

      <div className="flex justify-end gap-2 pt-1">
        <Button type="button" variant="ghost" onClick={onCancel} disabled={submitting}>
          Cancel
        </Button>
        <Button type="submit" disabled={!stripe || !ready || submitting}>
          {submitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
          {hasExistingCard ? 'Update card' : 'Save card'}
        </Button>
      </div>
    </form>
  );
};

const UpdateCardDialog = ({ open, onOpenChange, publishableKey, hasExistingCard, onSuccess }) => {
  const { toast } = useToast();
  const [clientSecret, setClientSecret] = useState(null);
  const [loading, setLoading] = useState(false);
  const [stripeFailed, setStripeFailed] = useState(false);

  const stripePromise = useMemo(() => getStripe(publishableKey), [publishableKey]);

  // getStripe resolves to null when Stripe.js could not be fetched. Without this
  // check useStripe() just stays null, leaving the submit button disabled forever
  // with no explanation — so surface it as a real state instead.
  React.useEffect(() => {
    if (!stripePromise) return undefined;
    let cancelled = false;
    stripePromise.then((s) => { if (!cancelled) setStripeFailed(!s); });
    return () => { cancelled = true; };
  }, [stripePromise]);

  // Mint a fresh SetupIntent each time the dialog opens. Reusing one across opens
  // risks confirming an intent the customer already abandoned.
  React.useEffect(() => {
    if (!open) {
      setClientSecret(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    createSetupIntent()
      .then((res) => {
        if (cancelled) return;
        if (res?.client_secret) {
          setClientSecret(res.client_secret);
        } else {
          console.error('No client_secret in setup-intent response:', res);
          toast({
            title: 'Could not open the card form',
            description: 'Please try again.',
            variant: 'destructive',
          });
          onOpenChange(false);
        }
      })
      .catch((err) => {
        if (cancelled) return;
        console.error('setup-intent request failed:', err);
        toast({
          title: 'Could not open the card form',
          description: 'Please try again.',
          variant: 'destructive',
        });
        onOpenChange(false);
      })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [open, toast, onOpenChange]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {/* The card form grows when Stripe offers extra methods or shows a bank-redirect
          notice, so cap the height and scroll inside rather than letting the dialog
          run off the top and bottom of short viewports. */}
      <DialogContent className="sm:max-w-[480px] max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{hasExistingCard ? 'Update payment method' : 'Add payment method'}</DialogTitle>
          <DialogDescription>
            This card will be used for every agent subscription on this account.
          </DialogDescription>
        </DialogHeader>

        {stripeFailed ? (
          <div className="py-8 text-center space-y-3">
            <AlertTriangle className="h-8 w-8 mx-auto text-amber-400" />
            <p className="text-sm font-medium">The card form couldn&apos;t load</p>
            <p className="text-xs text-muted-foreground">
              This is usually caused by an ad-blocker or a browser privacy extension.
              Try disabling it for this site, or use the billing link at the bottom of
              the page to update your card instead.
            </p>
            <Button size="sm" variant="outline" onClick={() => onOpenChange(false)}>Close</Button>
          </div>
        ) : loading || !clientSecret || !stripePromise ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-primary" />
          </div>
        ) : (
          // Contain Stripe failures. This route sits outside every ErrorBoundary in
          // the app and there is no global one, so an uncaught throw here unmounts
          // the whole React root — and an empty root paints as a black page,
          // because index.css applies bg-background (3.9% lightness) to <body>.
          <ErrorBoundary>
            <Elements stripe={stripePromise} options={{ clientSecret, appearance: APPEARANCE }}>
              <CardForm
                hasExistingCard={hasExistingCard}
                onDone={() => { onOpenChange(false); onSuccess?.(); }}
                onCancel={() => onOpenChange(false)}
              />
            </Elements>
          </ErrorBoundary>
        )}
      </DialogContent>
    </Dialog>
  );
};

export default UpdateCardDialog;
