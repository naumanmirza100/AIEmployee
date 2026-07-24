import React, { useEffect, useState } from 'react';
import { Helmet } from 'react-helmet';
import { useNavigate, useParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { useToast } from '@/components/ui/use-toast';
import { companyAuthService } from '@/services';
import {
  Loader2, ArrowLeft, Pencil, X, Check, Lock,
  Building2, Phone, Globe, Factory, Users2, MapPin, FileText, Mail, ShieldCheck, CalendarDays,
  User as UserIcon, Plug, CalendarCheck, CheckCircle2, ExternalLink,
} from 'lucide-react';

const ACCENT = '#a259ff';

// One labelled detail field. Read mode shows the value; edit mode swaps in an input.
const Field = ({ icon: Icon, label, name, value, editing, onChange, placeholder, textarea, locked, href }) => (
  <div className="space-y-1.5">
    <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-white/35">
      <Icon className="h-3.5 w-3.5" />
      {label}
      {locked && <Lock className="h-3 w-3 text-white/25" title="Managed by your account — can't be changed here" />}
    </div>
    {editing && !locked ? (
      textarea ? (
        <Textarea
          value={value || ''}
          onChange={(e) => onChange(name, e.target.value)}
          placeholder={placeholder}
          className="min-h-[92px] bg-black/40 border-white/10 focus-visible:ring-violet-500/40 focus-visible:border-violet-500/40"
        />
      ) : (
        <Input
          value={value || ''}
          onChange={(e) => onChange(name, e.target.value)}
          placeholder={placeholder}
          className="h-10 bg-black/40 border-white/10 focus-visible:ring-violet-500/40 focus-visible:border-violet-500/40"
        />
      )
    ) : href && value ? (
      <a href={value.startsWith('http') ? value : `https://${value}`} target="_blank" rel="noreferrer"
         className="inline-flex items-center gap-1.5 text-sm text-violet-300 hover:text-violet-200 break-words">
        {value} <ExternalLink className="h-3 w-3 shrink-0" />
      </a>
    ) : (
      <p className={`text-[15px] ${value ? 'text-white' : 'text-white/25'} break-words`}>{value || 'Not set'}</p>
    )}
  </div>
);

const CompanyProfilePage = () => {
  const navigate = useNavigate();
  const { tab } = useParams();
  const { toast } = useToast();
  const activeTab = tab === 'integrations' ? 'integrations' : 'profile';

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState(false);
  const [profile, setProfile] = useState(null); // { company, user }
  const [form, setForm] = useState(null);

  useEffect(() => {
    if (!companyAuthService.getCompanyUser()) {
      navigate('/company/login');
      return;
    }
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const load = async () => {
    try {
      setLoading(true);
      const res = await companyAuthService.getCompanyProfile();
      if (res.status === 'success') {
        setProfile(res.data);
        setForm(res.data.company);
      }
    } catch (e) {
      toast({ title: 'Error', description: e.message || 'Failed to load profile', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  const setField = (name, val) => setForm((f) => ({ ...f, [name]: val }));
  const startEdit = () => { setForm(profile.company); setEditing(true); };
  const cancelEdit = () => { setForm(profile.company); setEditing(false); };

  const save = async () => {
    if (!form.name || form.name.trim().length < 2) {
      toast({ title: 'Check the name', description: 'Company name needs at least 2 characters.', variant: 'destructive' });
      return;
    }
    try {
      setSaving(true);
      const res = await companyAuthService.updateCompanyProfile({
        name: form.name, phone: form.phone, address: form.address, website: form.website,
        industry: form.industry, companySize: form.companySize, description: form.description,
      });
      if (res.status === 'success') {
        setProfile(res.data);
        setForm(res.data.company);
        setEditing(false);
        toast({ title: 'Saved', description: 'Your company profile is up to date.' });
      }
    } catch (e) {
      toast({ title: 'Error', description: e.message || 'Failed to save', variant: 'destructive' });
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center"
           style={{ background: 'radial-gradient(1200px 600px at 20% -10%, rgba(124,58,237,0.15), transparent), #07050f' }}>
        <Loader2 className="h-8 w-8 animate-spin text-violet-400" />
      </div>
    );
  }
  if (!profile) return null;

  const c = profile.company;
  const u = profile.user;
  const memberSince = c.createdAt
    ? new Date(c.createdAt).toLocaleDateString('en-GB', { month: 'short', year: 'numeric' })
    : null;

  const tabs = [
    { value: 'profile', label: 'Profile', icon: UserIcon, to: '/company/profile' },
    { value: 'integrations', label: 'Integrations', icon: Plug, to: '/company/profile/integrations' },
  ];

  return (
    <>
      <Helmet><title>Company Profile | Pay Per Project</title></Helmet>
      <div className="min-h-screen"
           style={{ background: 'radial-gradient(1100px 550px at 18% -12%, rgba(124,58,237,0.16), transparent 60%), radial-gradient(900px 500px at 100% 0%, rgba(37,99,235,0.10), transparent 55%), #07050f' }}>
        <div className="mx-auto max-w-5xl px-4 sm:px-6 py-6 sm:py-8">

          <button onClick={() => navigate('/company/dashboard')}
                  className="inline-flex items-center gap-2 text-sm text-white/50 hover:text-white transition-colors mb-5">
            <ArrowLeft className="h-4 w-4" /> Back to dashboard
          </button>

          {/* ── Identity banner ── */}
          <div className="relative overflow-hidden rounded-3xl border border-white/[0.08] p-6 sm:p-8"
               style={{ background: 'linear-gradient(120deg, rgba(124,58,237,0.16), rgba(79,70,229,0.06) 45%, rgba(255,255,255,0.02))' }}>
            {/* soft grid texture */}
            <div className="pointer-events-none absolute inset-0 opacity-[0.15]"
                 style={{ backgroundImage: 'linear-gradient(rgba(255,255,255,.35) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.35) 1px, transparent 1px)', backgroundSize: '44px 44px', maskImage: 'radial-gradient(circle at 30% 20%, black, transparent 70%)' }} />
            <div className="relative flex flex-col sm:flex-row sm:items-center gap-5">
              {/* Monogram */}
              <div className="h-20 w-20 sm:h-24 sm:w-24 rounded-2xl flex items-center justify-center text-white font-extrabold text-4xl select-none shrink-0"
                   style={{ background: 'linear-gradient(135deg, #7c3aed, #a259ff)', boxShadow: '0 12px 40px -8px rgba(124,58,237,0.6)' }}>
                {(c.name || 'C').charAt(0).toUpperCase()}
              </div>

              <div className="min-w-0 flex-1">
                <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-violet-300/70 mb-1">Company account</p>
                <h1 className="text-2xl sm:text-3xl font-bold text-white leading-tight break-words">{c.name}</h1>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-400/30 bg-emerald-400/10 px-3 py-1 text-xs text-emerald-300">
                    <ShieldCheck className="h-3.5 w-3.5" /> {c.email}
                  </span>
                  {c.industry && (
                    <span className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-xs text-white/60">
                      <Factory className="h-3.5 w-3.5" /> {c.industry}
                    </span>
                  )}
                </div>
              </div>

              {activeTab === 'profile' && (
                <div className="shrink-0">
                  {!editing ? (
                    <Button onClick={startEdit} className="border-0 text-white"
                            style={{ background: 'linear-gradient(90deg,#7c3aed,#4f46e5)' }}>
                      <Pencil className="h-4 w-4 mr-2" /> Edit
                    </Button>
                  ) : (
                    <div className="flex gap-2">
                      <Button variant="outline" onClick={cancelEdit} disabled={saving} className="border-white/15 text-white/80">
                        <X className="h-4 w-4 mr-2" /> Cancel
                      </Button>
                      <Button onClick={save} disabled={saving} className="border-0 text-white"
                              style={{ background: 'linear-gradient(90deg,#7c3aed,#4f46e5)' }}>
                        {saving ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Check className="h-4 w-4 mr-2" />} Save
                      </Button>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Stat strip */}
            <div className="relative mt-6 grid grid-cols-2 sm:grid-cols-3 gap-px rounded-xl overflow-hidden border border-white/[0.06]"
                 style={{ background: 'rgba(255,255,255,0.06)' }}>
              {[
                { icon: UserIcon, label: 'Signed in as', value: u.fullName || u.email },
                { icon: ShieldCheck, label: 'Role', value: (u.role || 'admin'), cap: true },
                { icon: CalendarDays, label: 'Member since', value: memberSince || '—' },
              ].map((s, i) => (
                <div key={i} className="bg-[#0b0817] px-4 py-3">
                  <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-white/35">
                    <s.icon className="h-3 w-3" /> {s.label}
                  </div>
                  <p className={`mt-1 text-sm font-medium text-white truncate ${s.cap ? 'capitalize' : ''}`}>{s.value}</p>
                </div>
              ))}
            </div>
          </div>

          {/* ── Tabs ── */}
          <div className="mt-6 mb-5 flex gap-1 p-1 rounded-xl w-fit border border-white/[0.08]" style={{ background: '#100b1e' }}>
            {tabs.map((t) => {
              const on = activeTab === t.value;
              return (
                <button key={t.value} onClick={() => navigate(t.to)}
                        className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg transition-all"
                        style={on
                          ? { background: 'linear-gradient(90deg,#a259ff,#7c3aed)', color: '#fff', boxShadow: '0 6px 20px -6px rgba(124,58,237,0.7)' }
                          : { color: 'rgba(255,255,255,0.55)' }}>
                  <t.icon className="h-4 w-4" /> {t.label}
                </button>
              );
            })}
          </div>

          {/* ── Content ── */}
          {activeTab === 'integrations' ? (
            <IntegrationsTab />
          ) : (
            <div className="rounded-2xl border border-white/[0.08] p-6 sm:p-7" style={{ background: 'rgba(14,10,26,0.7)' }}>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-6">
                <Field icon={Building2} label="Company name" name="name" value={form.name} editing={editing} onChange={setField} placeholder="Acme Inc." />
                <Field icon={Mail} label="Email" value={c.email} locked />
                <Field icon={Phone} label="Phone" name="phone" value={form.phone} editing={editing} onChange={setField} placeholder="+1 234 567 8900" />
                <Field icon={Globe} label="Website" name="website" value={form.website} editing={editing} onChange={setField} placeholder="https://acme.com" href />
                <Field icon={Factory} label="Industry" name="industry" value={form.industry} editing={editing} onChange={setField} placeholder="Software" />
                <Field icon={Users2} label="Company size" name="companySize" value={form.companySize} editing={editing} onChange={setField} placeholder="50-100" />
                <div className="sm:col-span-2">
                  <Field icon={MapPin} label="Address" name="address" value={form.address} editing={editing} onChange={setField} placeholder="123 Main St, City" />
                </div>
                <div className="sm:col-span-2">
                  <Field icon={FileText} label="Description" name="description" value={form.description} editing={editing} onChange={setField} placeholder="What your company does" textarea />
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
};

// ─── Integrations tab ──────────────────────────────────────────────────────
const IntegrationsTab = () => {
  const { toast } = useToast();
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [gcal, setGcal] = useState({ connected: false, googleEmail: '', configured: true });

  const load = async () => {
    try {
      setLoading(true);
      const res = await companyAuthService.getGoogleCalendarStatus();
      if (res.status === 'success') setGcal(res.data);
    } catch (e) {
      console.error('Google Calendar status error:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    const params = new URLSearchParams(window.location.search);
    if (params.get('gcal') === 'connected') {
      toast({ title: 'Google Calendar connected', description: 'Interviews will be added to your calendar.' });
      window.history.replaceState({}, '', window.location.pathname);
    } else if (params.get('gcal_error')) {
      toast({ title: 'Connection failed', description: params.get('gcal_error'), variant: 'destructive' });
      window.history.replaceState({}, '', window.location.pathname);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleConnect = async () => {
    try {
      setWorking(true);
      const res = await companyAuthService.connectGoogleCalendar();
      if (res.status === 'success' && res.data?.authUrl) {
        window.location.href = res.data.authUrl;
      } else {
        throw new Error(res.message || 'Could not start connection');
      }
    } catch (e) {
      toast({ title: 'Error', description: e.message || 'Failed to connect', variant: 'destructive' });
      setWorking(false);
    }
  };

  const handleDisconnect = async () => {
    try {
      setWorking(true);
      const res = await companyAuthService.disconnectGoogleCalendar();
      if (res.status === 'success') {
        toast({ title: 'Disconnected', description: 'Google Calendar has been disconnected.' });
        await load();
      }
    } catch (e) {
      toast({ title: 'Error', description: e.message || 'Failed to disconnect', variant: 'destructive' });
    } finally {
      setWorking(false);
    }
  };

  if (loading) {
    return <div className="flex justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-white/60" /></div>;
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
      {/* Google Calendar */}
      <div className="rounded-2xl border border-white/[0.08] p-5 flex flex-col" style={{ background: 'rgba(14,10,26,0.7)' }}>
        <div className="flex items-start gap-3">
          <div className="flex items-center justify-center w-11 h-11 rounded-xl shrink-0" style={{ background: '#1a73e8' }}>
            <CalendarCheck className="h-6 w-6 text-white" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <h3 className="text-base font-semibold text-white">Google Calendar</h3>
              {gcal.connected && (
                <span className="inline-flex items-center gap-1 rounded-full bg-emerald-400/10 border border-emerald-400/30 px-2 py-0.5 text-[10px] font-semibold text-emerald-300">
                  <CheckCircle2 className="h-3 w-3" /> Connected
                </span>
              )}
            </div>
            <p className="text-sm text-white/55 mt-1 leading-relaxed">
              Interviews land on your calendar as events with a Meet link, automatically.
            </p>
          </div>
        </div>

        <div className="mt-5 pt-4 border-t border-white/[0.06] flex items-center justify-between gap-3">
          <span className="text-xs text-white/45 truncate">
            {gcal.connected
              ? (gcal.googleEmail || 'Connected account')
              : 'Not connected'}
          </span>
          {gcal.connected ? (
            <Button variant="outline" size="sm" onClick={handleDisconnect} disabled={working}
                    className="border-white/15 text-white/80 hover:text-white rounded-full shrink-0">
              {working ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Disconnect'}
            </Button>
          ) : (
            <Button size="sm" onClick={handleConnect} disabled={working || !gcal.configured}
                    className="rounded-full font-semibold border-0 shrink-0"
                    style={{ background: ACCENT, color: '#160b28' }}>
              {working ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Connect'}
            </Button>
          )}
        </div>

        {!gcal.configured && (
          <p className="mt-3 text-[11px] text-amber-400/80">
            Google Calendar isn't configured on the server yet. Contact support to enable it.
          </p>
        )}
      </div>

      {/* Placeholder for future integrations — keeps the grid balanced and hints at more */}
      <div className="rounded-2xl border border-dashed border-white/[0.08] p-5 flex flex-col items-center justify-center text-center min-h-[150px]"
           style={{ background: 'rgba(255,255,255,0.015)' }}>
        <Plug className="h-6 w-6 text-white/25 mb-2" />
        <p className="text-sm text-white/40">More integrations coming soon</p>
      </div>
    </div>
  );
};

export default CompanyProfilePage;
