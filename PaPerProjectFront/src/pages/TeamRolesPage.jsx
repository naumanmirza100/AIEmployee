import React, { useEffect, useMemo, useState } from 'react';
import { Helmet } from 'react-helmet';
import { Link, useNavigate } from 'react-router-dom';
import { ChevronLeft, Loader2, Plus, UserCog } from 'lucide-react';

import DashboardNavbar from '@/components/common/DashboardNavbar';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { useToast } from '@/components/ui/use-toast';
import usePurchasedModules from '@/hooks/usePurchasedModules';
import { companyApi, getCompanyUser, logoutCompany } from '@/services/companyAuthService';
import { getAgentNavItems } from '@/utils/agentNavItems';

const lastSeen = (login) => {
  if (!login.has_signed_in) return 'Has not signed in yet';
  const d = new Date(login.last_login);
  return Number.isNaN(d.getTime()) ? '' : `Last signed in ${d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })}`;
};

/**
 * /company/settings/team — the company's dashboard logins and their roles
 * (backend: api/views/company_logins.py). An owner or admin can add a login,
 * change a role and switch a login off. Before this page a role could not be
 * changed anywhere, so only the first login was ever an admin.
 */
export default function TeamRolesPage() {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { purchasedModules, modulesLoaded } = usePurchasedModules();
  const companyUser = useMemo(() => getCompanyUser(), []);
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [form, setForm] = useState({ full_name: '', email: '', role: 'company_user' });
  const [busy, setBusy] = useState('');          // 'add' or the id being changed

  useEffect(() => {
    companyApi.get('/company/logins')
      .then((res) => setData(res?.data || null))
      .catch((e) => setError(e?.message || 'Could not load the logins.'));
  }, []);

  const add = async (event) => {
    event.preventDefault();
    if (busy) return;
    setBusy('add');
    try {
      const res = await companyApi.post('/company/logins', {
        full_name: form.full_name.trim(), email: form.email.trim(), role: form.role,
      });
      setData(res?.data || data);
      setForm({ full_name: '', email: '', role: 'company_user' });
      toast({ title: res?.invited ? 'Login added' : 'Login added, but not emailed', description: res?.message });
    } catch (e) {
      toast({ title: 'Not added', description: e?.message || 'Please try again.', variant: 'destructive' });
    } finally {
      setBusy('');
    }
  };

  const change = async (login, patch) => {
    setBusy(login.id);
    try {
      const res = await companyApi.patch(`/company/logins/${login.id}`, patch);
      setData(res?.data || data);
    } catch (e) {
      toast({ title: 'Not changed', description: e?.message || 'Please try again.', variant: 'destructive' });
    } finally {
      setBusy('');
    }
  };

  const handleLogout = async () => {
    await logoutCompany();
    navigate('/company/login');
  };

  const roles = data?.roles || [];
  const canManage = !!data?.can_manage;

  return (
    <>
      <Helmet><title>Logins and roles — AIEmployee</title></Helmet>
      <div className="min-h-screen overflow-x-hidden" style={{ background: 'var(--app-page-bg)' }}>
        <DashboardNavbar
          icon={UserCog}
          title="Logins and roles"
          subtitle="Who can sign in to this dashboard, and what each can do"
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
            These are the logins to this dashboard. Your employees' own logins (My Space) are under{' '}
            <Link to="/company/dashboard/users" className="text-violet-600 underline dark:text-violet-300">Dashboard → Users</Link>.
          </p>

          {error && <p className="text-sm text-destructive">{error}</p>}
          {!data && !error && (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading…
            </p>
          )}

          {data && (
            <>
              {canManage && (
                <form onSubmit={add} className="rounded-xl border border-border bg-[var(--panel-2)] p-4 space-y-3">
                  <h2 className="text-sm font-semibold text-foreground">Add a login</h2>
                  <div className="grid gap-2 sm:grid-cols-2">
                    <label className="text-xs text-muted-foreground">
                      Name
                      <Input required value={form.full_name} maxLength={255} className="mt-1"
                        onChange={(e) => setForm({ ...form, full_name: e.target.value })} placeholder="Sam Rivera" />
                    </label>
                    <label className="text-xs text-muted-foreground">
                      Email address
                      <Input required type="email" value={form.email} className="mt-1"
                        onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="sam@yourcompany.com" />
                    </label>
                  </div>
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
                    <label className="flex-1 text-xs text-muted-foreground">
                      Role
                      <Select value={form.role} onValueChange={(role) => setForm({ ...form, role })}>
                        <SelectTrigger className="mt-1" aria-label="Role for the new login"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          {roles.map((r) => <SelectItem key={r.key} value={r.key}>{r.label}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    </label>
                    <Button type="submit" disabled={busy === 'add' || !form.full_name.trim() || !form.email.trim()} className="shrink-0">
                      {busy === 'add' ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Plus className="mr-1 h-4 w-4" />}
                      Add login
                    </Button>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    They get an email telling them to set their own password with “Forgot password” on the sign-in page.
                  </p>
                </form>
              )}

              <section className="overflow-hidden rounded-xl border border-border bg-[var(--panel-2)]">
                <div className="border-b border-border px-4 py-2.5">
                  <h2 className="text-sm font-semibold text-foreground">
                    {data.logins.length} {data.logins.length === 1 ? 'login' : 'logins'}
                  </h2>
                </div>
                <div className="divide-y divide-border">
                  {data.logins.map((login) => (
                    <div key={login.id} data-login={login.email}
                      className={`flex flex-wrap items-center justify-between gap-3 px-4 py-3 ${login.is_active ? '' : 'opacity-60'}`}>
                      <div className="min-w-0">
                        <p className="text-sm text-foreground">
                          {login.full_name}
                          {login.is_you && <span className="ml-2 rounded-full border border-border px-2 py-0.5 text-[11px] text-muted-foreground">you</span>}
                          {!login.is_active && <span className="ml-2 rounded-full border border-border px-2 py-0.5 text-[11px] text-muted-foreground">switched off</span>}
                        </p>
                        <p className="break-all text-xs text-muted-foreground">{login.email} · {lastSeen(login)}</p>
                      </div>
                      {canManage ? (
                        <div className="flex shrink-0 items-center gap-3">
                          {roles.some((r) => r.key === login.role) ? (
                            <Select value={login.role} disabled={busy === login.id}
                              onValueChange={(role) => role !== login.role && change(login, { role })}>
                              <SelectTrigger className="h-8 w-36 text-sm" aria-label={`Role of ${login.full_name}`}><SelectValue /></SelectTrigger>
                              <SelectContent>
                                {roles.map((r) => <SelectItem key={r.key} value={r.key}>{r.label}</SelectItem>)}
                              </SelectContent>
                            </Select>
                          ) : <span className="w-36 text-sm text-muted-foreground">{login.role_label}</span>}
                          <Switch
                            aria-label={`${login.full_name} can sign in`}
                            title={login.is_active ? 'Can sign in' : 'Switched off'}
                            checked={login.is_active}
                            disabled={busy === login.id}
                            onCheckedChange={(is_active) => change(login, { is_active })}
                          />
                        </div>
                      ) : <span className="shrink-0 text-sm text-muted-foreground">{login.role_label}</span>}
                    </div>
                  ))}
                </div>
              </section>

              <section className="rounded-xl border border-border bg-[var(--panel-2)] p-4">
                <h2 className="mb-2 text-sm font-semibold text-foreground">What each role can do</h2>
                <dl className="space-y-1.5">
                  {roles.map((r) => (
                    <div key={r.key} className="text-xs">
                      <dt className="inline font-medium text-foreground">{r.label}: </dt>
                      <dd className="inline text-muted-foreground">{r.description}</dd>
                    </div>
                  ))}
                </dl>
              </section>

              {!canManage && (
                <p className="text-xs text-muted-foreground">
                  Only an owner or admin of your company can add a login or change a role.
                </p>
              )}
            </>
          )}
        </div>
      </div>
    </>
  );
}
