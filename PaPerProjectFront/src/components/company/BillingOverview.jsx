// Company → Billing.
//
// The single billing surface for a company. Everything here is read live from
// Stripe via /modules/billing-overview, so the figures match the customer's real
// billing state rather than whatever our webhook mirror last heard about.
//
// Card entry is in-app too, via Stripe Elements (see UpdateCardDialog). The PAN
// never touches our DOM — Elements is an iframe on Stripe's origin — so this stays
// PCI SAQ A. The hosted portal survives only as a secondary link for what we do not
// reimplement: billing address, tax IDs and the full receipt archive.

import React, { useState, useEffect, useCallback } from 'react';
import { loadStripe } from '@stripe/stripe-js';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/components/ui/use-toast';
import {
  CreditCard, Loader2, Download, ExternalLink, AlertTriangle, RefreshCw,
  Receipt, CalendarClock,
} from 'lucide-react';
import {
  getBillingOverview, createBillingPortal, setDefaultPaymentMethod,
} from '@/services/modulePurchaseService';
import UpdateCardDialog from './UpdateCardDialog';

const fmtDate = (iso) => {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      day: 'numeric', month: 'short', year: 'numeric',
    });
  } catch {
    return '—';
  }
};

const fmtMoney = (amount, currency = 'USD') => {
  if (amount === null || amount === undefined) return '—';
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(amount);
  } catch {
    return `$${Number(amount).toFixed(2)}`;
  }
};

// Stripe's vocabulary, mapped to something a customer can act on.
const STATUS_STYLE = {
  active: { label: 'Active', cls: 'bg-green-500/15 text-green-400 border-green-500/30' },
  trialing: { label: 'Trial', cls: 'bg-blue-500/15 text-blue-400 border-blue-500/30' },
  past_due: { label: 'Payment failed', cls: 'bg-red-500/15 text-red-400 border-red-500/30' },
  unpaid: { label: 'Unpaid', cls: 'bg-red-500/15 text-red-400 border-red-500/30' },
  incomplete: { label: 'Awaiting payment', cls: 'bg-amber-500/15 text-amber-400 border-amber-500/30' },
  incomplete_expired: { label: 'Expired', cls: 'bg-muted text-muted-foreground border-border' },
  canceled: { label: 'Cancelled', cls: 'bg-muted text-muted-foreground border-border' },
  paused: { label: 'Paused', cls: 'bg-amber-500/15 text-amber-400 border-amber-500/30' },
};

const INVOICE_STYLE = {
  paid: 'bg-green-500/15 text-green-400 border-green-500/30',
  open: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  void: 'bg-muted text-muted-foreground border-border',
  uncollectible: 'bg-red-500/15 text-red-400 border-red-500/30',
  draft: 'bg-muted text-muted-foreground border-border',
};

