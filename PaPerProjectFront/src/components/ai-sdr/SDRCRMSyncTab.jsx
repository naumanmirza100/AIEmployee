import React, { useState, useEffect, useCallback } from 'react';
import {
  RefreshCw, Plus, Trash2, CheckCircle2, XCircle, Wifi, WifiOff,
  AlertCircle, Loader2, ChevronDown, ChevronUp, Users, Mail,
  Calendar, FileText, Database, Zap,
} from 'lucide-react';
import { useToast } from '@/components/ui/use-toast';
import {
  listCrmIntegrations, createCrmIntegration, deleteCrmIntegration,
  pingCrmIntegration, syncCrmLeads, getCrmQueueStatus, retryCrmFailed,
} from '@/services/aiSdrService';

// ---------------------------------------------------------------------------
// Styles (matching project dark theme)
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

const btnSecondary = {
  background: 'rgba(255,255,255,0.06)',
  border: '1px solid rgba(255,255,255,0.12)',
  borderRadius: 8,
  padding: '8px 16px',
  color: '#d1d5db',
  cursor: 'pointer',
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  fontSize: 13,
};

// ---------------------------------------------------------------------------
// Provider Config
// ---------------------------------------------------------------------------
const PROVIDERS = {
  hubspot: {
    label: 'HubSpot',
    color: '#ff7a59',
    bg: 'rgba(255,122,89,0.12)',
    logo: '🟠',
    fields: [{ key: 'access_token', label: 'Access Token (Service Key)', placeholder: 'pat-na1-...' }],
  },
  salesforce: {
    label: 'Salesforce',
    color: '#00a1e0',
    bg: 'rgba(0,161,224,0.12)',
    logo: '🔵',
    fields: [
      { key: 'client_id',      label: 'Client ID',       placeholder: '3MVG...' },
      { key: 'client_secret',  label: 'Client Secret',   placeholder: '...',        type: 'password' },
      { key: 'username',       label: 'Username',         placeholder: 'user@example.com' },
      { key: 'password',       label: 'Password',         placeholder: '...',        type: 'password' },
      { key: 'security_token', label: 'Security Token',   placeholder: '...',        type: 'password' },
      { key: 'domain',         label: 'Domain',           placeholder: 'login (or test for sandbox)' },
    ],
  },
  pipedrive: {
    label: 'Pipedrive',
    color: '#27c16b',
    bg: 'rgba(39,193,107,0.12)',
    logo: '🟢',
    fields: [{ key: 'api_token', label: 'API Token', placeholder: 'abc123...' }],
  },
};

