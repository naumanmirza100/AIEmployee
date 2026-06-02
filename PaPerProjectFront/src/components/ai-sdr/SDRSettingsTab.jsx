import React, { useState, useEffect, useCallback } from 'react';
import {
  Key, Eye, EyeOff, Save, CheckCircle2, AlertCircle,
  Loader2, RefreshCw, ExternalLink, ChevronDown, ChevronUp,
  Database, Zap, Settings, Wifi, WifiOff, Trash2, Plus,
} from 'lucide-react';
import { useToast } from '@/components/ui/use-toast';
import { getSdrSettings, saveSdrSettings, listCrmIntegrations, createCrmIntegration, updateCrmIntegration, deleteCrmIntegration, pingCrmIntegration } from '@/services/aiSdrService';

// ---------------------------------------------------------------------------
// Shared styles (dark theme, matches rest of SDR tabs)
// ---------------------------------------------------------------------------
const card = {
  background: 'rgba(255,255,255,0.03)',
  border: '1px solid rgba(255,255,255,0.08)',
  borderRadius: 12,
  padding: 24,
};

const inputStyle = {
  background: 'rgba(255,255,255,0.05)',
  border: '1px solid rgba(255,255,255,0.1)',
  borderRadius: 8,
  padding: '10px 14px',
  color: '#fff',
  fontSize: 14,
  width: '100%',
  outline: 'none',
  fontFamily: 'monospace',
};

const labelStyle = {
  display: 'block',
  fontSize: 13,
  fontWeight: 600,
  color: '#cfc6e6',
  marginBottom: 6,
};

const hintStyle = {
  fontSize: 12,
  color: 'rgba(255,255,255,0.35)',
  marginTop: 5,
  lineHeight: 1.5,
};

const btnPrimary = {
  background: 'linear-gradient(135deg,#a855f7,#ec4899)',
  border: 'none',
  borderRadius: 8,
  padding: '10px 20px',
  color: '#fff',
  fontWeight: 600,
  cursor: 'pointer',
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  fontSize: 14,
};

const sectionHeader = {
  display: 'flex',
  alignItems: 'center',
  gap: 10,
  marginBottom: 20,
  paddingBottom: 12,
  borderBottom: '1px solid rgba(255,255,255,0.06)',
};

// ---------------------------------------------------------------------------
// KeyField — input + show/hide toggle + set/not-set badge
// ---------------------------------------------------------------------------
const KeyField = ({ label, value, placeholder, hint, isSet, onChange, link, linkLabel }) => {
  const [show, setShow] = useState(false);

  return (
    <div style={{ marginBottom: 20 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <label style={labelStyle}>{label}</label>
        <span style={{
          fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 20,
          background: isSet ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.12)',
          color: isSet ? '#4ade80' : '#f87171',
          border: `1px solid ${isSet ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.25)'}`,
        }}>
          {isSet ? '✓ Set' : '✗ Not Set'}
        </span>
      </div>

      <div style={{ position: 'relative' }}>
        <input
          type={show ? 'text' : 'password'}
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder={placeholder}
          style={{ ...inputStyle, paddingRight: 44 }}
        />
        <button
          type="button"
          onClick={() => setShow(v => !v)}
          style={{
            position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)',
            background: 'none', border: 'none', cursor: 'pointer', color: 'rgba(255,255,255,0.4)',
            padding: 0,
          }}
        >
          {show ? <EyeOff size={16} /> : <Eye size={16} />}
        </button>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginTop: 5 }}>
        <p style={hintStyle}>{hint}</p>
        {link && (
          <a href={link} target="_blank" rel="noopener noreferrer"
            style={{ fontSize: 12, color: '#a855f7', display: 'flex', alignItems: 'center', gap: 4,
              textDecoration: 'none', whiteSpace: 'nowrap', marginLeft: 12 }}>
            {linkLabel} <ExternalLink size={11} />
          </a>
        )}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Collapsible section