const BillingOverview = () => {
  const { toast } = useToast();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [portalLoading, setPortalLoading] = useState(false);
  const [cardDialogOpen, setCardDialogOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getBillingOverview();
      setData(res?.status === 'success' ? res : null);
    } catch (err) {
      console.error('Failed to load billing overview:', err);
      toast({
        title: 'Could not load billing',
        description: 'Please try again.',
        variant: 'destructive',
      });
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => { load(); }, [load]);

  // 3DS return path. When confirmSetup could not stay in-page it sent the customer
  // to the issuer and Stripe bounced them back here with the intent in the query
  // string. The card is attached at this point but still points at nothing, so the
  // promotion step that CardForm would have run has to be finished here instead —
  // otherwise a 3DS card silently never becomes the default.
  const publishableKey = data?.publishable_key;
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const secret = params.get('setup_intent_client_secret');
    if (!secret || !publishableKey) return;

    // Clear immediately so a refresh (or a re-render) cannot re-fire this.
    params.delete('setup_intent_client_secret');
    params.delete('setup_intent');
    params.delete('redirect_status');
    const qs = params.toString();
    window.history.replaceState({}, '', window.location.pathname + (qs ? `?${qs}` : ''));

    let cancelled = false;
    (async () => {
      try {
        const stripe = await loadStripe(publishableKey);
        const { setupIntent, error } = await stripe.retrieveSetupIntent(secret);
        if (cancelled) return;
        if (error || setupIntent?.status !== 'succeeded') {
          toast({
            title: 'Card not saved',
            description: error?.message || 'The card could not be confirmed. Please try again.',
            variant: 'destructive',
          });
          return;
        }
        await setDefaultPaymentMethod(setupIntent.payment_method);
        if (cancelled) return;
        toast({ title: 'Card updated', description: 'Future charges will use this card.' });
        load();
      } catch (err) {
        if (!cancelled) {
          toast({
            title: 'Card not saved',
            description: err?.message || 'Please try again.',
            variant: 'destructive',
          });
        }
      }
    })();

    return () => { cancelled = true; };
  }, [publishableKey, toast, load]);

  const openPortal = async () => {
    setPortalLoading(true);
    try {
      const res = await createBillingPortal();
      if (res?.url) {
        window.location.href = res.url;
        return;
      }
      console.error('No portal URL in response:', res);
      toast({
        title: 'Could not open billing details',
        description: 'Please try again.',
        variant: 'destructive',
      });
    } catch (err) {
      console.error('Failed to create billing portal session:', err);
      toast({
        title: 'Could not open billing details',
        description: 'Please try again.',
        variant: 'destructive',
      });
    } finally {
      setPortalLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  // Nothing bought yet. A card can still be saved ahead of the first purchase —
  // create_setup_intent mints the Stripe customer on demand — so keep "Add card"
  // reachable and only fall back to a dead end when there is no key to run it with.
  if (!data || !data.has_billing) {
    return (
      <>
        <Card>
          <CardContent className="py-12 text-center">
            <CreditCard className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
            <p className="text-lg font-medium">No billing history yet</p>
            <p className="text-sm text-muted-foreground mt-2">
              Subscribe to an agent and your invoices and payment details will appear here.
            </p>
            {data?.publishable_key && (
              <Button className="mt-5" onClick={() => setCardDialogOpen(true)}>
                <CreditCard className="h-4 w-4 mr-2" />
                Add card
              </Button>
            )}
          </CardContent>
        </Card>

        {data?.publishable_key && (
          <UpdateCardDialog
            open={cardDialogOpen}
            onOpenChange={setCardDialogOpen}
            publishableKey={data.publishable_key}
            hasExistingCard={false}
            onSuccess={load}
          />
        )}
      </>
    );
  }

  const {
    subscriptions = [], invoices = [], payment_method: pm, live,
    publishable_key: pubKey,
  } = data;

  return (
    <div className="space-y-4">
      {live === false && (
        <div className="flex items-start gap-2 p-3 rounded-lg bg-amber-500/10 border border-amber-500/20">
          <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
          <p className="text-sm text-amber-300">
            Some details below may be out of date. Refresh in a moment to see the latest.
          </p>
        </div>
      )}

      {/* Payment method */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div>
              <CardTitle className="text-base flex items-center gap-2">
                <CreditCard className="h-4 w-4 text-primary" /> Payment method
              </CardTitle>
              <CardDescription className="mt-1">
                Used for every agent subscription on this account.
              </CardDescription>
            </div>
            {/* No publishable key configured → fall back to the hosted portal
                rather than opening a dialog that cannot mount Elements. */}
            <Button
              size="sm"
              variant="outline"
              onClick={() => (pubKey ? setCardDialogOpen(true) : openPortal())}
              disabled={!pubKey && portalLoading}
            >
              {!pubKey && portalLoading
                ? <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                : <CreditCard className="h-4 w-4 mr-2" />}
              {pm ? 'Update card' : 'Add card'}
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {pm ? (
            <div className="flex items-center gap-3">
              <div className="px-2.5 py-1 rounded border bg-muted/40 text-sm font-medium">
                {pm.brand || 'Card'}
              </div>
              <span className="text-sm font-mono">•••• {pm.last4}</span>
              <span className="text-sm text-muted-foreground">
                expires {String(pm.exp_month).padStart(2, '0')}/{pm.exp_year}
              </span>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No card on file.</p>
          )}
        </CardContent>
      </Card>

      {/* Subscriptions */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <CalendarClock className="h-4 w-4 text-primary" /> Subscriptions
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {subscriptions.length === 0 ? (
            <p className="text-sm text-muted-foreground">No subscriptions.</p>
          ) : subscriptions.map((s) => {
            const style = STATUS_STYLE[s.stripe_status]
              || { label: s.stripe_status, cls: 'bg-muted text-muted-foreground border-border' };
            return (
              <div
                key={s.stripe_subscription_id}
                className="border rounded-lg p-3 flex items-start justify-between gap-3 flex-wrap"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-sm">{s.module_display_name}</span>
                    <Badge variant="outline" className={`text-xs ${style.cls}`}>
                      {style.label}
                    </Badge>
                    {s.cancel_at_period_end && (
                      <Badge variant="outline" className="text-xs bg-orange-500/15 text-orange-300 border-orange-500/30">
                        Cancels at period end
                      </Badge>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">
                    {fmtMoney(s.amount, s.currency)}
                    {s.billing_interval ? ` / ${s.billing_interval}` : ''}
                    {s.current_period_end && (
                      <>
                        {' · '}
                        {s.cancel_at_period_end || ['canceled', 'incomplete_expired'].includes(s.stripe_status)
                          ? `Ends ${fmtDate(s.current_period_end)}`
                          : `Renews ${fmtDate(s.current_period_end)}`}
                      </>
                    )}
                  </p>
                </div>
              </div>
            );
          })}
        </CardContent>
      </Card>

      {/* Invoices */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between gap-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Receipt className="h-4 w-4 text-primary" /> Invoices
            </CardTitle>
            <Button size="sm" variant="ghost" onClick={load} title="Refresh from Stripe">
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {invoices.length === 0 ? (
            <p className="text-sm text-muted-foreground">No invoices yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-muted-foreground border-b">
                    <th className="py-2 pr-3 font-medium">Invoice</th>
                    <th className="py-2 pr-3 font-medium">Date</th>
                    <th className="py-2 pr-3 font-medium">Amount</th>
                    <th className="py-2 pr-3 font-medium">Status</th>
                    <th className="py-2 font-medium sr-only">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {invoices.map((inv) => (
                    <tr key={inv.id} className="border-b last:border-0">
                      <td className="py-2 pr-3 font-mono text-xs">{inv.number || inv.id}</td>
                      <td className="py-2 pr-3 whitespace-nowrap">{fmtDate(inv.created)}</td>
                      <td className="py-2 pr-3 whitespace-nowrap">
                        {fmtMoney(
                          inv.status === 'paid' ? inv.amount_paid : inv.amount_due,
                          inv.currency,
                        )}
                      </td>
                      <td className="py-2 pr-3">
                        <Badge
                          variant="outline"
                          className={`text-xs ${INVOICE_STYLE[inv.status] || INVOICE_STYLE.draft}`}
                        >
                          {inv.status}
                        </Badge>
                      </td>
                      <td className="py-2">
                        <div className="flex items-center gap-1 justify-end">
                          {inv.hosted_invoice_url && (
                            <Button size="sm" variant="ghost" asChild>
                              <a href={inv.hosted_invoice_url} target="_blank" rel="noopener noreferrer" title="View invoice">
                                <ExternalLink className="h-3.5 w-3.5" />
                              </a>
                            </Button>
                          )}
                          {inv.invoice_pdf && (
                            <Button size="sm" variant="ghost" asChild>
                              <a href={inv.invoice_pdf} target="_blank" rel="noopener noreferrer" title="Download PDF">
                                <Download className="h-3.5 w-3.5" />
                              </a>
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* The portal's remaining job. Everything above is native; billing address,
          tax IDs and the full receipt archive are the parts we do not reimplement,
          so they get one honest link rather than a button that duplicates the page. */}
      <div className="pt-1">
        <button
          type="button"
          onClick={openPortal}
          disabled={portalLoading}
          className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
        >
          {portalLoading
            ? <Loader2 className="h-3 w-3 animate-spin" />
            : <ExternalLink className="h-3 w-3" />}
          Billing address, tax ID and full receipt history
        </button>
      </div>

      {pubKey && (
        <UpdateCardDialog
          open={cardDialogOpen}
          onOpenChange={setCardDialogOpen}
          publishableKey={pubKey}
          hasExistingCard={Boolean(pm)}
          onSuccess={load}
        />
      )}
    </div>
  );
};

export default BillingOverview;
