import React, { useEffect, useMemo, useState } from 'react';
import { Helmet } from 'react-helmet';
import { Link, useNavigate } from 'react-router-dom';
import { BellRing, ChevronLeft, Loader2, MailX } from 'lucide-react';

import DashboardNavbar from '@/components/common/DashboardNavbar';
import { Switch } from '@/components/ui/switch';
import { useToast } from '@/components/ui/use-toast';
import usePurchasedModules from '@/hooks/usePurchasedModules';
import { companyApi, getCompanyUser, logoutCompany } from '@/services/companyAuthService';
import { getAgentNavItems } from '@/utils/agentNavItems';

/**
 * /company/settings/notifications — one place to choose what each dashboard
 * login hears about, from every agent: in the bell, by email, or both
 * (backend: core/notification_settings.py). Each agent's alerts and emails
 * ask these choices before they go out.
 */
export default function NotificationSettingsPage() {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { purchasedModules, modulesLoaded } = usePurchasedModules();
  const companyUser = useMemo(() => getCompanyUser(), []);
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    companyApi.get('/company/notification-settings')
      .then((res) => setData(res?.data || null))
      .catch((e) => setError(e?.message || 'Could not load your notification settings.'));
  }, []);

  const save = async (change, optimistic) => {
    const before = data;
    setData(optimistic);
    try {
      const res = await companyApi.patch('/company/notification-settings', change);
      setData(res?.data || optimistic);
    } catch (e) {
      setData(before);
      toast({ title: 'Not saved', description: e?.message || 'Please try again.', variant: 'destructive' });
    }
  };

  const setTopic = (key, field, value) => save(
    { topic: key, [field]: value },
    { ...data, topics: data.topics.map((t) => (t.key === key ? { ...t, [field]: value } : t)) },
  );

  const groups = useMemo(() => {
    const out = [];
    (data?.topics || []).forEach((t) => {
      const last = out[out.length - 1];
      if (last && last.agent === t.agent) last.topics.push(t);
      else out.push({ agent: t.agent, label: t.agent_label, topics: [t] });
    });
    return out;
  }, [data]);

  const handleLogout = async () => {
    await logoutCompany();
    navigate('/company/login');
  };

  const paused = !!data?.email_paused;

  return (
    <>
      <Helmet><title>Notification settings — AIEmployee</title></Helmet>
      <div className="min-h-screen overflow-x-hidden" style={{ background: 'var(--app-page-bg)' }}>
        <DashboardNavbar
          icon={BellRing}
          title="Notification settings"
          subtitle="What you hear about, from every agent"
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

          {error && <p className="text-sm text-destructive">{error}</p>}
          {!data && !error && (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading…
            </p>
          )}

          {data && (
            <>
              <div className="flex items-center justify-between gap-4 rounded-xl border border-border bg-[var(--panel-2)] p-4">
                <div className="flex items-start gap-3 min-w-0">
                  <MailX className="mt-0.5 h-5 w-5 shrink-0 text-muted-foreground" />
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-foreground">Pause all emails</p>
                    <p className="text-xs text-muted-foreground break-words">
                      {paused
                        ? 'Nothing is emailed until you turn this off; the bell still works. Your choices below are kept.'
                        : `Emails go to ${data.email_address || 'your login email'}.`}
                    </p>
                  </div>
                </div>
                <Switch
                  aria-label="Pause all emails"
                  checked={paused}
                  onCheckedChange={(v) => save({ email_paused: v }, { ...data, email_paused: v })}
                />
              </div>

              {groups.map((g) => (
                <section key={g.agent} className="overflow-hidden rounded-xl border border-border bg-[var(--panel-2)]">
                  <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
                    <h2 className="text-sm font-semibold text-foreground">{g.label}</h2>
                    <div className="flex gap-6 pr-1 text-[11px] uppercase tracking-wider text-muted-foreground">
                      <span className="w-11 text-center">Bell</span>
                      <span className="w-11 text-center">Email</span>
                    </div>
                  </div>
                  <div className="divide-y divide-border">
                    {g.topics.map((t) => (
                      <div key={t.key} className="flex items-center justify-between gap-4 px-4 py-3">
                        <div className="min-w-0">
                          <p className="text-sm text-foreground">{t.label}</p>
                          <p className="text-xs text-muted-foreground">{t.description}</p>
                        </div>
                        <div className="flex shrink-0 gap-6">
                          {t.offers_in_app ? (
                            <Switch
                              aria-label={`Bell: ${t.label}`}
                              checked={t.in_app}
                              disabled={t.in_app_locked}
                              title={t.in_app_locked ? 'Always in the bell' : undefined}
                              onCheckedChange={(v) => setTopic(t.key, 'in_app', v)}
                            />
                          ) : <span className="w-11 text-center text-xs text-muted-foreground" title="Email only">—</span>}
                          {t.offers_email ? (
                            <Switch
                              aria-label={`Email: ${t.label}`}
                              checked={t.email}
                              className={paused ? 'opacity-40' : ''}
                              title={paused ? 'All emails are paused' : undefined}
                              onCheckedChange={(v) => setTopic(t.key, 'email', v)}
                            />
                          ) : <span className="w-11 text-center text-xs text-muted-foreground" title="Bell only">—</span>}
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              ))}

              {groups.some((g) => g.agent === 'project_manager_agent') && (
                <p className="text-xs text-muted-foreground">
                  Sending Project Manager alerts to Slack or Teams is set up in{' '}
                  <Link to="/project-manager/dashboard?tab=ai-tools" className="text-violet-600 underline dark:text-violet-300">
                    Project Manager → AI tools → Notification settings
                  </Link>.
                </p>
              )}
            </>
          )}
        </div>
      </div>
    </>
  );
}