// ---------------------------------------------------------------------------
const Section = ({ icon: Icon, title, subtitle, badge, children, defaultOpen = true }) => {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div style={{ ...card, marginBottom: 16 }}>
      <button
        onClick={() => setOpen(v => !v)}
        style={{ width: '100%', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
      >
        <div style={{ ...sectionHeader, marginBottom: open ? 20 : 0, paddingBottom: open ? 12 : 0,
          borderBottom: open ? '1px solid rgba(255,255,255,0.06)' : 'none' }}>
          <div style={{
            width: 36, height: 36, borderRadius: 10,
            background: 'linear-gradient(135deg,#a855f720,#ec489920)',
            border: '1px solid rgba(168,85,247,0.25)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Icon size={18} color="#a855f7" />
          </div>
          <div style={{ flex: 1, textAlign: 'left' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ color: '#fff', fontWeight: 700, fontSize: 15 }}>{title}</span>
              {badge && (
                <span style={{
                  fontSize: 10, fontWeight: 700, padding: '2px 7px', borderRadius: 20,
                  background: 'rgba(168,85,247,0.15)', color: '#c084fc',
                  border: '1px solid rgba(168,85,247,0.3)',
                }}>
                  {badge}
                </span>
              )}
            </div>
            <p style={{ color: 'rgba(255,255,255,0.45)', fontSize: 12, marginTop: 2 }}>{subtitle}</p>
          </div>
          {open ? <ChevronUp size={16} color="rgba(255,255,255,0.4)" /> : <ChevronDown size={16} color="rgba(255,255,255,0.4)" />}
        </div>
      </button>
      {open && <div>{children}</div>}
    </div>
  );
};

// ---------------------------------------------------------------------------
// CRM provider definitions
// ---------------------------------------------------------------------------
const CRM_PROVIDERS = {
  hubspot: {
    label: 'HubSpot', logo: '🟠', color: '#ff7a59',
    fields: [{ key: 'access_token', label: 'Access Token', placeholder: 'pat-na1-...', secret: true }],
  },
  salesforce: {
    label: 'Salesforce', logo: '🔵', color: '#00a1e0',
    fields: [
      { key: 'client_id',      label: 'Client ID',       placeholder: '3MVG...' },
      { key: 'client_secret',  label: 'Client Secret',   placeholder: '...',              secret: true },
      { key: 'username',       label: 'Username',         placeholder: 'user@example.com' },
      { key: 'password',       label: 'Password',         placeholder: '...',              secret: true },
      { key: 'security_token', label: 'Security Token',   placeholder: '...',              secret: true },
      { key: 'domain',         label: 'Domain',           placeholder: 'login or test' },
    ],
  },
  pipedrive: {
    label: 'Pipedrive', logo: '🟢', color: '#27c16b',
    fields: [{ key: 'api_token', label: 'API Token', placeholder: 'abc123...', secret: true }],
  },
};

// ---------------------------------------------------------------------------
// Confirm delete modal
// ---------------------------------------------------------------------------
const ConfirmDeleteModal = ({ provider, onConfirm, onCancel, deleting }) => {
  const cfg = CRM_PROVIDERS[provider] || {};
  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 2000,
      background: 'rgba(0,0,0,0.65)', backdropFilter: 'blur(4px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        background: 'linear-gradient(135deg,#0f0a1f 0%,#1a0a2e 100%)',
        border: '1px solid rgba(239,68,68,0.25)',
        borderRadius: 16, padding: 32, width: 400, maxWidth: '90vw',
        boxShadow: '0 24px 64px rgba(0,0,0,0.5)',
      }}>
        {/* Icon */}
        <div style={{
          width: 52, height: 52, borderRadius: 14, marginBottom: 20,
          background: 'rgba(239,68,68,0.12)', border: '1px solid rgba(239,68,68,0.25)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <Trash2 size={24} color="#f87171" />
        </div>

        <div style={{ color: '#fff', fontWeight: 700, fontSize: 17, marginBottom: 8 }}>
          Remove {cfg.label}?
        </div>
        <p style={{ color: 'rgba(255,255,255,0.45)', fontSize: 14, lineHeight: 1.6, marginBottom: 28 }}>
          This will permanently disconnect your <strong style={{ color: '#f87171' }}>{cfg.label}</strong> integration.
          All saved credentials will be deleted and lead syncing will stop.
        </p>

        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <button
            onClick={onCancel}
            disabled={deleting}
            style={{
              background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.12)',
              borderRadius: 8, padding: '9px 20px', color: '#d1d5db',
              fontSize: 14, fontWeight: 500, cursor: 'pointer',
            }}>
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={deleting}
            style={{
              background: 'linear-gradient(135deg,#dc2626,#ef4444)',
              border: 'none', borderRadius: 8, padding: '9px 20px', color: '#fff',
              fontSize: 14, fontWeight: 700, cursor: deleting ? 'not-allowed' : 'pointer',
              opacity: deleting ? 0.7 : 1,
              display: 'flex', alignItems: 'center', gap: 8,
            }}>
            {deleting
              ? <><Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} /> Removing…</>
              : <><Trash2 size={14} /> Yes, Remove</>}
          </button>
        </div>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// CRM integration card (connected — edit credentials + test + remove)
// ---------------------------------------------------------------------------
const CRMIntegrationCard = ({ integration, onRefresh }) => {
  const cfg = CRM_PROVIDERS[integration.provider] || {};
  const [creds, setCreds] = useState({ ...integration.credentials_preview });
  const [show, setShow] = useState({});
  const [saving, setSaving] = useState(false);
  const [pinging, setPinging] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const { toast } = useToast();

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateCrmIntegration(integration.id, { credentials: creds });
      toast({ title: `${cfg.label} credentials updated` });
      onRefresh();
    } catch (e) {
      toast({ title: 'Save failed', description: e?.message, variant: 'destructive' });
    } finally { setSaving(false); }
  };

  const handlePing = async () => {
    setPinging(true);
    try {
      const res = await pingCrmIntegration(integration.id);
      toast({ title: res.status === 'ok' ? '✅ Connected!' : '❌ Failed', description: res.message });
      onRefresh();
    } catch {
      toast({ title: 'Test failed', variant: 'destructive' });
    } finally { setPinging(false); }
  };

  const handleDeleteConfirmed = async () => {
    setDeleting(true);
    try {
      await deleteCrmIntegration(integration.id);
      toast({ title: `${cfg.label} disconnected`, description: 'Integration removed successfully.' });
      setShowDeleteModal(false);
      onRefresh();
    } catch (e) {
      toast({ title: 'Remove failed', description: e?.response?.data?.error || e?.message, variant: 'destructive' });
    } finally { setDeleting(false); }
  };

  const isOk = integration.last_ping_ok;
  const neverPinged = integration.last_ping_ok === null || integration.last_ping_ok === undefined;

  return (
    <>
      {showDeleteModal && (
        <ConfirmDeleteModal
          provider={integration.provider}
          onConfirm={handleDeleteConfirmed}
          onCancel={() => setShowDeleteModal(false)}
          deleting={deleting}
        />
      )}
    <div style={{ marginBottom: 20, padding: 18, borderRadius: 10, background: 'rgba(255,255,255,0.03)', border: `1px solid ${cfg.color}33` }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 24 }}>{cfg.logo}</span>
          <div>
            <span style={{ color: '#fff', fontWeight: 700, fontSize: 14 }}>{cfg.label}</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginTop: 3 }}>
              {neverPinged
                ? <span style={{ color: '#6b7280', fontSize: 11 }}>Not tested</span>
                : isOk
                  ? <><Wifi size={11} color="#10b981" /><span style={{ color: '#10b981', fontSize: 11 }}>Connected</span></>
                  : <><WifiOff size={11} color="#ef4444" /><span style={{ color: '#ef4444', fontSize: 11 }}>Failed</span></>}
            </div>
          </div>
        </div>
        <button
          onClick={() => setShowDeleteModal(true)}
          style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)',
            borderRadius: 7, padding: '5px 12px', color: '#f87171', fontSize: 12,
            cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5 }}>
          <Trash2 size={12} /> Remove
        </button>
      </div>

      {/* Credential fields */}
      {cfg.fields?.map(f => (
        <div key={f.key} style={{ marginBottom: 12 }}>
          <label style={{ ...labelStyle, fontSize: 12 }}>{f.label}</label>
          <div style={{ position: 'relative' }}>
            <input
              type={f.secret && !show[f.key] ? 'password' : 'text'}
              value={creds[f.key] || ''}
              onChange={e => setCreds(p => ({ ...p, [f.key]: e.target.value }))}
              placeholder={f.placeholder}
              style={{ ...inputStyle, paddingRight: f.secret ? 44 : 14 }}
            />
            {f.secret && (
              <button type="button" onClick={() => setShow(p => ({ ...p, [f.key]: !p[f.key] }))}
                style={{ position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)',
                  background: 'none', border: 'none', cursor: 'pointer', color: 'rgba(255,255,255,0.4)', padding: 0 }}>
                {show[f.key] ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            )}
          </div>
        </div>
      ))}

      {/* Actions */}
      <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
        <button onClick={handlePing} disabled={pinging}
          style={{ background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)',
            borderRadius: 7, padding: '7px 14px', color: '#d1d5db', fontSize: 12, cursor: 'pointer',
            display: 'flex', alignItems: 'center', gap: 5 }}>
          {pinging ? <Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} /> : <Wifi size={12} />}
          Test Connection
        </button>
        <button onClick={handleSave} disabled={saving}
          style={{ background: 'linear-gradient(135deg,#a855f7,#ec4899)', border: 'none',
            borderRadius: 7, padding: '7px 14px', color: '#fff', fontSize: 12, fontWeight: 600,
            cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5 }}>
          {saving ? <Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} /> : <Save size={12} />}
          Save
        </button>
      </div>
    </div>
    </>
  );
};

