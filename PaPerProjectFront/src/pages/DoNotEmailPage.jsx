import React, { useEffect, useMemo, useState } from 'react';
import { Helmet } from 'react-helmet';
import { useNavigate } from 'react-router-dom';
import { ChevronLeft, Loader2, MailX, Plus, Search } from 'lucide-react';

import DashboardNavbar from '@/components/common/DashboardNavbar';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useToast } from '@/components/ui/use-toast';
import usePurchasedModules from '@/hooks/usePurchasedModules';
import { companyApi, getCompanyUser, logoutCompany } from '@/services/companyAuthService';
import { getAgentNavItems } from '@/utils/agentNavItems';

const REASON_STYLE = {
  unsubscribed: 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300',
  bounced: 'border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-300',
  manual: 'border-border bg-muted text-muted-foreground',
};

const day = (iso) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
};

/**
 * /company/settings/do-not-email — the addresses this company must not send
 * outreach to (backend: core/do_not_email.py). Marketing and AI SDR both add
 * to it when someone unsubscribes or an address bounces, and both check it
 * before every email. An owner or admin can take a wrong entry off.
 */
export default function DoNotEmailPage() {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { purchasedModules, modulesLoaded } = usePurchasedModules();
  const companyUser = useMemo(() => getCompanyUser(), []);
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [email, setEmail] = useState('');
  const [note, setNote] = useState('');
  const [search, setSearch] = useState('');
  const [busy, setBusy] = useState('');          // 'add' or the id being removed
  const [confirming, setConfirming] = useState(null);

  useEffect(() => {
    companyApi.get('/company/do-not-email')
      .then((res) => setData(res?.data || null))
      .catch((e) => setError(e?.message || 'Could not load the do-not-email list.'));
  }, []);

  const add = async (event) => {
    event.preventDefault();
    if (!email.trim() || busy) return;
    setBusy('add');
    try {
      const res = await companyApi.post('/company/do-not-email', { email: email.trim(), note: note.trim() });
      setData(res?.data || data);
      setEmail('');
      setNote('');
      toast({ title: res?.added ? 'Added' : 'Already on the list', description: res?.message });
    } catch (e) {
      toast({ title: 'Not added', description: e?.message || 'Please try again.', variant: 'destructive' });
    } finally {
      setBusy('');
    }
  };

  const remove = async (entry) => {
    setBusy(entry.id);
    try {
      const res = await companyApi.delete(`/company/do-not-email/${entry.id}`);
      setData(res?.data || data);
      toast({ title: 'Removed', description: res?.message });
    } catch (e) {
      toast({ title: 'Not removed', description: e?.message || 'Please try again.', variant: 'destructive' });
    } finally {
      setBusy('');
      setConfirming(null);
    }
  };

  const handleLogout = async () => {
    await logoutCompany();
    navigate('/company/login');
  };

  const entries = data?.entries || [];
  const shown = useMemo(() => {
    const q = search.trim().toLowerCase();
    return q ? entries.filter((e) => e.email.includes(q)) : entries;
  }, [entries, search]);

  return (
    <>
      <Helmet><title>Do-not-email list — AIEmployee</title></Helmet>
      <div className="min-h-screen overflow-x-hidden" style={{ background: 'var(--app-page-bg)' }}>
        <DashboardNavbar
          icon={MailX}
          title="Do-not-email list"
          subtitle="People your company must not send outreach to"
          user={companyUser}
          userRole="Company User"
          onLogout={handleLogout}
          showNavTabs
          activeSection="dashboard"
          navItems={getAgentNavItems(purchasedModules, 'dashboard', navigate)}
          sidebarLoading={!modulesLoaded}
        />
        <div className="container mx-auto max-w-3xl px-4 py-8 space-y-5">
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            <ChevronLeft className="h-4 w-4" /> Back
          </button>

          <p className="text-sm text-muted-foreground">
            An address is added here when the person unsubscribes, when their email bounces, or when you add it
            below. Marketing and AI SDR both check this list before every email, and before a lead is added to
            a campaign, whichever colleague or agent is sending.
          </p>

          {error && <p className="text-sm text-destructive">{error}</p>}
          {!data && !error && (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading…
            </p>
          )}

          {data && (
            <>
              <form
                onSubmit={add}
                className="flex flex-col gap-2 rounded-xl border border-border bg-[var(--panel-2)] p-4 sm:flex-row sm:items-end"
              >
                <label className="min-w-0 flex-1 text-xs text-muted-foreground">
                  Email address
                  <Input
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="person@example.com"
                    className="mt-1"
                  />
                </label>
                <label className="min-w-0 flex-1 text-xs text-muted-foreground">
                  Note (optional)
                  <Input
                    value={note}
                    maxLength={255}
                    onChange={(e) => setNote(e.target.value)}
                    placeholder="e.g. asked by phone"
                    className="mt-1"
                  />
                </label>
                <Button type="submit" disabled={busy === 'add' || !email.trim()} className="shrink-0">
                  {busy === 'add' ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Plus className="mr-1 h-4 w-4" />}
                  Add
                </Button>
              </form>

              <section className="overflow-hidden rounded-xl border border-border bg-[var(--panel-2)]">
                <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-2.5">
                  <h2 className="text-sm font-semibold text-foreground">
                    {data.total} {data.total === 1 ? 'address' : 'addresses'}
                  </h2>
                  {entries.length > 5 && (
                    <div className="relative">
                      <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                      <Input
                        aria-label="Search addresses"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        placeholder="Search"
                        className="h-8 w-48 pl-7 text-sm"
                      />
                    </div>
                  )}
                </div>

                {entries.length === 0 && (
                  <p className="px-4 py-8 text-center text-sm text-muted-foreground">
                    Nobody is on the list yet.
                  </p>
                )}
                {entries.length > 0 && shown.length === 0 && (
                  <p className="px-4 py-8 text-center text-sm text-muted-foreground">No address matches “{search}”.</p>
                )}

                <div className="divide-y divide-border">
                  {shown.map((entry) => (
                    <div key={entry.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                      <div className="min-w-0">
                        <p className="break-all text-sm text-foreground">{entry.email}</p>
                        <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
                          <span className={`rounded-full border px-2 py-0.5 ${REASON_STYLE[entry.reason] || REASON_STYLE.manual}`}>
                            {entry.reason_label}
                          </span>
                          {entry.source !== 'manual' && entry.source_label && <span>from {entry.source_label}</span>}
                          {entry.added_by && <span>by {entry.added_by}</span>}
                          <span>{day(entry.created_at)}</span>
                          {entry.note && <span className="break-words">· {entry.note}</span>}
                        </p>
                      </div>
                      {data.can_remove && (
                        confirming === entry.id ? (
                          <div className="flex shrink-0 items-center gap-2">
                            <span className="text-xs text-muted-foreground">Allow emails to them again?</span>
                            <Button size="sm" variant="destructive" disabled={busy === entry.id} onClick={() => remove(entry)}>
                              {busy === entry.id && <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />}
                              Yes, remove
                            </Button>
                            <Button size="sm" variant="outline" disabled={busy === entry.id} onClick={() => setConfirming(null)}>
                              Keep
                            </Button>
                          </div>
                        ) : (
                          <Button size="sm" variant="outline" className="shrink-0" onClick={() => setConfirming(entry.id)}>
                            Remove
                          </Button>
                        )
                      )}
                    </div>
                  ))}
                </div>
              </section>

              {data.total > entries.length && (
                <p className="text-xs text-muted-foreground">
                  Showing the newest {entries.length} of {data.total}.
                </p>
              )}
              {!data.can_remove && entries.length > 0 && (
                <p className="text-xs text-muted-foreground">
                  Only an owner or admin of your company can take an address off this list.
                </p>
              )}
            </>
          )}
        </div>
      </div>
    </>
  );
}
