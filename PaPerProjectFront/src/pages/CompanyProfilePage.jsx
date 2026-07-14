import React, { useEffect, useState } from 'react';
import { Helmet } from 'react-helmet';
import { useNavigate, useParams } from 'react-router-dom';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { useToast } from '@/components/ui/use-toast';
import { companyAuthService } from '@/services';
import {
  Loader2, ArrowLeft, Pencil, X, Check, Lock,
  Building2, Phone, Globe, Factory, Users2, MapPin, FileText, Mail, ShieldCheck, CalendarDays,
  User as UserIcon, Plug, CalendarCheck, CheckCircle2,
} from 'lucide-react';

// Editable text field row (labelled). Renders a read value or an input.
const Field = ({ icon: Icon, label, name, value, editing, onChange, placeholder, textarea, locked }) => (
  <div className="space-y-1.5">
    <Label className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-white/40">
      <Icon className="h-3.5 w-3.5" />
      {label}
      {locked && <Lock className="h-3 w-3 text-white/30" title="Email can't be changed here" />}
    </Label>
    {editing && !locked ? (
      textarea ? (
        <Textarea
          value={value}
          onChange={(e) => onChange(name, e.target.value)}
          placeholder={placeholder}
          className="min-h-[90px] bg-black/30 border-white/15"
        />
      ) : (
        <Input
          value={value}
          onChange={(e) => onChange(name, e.target.value)}
          placeholder={placeholder}
          className="bg-black/30 border-white/15"
        />
      )
    ) : (
      <p className={`text-sm ${value ? 'text-white' : 'text-white/30'} ${locked ? 'flex items-center gap-2' : ''} break-words`}>
        {value || '—'}
      </p>
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
      toast({ title: 'Invalid name', description: 'Company name must be at least 2 characters.', variant: 'destructive' });
      return;
    }
    try {
      setSaving(true);
      const res = await companyAuthService.updateCompanyProfile({
        name: form.name,
        phone: form.phone,
        address: form.address,
        website: form.website,
        industry: form.industry,
        companySize: form.companySize,
        description: form.description,
      });
      if (res.status === 'success') {
        setProfile(res.data);
        setForm(res.data.company);
        setEditing(false);
        toast({ title: 'Saved', description: 'Your company profile has been updated.' });
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
           style={{ background: 'linear-gradient(135deg,#020308,#0a0a1a 40%,#0f0a20 70%,#020308)' }}>
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

  return (
    <>
      <Helmet><title>Company Profile | Pay Per Project</title></Helmet>
      <div className="min-h-screen px-4 py-6 sm:px-8 sm:py-10"
           style={{ background: 'linear-gradient(135deg,#020308,#0a0a1a 40%,#0f0a20 70%,#020308)' }}>
        <div className="mx-auto max-w-5xl">
          {/* Top bar */}
          <div className="flex items-center justify-between mb-5">
            <Button variant="ghost" className="text-white/70 hover:text-white" onClick={() => navigate('/company/dashboard')}>
              <ArrowLeft className="h-4 w-4 mr-2" /> Dashboard
            </Button>
            {activeTab === 'profile' && (
              !editing ? (
                <Button onClick={startEdit}
                        style={{ background: 'linear-gradient(90deg,#7c3aed,#4f46e5)' }}
                        className="text-white border-0">
                  <Pencil className="h-4 w-4 mr-2" /> Edit Profile
                </Button>
              ) : (
                <div className="flex gap-2">
                  <Button variant="outline" onClick={cancelEdit} disabled={saving} className="border-white/20">
                    <X className="h-4 w-4 mr-2" /> Cancel
                  </Button>
                  <Button onClick={save} disabled={saving}
                          style={{ background: 'linear-gradient(90deg,#7c3aed,#4f46e5)' }}
                          className="text-white border-0">
                    {saving ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Check className="h-4 w-4 mr-2" />}
                    Save Changes
                  </Button>
                </div>
              )
            )}
          </div>

          {/* Tabs */}
          <div className="inline-flex mb-6 p-1 gap-1 rounded-lg bg-[#1a1333] border border-[#3a295a]">
            {[
              { value: 'profile', label: 'Profile', icon: UserIcon, to: '/company/profile' },
              { value: 'integrations', label: 'Integrations', icon: Plug, to: '/company/profile/integrations' },
            ].map((t) => (
              <button
                key={t.value}
                onClick={() => navigate(t.to)}
                className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-md border transition-all"
                style={activeTab === t.value
                  ? { background: 'linear-gradient(90deg,#a259ff,#7c3aed)', color: '#fff', border: '1.5px solid #a259ff' }
                  : { background: 'rgba(60,30,90,0.22)', color: '#cfc6e6', border: '1.5px solid #2d2342' }}
              >
                <t.icon className="h-4 w-4" />
                {t.label}
              </button>
            ))}
          </div>

          {activeTab === 'integrations' ? (
            <IntegrationsTab />
          ) : (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
            {/* Identity rail */}
            <Card className="lg:col-span-1 border-white/10 bg-black/30 backdrop-blur-sm h-fit">
              <CardContent className="p-6 text-center">
                <div className="mx-auto mb-4 h-20 w-20 rounded-2xl flex items-center justify-center text-white font-bold text-3xl select-none"
                     style={{ background: 'linear-gradient(135deg,#7c3aed,#a259ff)', boxShadow: '0 0 20px rgba(124,58,237,0.45)' }}>
                  {(c.name || 'C').charAt(0).toUpperCase()}
                </div>
                <h1 className="text-xl font-bold text-white break-words">{c.name}</h1>

                {/* Verified email — locked identity */}
                <div className="mt-3 inline-flex items-center gap-2 rounded-full border border-emerald-400/30 bg-emerald-400/10 px-3 py-1 text-xs text-emerald-300">
                  <ShieldCheck className="h-3.5 w-3.5" />
                  {c.email}
                </div>

                <div className="mt-6 space-y-3 text-left">
                  <div className="flex items-center gap-2 text-sm text-white/60">
                    <Users2 className="h-4 w-4 text-violet-400" />
                    Signed in as <span className="text-white font-medium">{u.fullName || u.email}</span>
                  </div>
                  <div className="flex items-center gap-2 text-sm text-white/60">
                    <ShieldCheck className="h-4 w-4 text-violet-400" />
                    Role <span className="text-white font-medium capitalize">{u.role || 'admin'}</span>
                  </div>
                  {memberSince && (
                    <div className="flex items-center gap-2 text-sm text-white/60">
                      <CalendarDays className="h-4 w-4 text-violet-400" />
                      Member since <span className="text-white font-medium">{memberSince}</span>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>

            {/* Details */}
            <Card className="lg:col-span-2 border-white/10 bg-black/30 backdrop-blur-sm">
              <CardContent className="p-6">
                <h2 className="text-sm font-semibold uppercase tracking-wider text-white/50 mb-5">Company Details</h2>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-5">
                  <Field icon={Building2} label="Company Name" name="name" value={form.name} editing={editing} onChange={setField} placeholder="Acme Inc." />
                  <Field icon={Mail} label="Email" value={c.email} locked />
                  <Field icon={Phone} label="Phone" name="phone" value={form.phone} editing={editing} onChange={setField} placeholder="+1 234 567 8900" />
                  <Field icon={Globe} label="Website" name="website" value={form.website} editing={editing} onChange={setField} placeholder="https://acme.com" />
                  <Field icon={Factory} label="Industry" name="industry" value={form.industry} editing={editing} onChange={setField} placeholder="Software" />
                  <Field icon={Users2} label="Company Size" name="companySize" value={form.companySize} editing={editing} onChange={setField} placeholder="50-100" />
                  <div className="sm:col-span-2">
                    <Field icon={MapPin} label="Address" name="address" value={form.address} editing={editing} onChange={setField} placeholder="123 Main St, City" />
                  </div>
                  <div className="sm:col-span-2">
                    <Field icon={FileText} label="Description" name="description" value={form.description} editing={editing} onChange={setField} placeholder="What your company does" textarea />
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
          )}
        </div>
      </div>
    </>
  );
};

// ─── Integrations tab: Google Calendar connect card ───────────────────────
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
    // Surface the OAuth callback result (?gcal=connected / ?gcal_error=...).
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
      {/* Google Calendar card */}
      <div className="rounded-2xl border border-white/10 bg-black/30 backdrop-blur-sm p-5 flex flex-col">
        <div className="flex items-start gap-3">
          <div className="flex items-center justify-center w-11 h-11 rounded-xl shrink-0" style={{ background: '#1a73e8' }}>
            <CalendarCheck className="h-6 w-6 text-white" />
          </div>
          <div className="min-w-0">
            <h3 className="text-base font-semibold text-white">Google Calendar</h3>
            <p className="text-sm text-white/55 mt-0.5 leading-relaxed">
              Interviews land on your calendar as events with a Meet link, automatically.
            </p>
          </div>
        </div>

        <div className="mt-5 flex items-center justify-between gap-3">
          <span className="text-xs text-white/45">
            {gcal.connected ? (
              <span className="inline-flex items-center gap-1.5 text-emerald-400">
                <CheckCircle2 className="h-3.5 w-3.5" />
                Connected{gcal.googleEmail ? ` · ${gcal.googleEmail}` : ''}
              </span>
            ) : (
              'Calendar'
            )}
          </span>

          {gcal.connected ? (
            <Button variant="outline" size="sm" onClick={handleDisconnect} disabled={working}
                    className="border-white/20 text-white/80 hover:text-white rounded-full">
              {working ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Disconnect'}
            </Button>
          ) : (
            <Button size="sm" onClick={handleConnect} disabled={working || !gcal.configured}
                    className="rounded-full font-semibold border-0"
                    style={{ background: '#c6f24e', color: '#1a1a1a' }}>
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
    </div>
  );
};

export default CompanyProfilePage;