// ---------------------------------------------------------------------------
// CRM connect form (not yet connected)
// ---------------------------------------------------------------------------
const CRMConnectForm = ({ provider, onSaved }) => {
  const cfg = CRM_PROVIDERS[provider];
  const [open, setOpen] = useState(false);
  const [creds, setCreds] = useState({});
  const [show, setShow] = useState({});
  const [saving, setSaving] = useState(false);
  const { toast } = useToast();

  const handleConnect = async () => {
    const missing = cfg.fields.find(f => !creds[f.key]);
    if (missing) { toast({ title: `${missing.label} is required`, variant: 'destructive' }); return; }
    setSaving(true);
    try {
      await createCrmIntegration({ provider, credentials: creds });
      toast({ title: `${cfg.label} connected!` });
      onSaved();
      setOpen(false);
      setCreds({});
    } catch (e) {
      const msg = e?.response?.data?.error || e?.message || 'Check your credentials.';
      toast({ title: 'Connection failed', description: msg, variant: 'destructive' });
    } finally { setSaving(false); }
  };

  return (
    <div style={{ marginBottom: 12, borderRadius: 10, border: '1px solid rgba(255,255,255,0.07)', overflow: 'hidden' }}>
      <button onClick={() => setOpen(v => !v)}
        style={{ width: '100%', background: 'rgba(255,255,255,0.02)', border: 'none', cursor: 'pointer',
          padding: '12px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 20 }}>{cfg.logo}</span>
          <span style={{ color: '#d1d5db', fontWeight: 600, fontSize: 14 }}>{cfg.label}</span>
          <span style={{ fontSize: 11, padding: '2px 7px', borderRadius: 20,
            background: 'rgba(239,68,68,0.1)', color: '#f87171', border: '1px solid rgba(239,68,68,0.2)' }}>
            Not connected
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ color: '#a855f7', fontSize: 12, fontWeight: 600 }}>Connect</span>
          {open ? <ChevronUp size={14} color="rgba(255,255,255,0.4)" /> : <ChevronDown size={14} color="rgba(255,255,255,0.4)" />}
        </div>
      </button>

      {open && (
        <div style={{ padding: '14px 16px 16px', borderTop: '1px solid rgba(255,255,255,0.06)' }}>
          {cfg.fields.map(f => (
            <div key={f.key} style={{ marginBottom: 12 }}>
              <label style={{ ...labelStyle, fontSize: 12 }}>{f.label}</label>
              <div style={{ position: 'relative' }}>
                <input
                  type={f.secret && !show[f.key] ? 'password' : 'text'}
                  value={creds[f.key] || ''}
                  onChange={e => setCreds(p => ({ ...p, [f.key]: e.target.value }))}
                  placeholder={f.placeholder}
                  style={{ ...inputStyle, paddingRight: f.secret ? 44 : 14 }}
                />
                {f.secret && (
                  <button type="button" onClick={() => setShow(p => ({ ...p, [f.key]: !p[f.key] }))}
                    style={{ position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)',
                      background: 'none', border: 'none', cursor: 'pointer', color: 'rgba(255,255,255,0.4)', padding: 0 }}>
                    {show[f.key] ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                )}
              </div>
            </div>
          ))}
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 4 }}>
            <button onClick={handleConnect} disabled={saving}
              style={{ background: 'linear-gradient(135deg,#a855f7,#ec4899)', border: 'none',
                borderRadius: 7, padding: '8px 18px', color: '#fff', fontSize: 13, fontWeight: 600,
                cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}>
              {saving ? <Loader2 size={13} style={{ animation: 'spin 1s linear infinite' }} /> : <Plus size={13} />}
              {saving ? 'Connecting...' : 'Connect'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
const SDRSettingsTab = () => {
  const { toast } = useToast();

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // Form state — populated with actual stored values
  const [apolloKey, setApolloKey]       = useState('');
  const [apifyToken, setApifyToken]     = useState('');
  const [apifyActor, setApifyActor]     = useState('');

  // Track originals to detect changes
  const originals = React.useRef({ apolloKey: '', apifyToken: '', apifyActor: '' });

  // "is set" flags
  const [apolloSet, setApolloSet]       = useState(false);
  const [apifySet, setApifySet]         = useState(false);

  const [lastUpdated, setLastUpdated]   = useState(null);

  // CRM integrations
  const [crmIntegrations, setCrmIntegrations] = useState([]);

  // -----------------------------------------------------------------------
  const fetchSettings = useCallback(async () => {
    setLoading(true);
    try {
      const [sdrRes, crmRes] = await Promise.allSettled([getSdrSettings(), listCrmIntegrations()]);
      const res = sdrRes.status === 'fulfilled' ? sdrRes.value : null;
      if (!res) throw new Error('Could not load settings');
      const d = res?.data || res;
      const ak = d.apollo_api_key || '';
      const at = d.apify_api_token || '';
      const aa = d.apify_actor_id || '';
      setApolloKey(ak);
      setApifyToken(at);
      setApifyActor(aa);
      setApolloSet(!!d.apollo_api_key_set);
      setApifySet(!!d.apify_api_token_set);
      setLastUpdated(d.updated_at || null);
      originals.current = { apolloKey: ak, apifyToken: at, apifyActor: aa };
      if (crmRes.status === 'fulfilled') {
        const crm = crmRes.value?.data || crmRes.value;
        setCrmIntegrations(Array.isArray(crm) ? crm : []);
      }
    } catch {
      toast({ title: 'Error', description: 'Could not load settings.', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => { fetchSettings(); }, [fetchSettings]);

  // -----------------------------------------------------------------------
  const handleSave = async () => {
    setSaving(true);
    try {
      const payload = {};
      // Send a field only if it changed from what was loaded
      if (apolloKey.trim() !== originals.current.apolloKey)   payload.apollo_api_key  = apolloKey.trim();
      if (apifyToken.trim() !== originals.current.apifyToken) payload.apify_api_token = apifyToken.trim();
      if (apifyActor.trim() !== originals.current.apifyActor) payload.apify_actor_id  = apifyActor.trim();

      if (Object.keys(payload).length === 0) {
        toast({ title: 'No changes', description: 'Nothing to save.' });
        setSaving(false);
        return;
      }

      await saveSdrSettings(payload);
      toast({ title: 'Settings saved', description: 'Your API keys have been updated.' });
      await fetchSettings();
    } catch (err) {
      const msg = err?.response?.data?.message || err?.message || 'Failed to save settings.';
      toast({ title: 'Error', description: msg, variant: 'destructive' });
    } finally {
      setSaving(false);
    }
  };

  const [activePanel, setActivePanel] = useState('leads');

  // -----------------------------------------------------------------------
  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 80 }}>
        <Loader2 size={28} color="#a855f7" style={{ animation: 'spin 1s linear infinite' }} />
        <span style={{ color: 'rgba(255,255,255,0.5)', marginLeft: 12 }}>Loading settings…</span>
      </div>
    );
  }

  const SIDE_TABS = [
    {
      key: 'leads',
      icon: Database,
      label: 'Leads',
      sublabel: 'Apollo & Apify API keys',
      badge: (apolloSet || apifySet) ? 'Active' : null,
      badgeColor: '#4ade80',
    },
    {
      key: 'crm',
      icon: RefreshCw,
      label: 'CRMs',
      sublabel: 'HubSpot · Salesforce · Pipedrive',
      badge: crmIntegrations.length > 0 ? `${crmIntegrations.length} connected` : null,
      badgeColor: '#4ade80',
    },
  ];

  return (
    <div style={{ display: 'flex', gap: 20, alignItems: 'flex-start', paddingBottom: 40, minHeight: 500 }}>

      {/* ── Left sidebar ── */}
      <div style={{
        width: 210, flexShrink: 0,
        background: 'rgba(255,255,255,0.02)',
        border: '1px solid rgba(255,255,255,0.07)',
        borderRadius: 14, padding: 10,
      }}>
        {/* Header */}
        <div style={{ padding: '8px 10px 14px', borderBottom: '1px solid rgba(255,255,255,0.06)', marginBottom: 8 }}>
          <div style={{ color: '#fff', fontWeight: 700, fontSize: 14 }}>SDR Settings</div>
          <div style={{ color: 'rgba(255,255,255,0.35)', fontSize: 11, marginTop: 2 }}>Per-account credentials</div>
        </div>

        {SIDE_TABS.map(tab => {
          const Icon = tab.icon;
          const active = activePanel === tab.key;
          return (
            <button
              key={tab.key}
              onClick={() => setActivePanel(tab.key)}
              style={{
                width: '100%', textAlign: 'left', border: 'none', cursor: 'pointer',
                borderRadius: 10, padding: '10px 12px', marginBottom: 4,
                background: active ? 'linear-gradient(135deg,rgba(168,85,247,0.18),rgba(236,72,153,0.12))' : 'transparent',
                outline: active ? '1px solid rgba(168,85,247,0.3)' : '1px solid transparent',
                transition: 'all 0.15s',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <div style={{
                  width: 32, height: 32, borderRadius: 8, flexShrink: 0,
                  background: active ? 'linear-gradient(135deg,#a855f7,#ec4899)' : 'rgba(255,255,255,0.06)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                  <Icon size={15} color={active ? '#fff' : 'rgba(255,255,255,0.4)'} />
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ color: active ? '#fff' : 'rgba(255,255,255,0.65)', fontWeight: active ? 700 : 500, fontSize: 13 }}>
                    {tab.label}
                  </div>
                  <div style={{ color: 'rgba(255,255,255,0.3)', fontSize: 11, marginTop: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {tab.sublabel}
                  </div>
                </div>
              </div>
              {tab.badge && (
                <div style={{ marginTop: 6, marginLeft: 42 }}>
                  <span style={{
                    fontSize: 10, fontWeight: 700, padding: '2px 7px', borderRadius: 20,
                    background: 'rgba(74,222,128,0.12)', color: tab.badgeColor,
                    border: '1px solid rgba(74,222,128,0.25)',
                  }}>
                    {tab.badge}
                  </span>
                </div>
              )}
            </button>
          );
        })}

        {/* Refresh at bottom */}
        <div style={{ borderTop: '1px solid rgba(255,255,255,0.06)', marginTop: 8, paddingTop: 10 }}>
          <button onClick={fetchSettings} style={{
            width: '100%', background: 'none', border: 'none', cursor: 'pointer',
            color: 'rgba(255,255,255,0.35)', fontSize: 12, display: 'flex', alignItems: 'center', gap: 6,
            padding: '6px 12px', borderRadius: 8,
          }}>
            <RefreshCw size={13} /> Refresh
          </button>
        </div>
      </div>

      {/* ── Right panel ── */}
      <div style={{ flex: 1, minWidth: 0 }}>

        {/* ════ Leads panel ════ */}
        {activePanel === 'leads' && (
          <div>
            {/* Status banner */}
            <div style={{
              ...card, marginBottom: 20,
              background: (apolloSet || apifySet) ? 'rgba(34,197,94,0.06)' : 'rgba(251,191,36,0.06)',
              border: `1px solid ${(apolloSet || apifySet) ? 'rgba(34,197,94,0.2)' : 'rgba(251,191,36,0.2)'}`,
              padding: '14px 20px', display: 'flex', alignItems: 'center', gap: 12,
            }}>
              {(apolloSet || apifySet)
                ? <CheckCircle2 size={18} color="#4ade80" />
                : <AlertCircle size={18} color="#fbbf24" />}
              <div style={{ flex: 1 }}>
                <p style={{ color: (apolloSet || apifySet) ? '#4ade80' : '#fbbf24', fontWeight: 600, fontSize: 13, marginBottom: 2 }}>
                  {(apolloSet || apifySet) ? 'Lead sources configured' : 'No lead sources configured'}
                </p>
                <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: 12 }}>
                  {(apolloSet || apifySet)
                    ? `Active: ${[apolloSet && 'Apollo.io', apifySet && 'Apify'].filter(Boolean).join(' · ')}`
                    : 'Add an Apollo or Apify key to enable lead generation.'}
                </p>
              </div>
              {lastUpdated && (
                <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.25)', whiteSpace: 'nowrap' }}>
                  Updated {new Date(lastUpdated).toLocaleDateString()}
                </span>
              )}
            </div>

            {/* Apollo */}
            <Section icon={Database} title="Apollo.io" subtitle="People Search API — email, title, company data" badge="Recommended" defaultOpen={true}>
              <KeyField
                label="Apollo API Key" value={apolloKey}
                placeholder="Enter your Apollo.io API key"
                hint="Found in Apollo.io → Settings → Integrations → API Keys."
                isSet={apolloSet} onChange={setApolloKey}
                link="https://app.apollo.io/#/settings/integrations/api" linkLabel="Get API key"
              />
            </Section>

            {/* Apify */}
            <Section icon={Zap} title="Apify" subtitle="Web scraping actors — LinkedIn, Google Search" defaultOpen={true}>
              <KeyField
                label="Apify API Token" value={apifyToken}
                placeholder="Enter your Apify API token"
                hint="Found in Apify Console → Settings → Integrations → API tokens."
                isSet={apifySet} onChange={setApifyToken}
                link="https://console.apify.com/account/integrations" linkLabel="Get token"
              />
              <div style={{ marginBottom: 4 }}>
                <label style={labelStyle}>Apify Actor ID <span style={{ fontWeight: 400, color: 'rgba(255,255,255,0.3)' }}>(optional)</span></label>
                <input
                  type="text" value={apifyActor} onChange={e => setApifyActor(e.target.value)}
                  placeholder="e.g. curious_coder/linkedin-people-search-scraper"
                  style={{ ...inputStyle, fontFamily: 'monospace' }}
                />
                <p style={hintStyle}>Leave blank to use the default LinkedIn scraper.</p>
              </div>
            </Section>

            {/* Info */}
            <div style={{ ...card, background: 'rgba(168,85,247,0.05)', border: '1px solid rgba(168,85,247,0.15)', marginBottom: 24 }}>
              <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                <Settings size={16} color="#a855f7" style={{ marginTop: 2, flexShrink: 0 }} />
                <div>
                  <p style={{ color: '#c084fc', fontWeight: 600, fontSize: 13, marginBottom: 6 }}>How lead sources work</p>
                  <ul style={{ color: 'rgba(255,255,255,0.45)', fontSize: 12, lineHeight: 1.8, paddingLeft: 16 }}>
                    <li><strong style={{ color: '#c084fc' }}>Apollo</strong> — real emails, job titles, company data</li>
                    <li><strong style={{ color: '#c084fc' }}>Apify</strong> — LinkedIn scraping; great coverage</li>
                  </ul>
                  <p style={{ color: 'rgba(255,255,255,0.3)', fontSize: 11, marginTop: 8 }}>
                    Apollo is tried first, then Apify. You can also choose the source manually.
                  </p>
                </div>
              </div>
            </div>

            {/* Save */}
            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button onClick={handleSave} disabled={saving}
                style={{ ...btnPrimary, opacity: saving ? 0.6 : 1, minWidth: 140 }}>
                {saving
                  ? <><Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} /> Saving…</>
                  : <><Save size={16} /> Save API Keys</>}
              </button>
            </div>
          </div>
        )}

        {/* ════ CRMs panel ════ */}
        {activePanel === 'crm' && (
          <div>
            {/* Header */}
            <div style={{ marginBottom: 20 }}>
              <h3 style={{ color: '#fff', fontWeight: 700, fontSize: 17, marginBottom: 4 }}>CRM Integrations</h3>
              <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: 13 }}>
                Connect your CRM to automatically sync leads, emails, and meetings.
              </p>
            </div>

            {/* Connected */}
            {crmIntegrations.map(integration => (
              <CRMIntegrationCard key={integration.id} integration={integration} onRefresh={fetchSettings} />
            ))}

            {/* Not connected */}
            {Object.keys(CRM_PROVIDERS)
              .filter(p => !crmIntegrations.find(i => i.provider === p))
              .map(p => <CRMConnectForm key={p} provider={p} onSaved={fetchSettings} />)}

            {crmIntegrations.length === 0 && (
              <div style={{ ...card, background: 'rgba(168,85,247,0.04)', border: '1px solid rgba(168,85,247,0.12)', marginTop: 8, padding: '14px 18px' }}>
                <p style={{ color: 'rgba(255,255,255,0.3)', fontSize: 12 }}>
                  No CRM connected yet. Click a provider above to get started.
                </p>
              </div>
            )}
          </div>
        )}
      </div>

      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </div>
  );
};

export default SDRSettingsTab;