// ---------------------------------------------------------------------------
// Connect Modal
// ---------------------------------------------------------------------------
function ConnectModal({ provider, onClose, onSaved }) {
  const cfg = PROVIDERS[provider];
  const [creds, setCreds] = useState({});
  const [loading, setLoading] = useState(false);
  const { toast } = useToast();

  const handleSave = async () => {
    const missing = cfg.fields.find(f => !creds[f.key]);
    if (missing) {
      toast({ title: `${missing.label} is required`, variant: 'destructive' });
      return;
    }
    setLoading(true);
    try {
      await createCrmIntegration({ provider, credentials: creds });
      toast({ title: `${cfg.label} connected!`, description: 'Integration saved successfully.' });
      onSaved();
      onClose();
    } catch (e) {
      toast({ title: 'Connection failed', description: e?.message || 'Check your credentials.', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
    }}>
      <div style={{ ...card, width: 480, maxWidth: '95vw', background: 'rgba(20,10,40,0.98)', border: '1px solid rgba(255,255,255,0.12)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
          <span style={{ fontSize: 28 }}>{cfg.logo}</span>
          <div>
            <div style={{ color: '#fff', fontWeight: 700, fontSize: 18 }}>Connect {cfg.label}</div>
            <div style={{ color: '#9ca3af', fontSize: 13 }}>Enter your {cfg.label} credentials</div>
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginBottom: 24 }}>
          {cfg.fields.map(f => (
            <div key={f.key}>
              <div style={{ color: '#d1d5db', fontSize: 13, marginBottom: 6 }}>{f.label}</div>
              <input
                style={inputStyle}
                type={f.type || 'text'}
                placeholder={f.placeholder}
                value={creds[f.key] || ''}
                onChange={e => setCreds(p => ({ ...p, [f.key]: e.target.value }))}
              />
            </div>
          ))}
        </div>

        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <button style={btnSecondary} onClick={onClose}>Cancel</button>
          <button style={btnPrimary} onClick={handleSave} disabled={loading}>
            {loading ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />}
            {loading ? 'Connecting...' : 'Connect'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Integration Card
// ---------------------------------------------------------------------------
function IntegrationCard({ integration, onDelete, onRefresh }) {
  const cfg = PROVIDERS[integration.provider] || {};
  const [pinging, setPinging] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const { toast } = useToast();

  const handlePing = async () => {
    setPinging(true);
    try {
      const res = await pingCrmIntegration(integration.id);
      toast({ title: res.status === 'ok' ? '✅ Connected!' : '❌ Failed', description: res.message });
      onRefresh();
    } catch {
      toast({ title: 'Ping failed', variant: 'destructive' });
    } finally {
      setPinging(false);
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    try {
      await syncCrmLeads(integration.id);
      toast({ title: 'Sync queued!', description: 'All leads will sync to ' + cfg.label });
    } catch {
      toast({ title: 'Sync failed', variant: 'destructive' });
    } finally {
      setSyncing(false);
    }
  };

  const [confirmDelete, setConfirmDelete] = useState(false);

  const handleDelete = async () => {
    if (!confirmDelete) { setConfirmDelete(true); return; }
    try {
      await deleteCrmIntegration(integration.id);
      toast({ title: `${cfg.label} disconnected` });
      onRefresh();
    } catch (e) {
      const msg = e?.response?.data?.error || e?.message || 'Unknown error';
      toast({ title: 'Delete failed', description: msg, variant: 'destructive' });
    } finally {
      setConfirmDelete(false);
    }
  };

  const isOk = integration.last_ping_ok;
  const neverPinged = integration.last_ping_ok === null || integration.last_ping_ok === undefined;

  return (
    <div style={{ ...card, display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontSize: 32 }}>{cfg.logo}</span>
          <div>
            <div style={{ color: '#fff', fontWeight: 700, fontSize: 16 }}>{cfg.label}</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 4 }}>
              {neverPinged ? (
                <span style={{ color: '#6b7280', fontSize: 12 }}>Not tested yet</span>
              ) : isOk ? (
                <><Wifi size={12} color="#10b981" /><span style={{ color: '#10b981', fontSize: 12 }}>Connected</span></>
              ) : (
                <><WifiOff size={12} color="#ef4444" /><span style={{ color: '#ef4444', fontSize: 12 }}>Connection failed</span></>
              )}
            </div>
          </div>
        </div>
        <button
          style={{ ...btnSecondary, color: '#ef4444', borderColor: 'rgba(239,68,68,0.2)',
            background: confirmDelete ? 'rgba(239,68,68,0.15)' : undefined }}
          onClick={handleDelete}
        >
          <Trash2 size={14} /> {confirmDelete ? 'Confirm Remove?' : 'Remove'}
        </button>
      </div>

      {/* Sync toggles */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {[
          { key: 'sync_contacts', icon: Users,    label: 'Contacts' },
          { key: 'sync_emails',   icon: Mail,     label: 'Emails' },
          { key: 'sync_meetings', icon: Calendar, label: 'Meetings' },
          { key: 'sync_notes',    icon: FileText, label: 'Notes' },
        ].map(({ key, icon: Icon, label }) => (
          <div key={key} style={{
            display: 'flex', alignItems: 'center', gap: 6, padding: '4px 10px',
            borderRadius: 20, fontSize: 12,
            background: integration[key] ? 'rgba(16,185,129,0.1)' : 'rgba(255,255,255,0.04)',
            color: integration[key] ? '#10b981' : '#6b7280',
            border: `1px solid ${integration[key] ? 'rgba(16,185,129,0.2)' : 'rgba(255,255,255,0.06)'}`,
          }}>
            <Icon size={11} /> {label}
          </div>
        ))}
      </div>

      {/* Actions */}
      <div style={{ display: 'flex', gap: 8 }}>
        <button style={btnSecondary} onClick={handlePing} disabled={pinging}>
          {pinging ? <Loader2 size={13} className="animate-spin" /> : <Wifi size={13} />}
          Test Connection
        </button>
        <button style={btnSecondary} onClick={handleSync} disabled={syncing}>
          {syncing ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
          Sync All Leads
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Queue Stats Bar
// ---------------------------------------------------------------------------
function QueueStats({ stats }) {
  if (!stats) return null;
  return (
    <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
      {[
        { label: 'Pending', value: stats.pending, color: '#f59e0b' },
        { label: 'Done',    value: stats.done,    color: '#10b981' },
        { label: 'Failed',  value: stats.failed,  color: '#ef4444' },
        { label: 'Total',   value: stats.total,   color: '#a855f7' },
      ].map(s => (
        <div key={s.label} style={{
          ...card, padding: '12px 20px', textAlign: 'center', minWidth: 90,
        }}>
          <div style={{ fontSize: 22, fontWeight: 700, color: s.color }}>{s.value ?? 0}</div>
          <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 2 }}>{s.label}</div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Tab
// ---------------------------------------------------------------------------
const SDRCRMSyncTab = () => {
  const [integrations, setIntegrations] = useState([]);
  const [queueStats, setQueueStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [connectingProvider, setConnectingProvider] = useState(null);
  const [retrying, setRetrying] = useState(false);
  const { toast } = useToast();

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [intRes, qRes] = await Promise.all([
        listCrmIntegrations(),
        getCrmQueueStatus(),
      ]);
      setIntegrations(intRes?.data || intRes || []);
      setQueueStats(qRes?.data || qRes);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const connectedProviders = integrations.map(i => i.provider);
  const availableProviders = Object.keys(PROVIDERS).filter(p => !connectedProviders.includes(p));

  const handleRetry = async () => {
    setRetrying(true);
    try {
      const res = await retryCrmFailed();
      toast({ title: `${res?.requeued ?? 0} items re-queued` });
      fetchAll();
    } catch {
      toast({ title: 'Retry failed', variant: 'destructive' });
    } finally {
      setRetrying(false);
    }
  };

  return (
    <div style={{ padding: '0 4px', display: 'flex', flexDirection: 'column', gap: 28 }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h2 style={{ color: '#fff', fontSize: 22, fontWeight: 700, margin: 0 }}>
            CRM & System Sync
          </h2>
          <p style={{ color: '#9ca3af', fontSize: 14, margin: '6px 0 0' }}>
            Automatically save leads, emails, and meetings to your CRM.
          </p>
        </div>
        <button style={btnPrimary} onClick={fetchAll} disabled={loading}>
          {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
          Refresh
        </button>
      </div>

      {/* Queue Stats */}
      {queueStats && (
        <div>
          <div style={{ color: '#9ca3af', fontSize: 13, marginBottom: 10, display: 'flex', alignItems: 'center', gap: 6 }}>
            <Database size={13} /> Sync Queue Status
          </div>
          <QueueStats stats={queueStats} />
          {queueStats.failed > 0 && (
            <button style={{ ...btnSecondary, marginTop: 10 }} onClick={handleRetry} disabled={retrying}>
              {retrying ? <Loader2 size={13} className="animate-spin" /> : <Zap size={13} />}
              Retry {queueStats.failed} Failed Items
            </button>
          )}
        </div>
      )}

      {/* Connected Integrations */}
      <div>
        <div style={{ color: '#9ca3af', fontSize: 13, marginBottom: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
          <CheckCircle2 size={13} /> Connected CRMs
        </div>

        {loading ? (
          <div style={{ color: '#6b7280', display: 'flex', gap: 8, alignItems: 'center', padding: 20 }}>
            <Loader2 size={16} className="animate-spin" /> Loading...
          </div>
        ) : integrations.length === 0 ? (
          <div style={{ ...card, textAlign: 'center', padding: 40 }}>
            <WifiOff size={32} color="#4b5563" style={{ margin: '0 auto 12px' }} />
            <div style={{ color: '#9ca3af', fontSize: 15 }}>No CRM connected yet</div>
            <div style={{ color: '#6b7280', fontSize: 13, marginTop: 6 }}>
              Connect a CRM below to start syncing automatically.
            </div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {integrations.map(i => (
              <IntegrationCard key={i.id} integration={i} onDelete={fetchAll} onRefresh={fetchAll} />
            ))}
          </div>
        )}
      </div>

      {/* Connect New CRM */}
      {availableProviders.length > 0 && (
        <div>
          <div style={{ color: '#9ca3af', fontSize: 13, marginBottom: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
            <Plus size={13} /> Connect a CRM
          </div>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            {availableProviders.map(provider => {
              const cfg = PROVIDERS[provider];
              return (
                <button
                  key={provider}
                  onClick={() => setConnectingProvider(provider)}
                  style={{
                    ...card,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 12,
                    padding: '16px 20px',
                    minWidth: 180,
                    border: `1px solid ${cfg.color}30`,
                    transition: 'all 0.2s',
                    background: cfg.bg,
                  }}
                >
                  <span style={{ fontSize: 24 }}>{cfg.logo}</span>
                  <div style={{ textAlign: 'left' }}>
                    <div style={{ color: '#fff', fontWeight: 600, fontSize: 15 }}>{cfg.label}</div>
                    <div style={{ color: cfg.color, fontSize: 12, marginTop: 2 }}>Click to connect</div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Connect Modal */}
      {connectingProvider && (
        <ConnectModal
          provider={connectingProvider}
          onClose={() => setConnectingProvider(null)}
          onSaved={fetchAll}
        />
      )}
    </div>
  );
};

export default SDRCRMSyncTab;
