import React, { useEffect, useMemo, useState } from 'react';
import { Helmet } from 'react-helmet';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useAgents } from '@/hooks/useAgents';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { useToast } from '@/components/ui/use-toast';
import {
  Loader2, Key, ShieldCheck, AlertTriangle, CheckCircle2, XCircle,
  Send, Trash2, ChevronLeft, ChevronRight, ChevronDown, RefreshCw, DollarSign, Gauge,
  Inbox, Building2, Save, Plus, Info, Settings, Globe, Search, Clock, CreditCard, Pencil
} from 'lucide-react';
import DashboardNavbar from '@/components/common/DashboardNavbar';
import { getAdminNavItems } from '@/utils/adminNavItems';
import { useAuth } from '@/contexts/AuthContext';
import adminApiKeysService from '@/services/adminApiKeysService';
import { ResetLogsTab } from '@/components/admin/ResetLogsTab';
// Tab panels live in their own files; this page keeps the state, data loading
// and modals that they all share.
import {
  GRADIENT_BG, CARD_CLASS, ROW_CLASS, ProviderLogo, PROVIDER_OPTIONS,
  formatTokens, StatCard, REQUEST_STATUS_META,
} from '@/components/admin/apiKeysShared';
import PlatformTab from '@/components/admin/PlatformKeysTab';
import OverviewTab from '@/components/admin/OverviewTab';
import KeysTab from '@/components/admin/CompanyKeysTab';
import PricingTab from '@/components/admin/PricingTab';
import QuotasTab from '@/components/admin/QuotasTab';
import RequestsTab from '@/components/admin/RequestsTab';

const CompanyPicker = ({ value, onChange, disabled, lockedLabel }) => {
  const [search, setSearch] = useState('');
  const [options, setOptions] = useState([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const t = setTimeout(async () => {
      try {
        const res = await adminApiKeysService.listCompaniesSimple(search);
        setOptions(res.companies || []);
      } catch { /* empty */ }
    }, 200);
    return () => clearTimeout(t);
  }, [search]);

  const selected = options.find(c => c.id === Number(value));
  return (
    <div className="relative">
      <div className="relative">
        <Search className="w-4 h-4 text-white/40 absolute left-3 top-1/2 -translate-y-1/2" />
        <Input
          disabled={disabled}
          className="bg-[#1a1333] border-[#3a295a] text-white pl-9"
          placeholder={disabled ? '' : 'Search company by name...'}
          value={disabled && lockedLabel ? lockedLabel : selected ? `${selected.name} (#${selected.id})` : search}
          onChange={(e) => { setSearch(e.target.value); onChange(''); }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 200)}
        />
      </div>
      {open && !disabled && options.length > 0 && (
        <div className="absolute z-20 mt-1 w-full max-h-56 overflow-y-auto bg-[#1a1333] border border-[#3a295a] rounded-lg shadow-xl">
          {options.map(c => (
            <button
              key={c.id}
              type="button"
              className="w-full text-left px-3 py-2 hover:bg-violet-500/20 text-white text-sm border-b border-[#2d2342] last:border-b-0"
              onMouseDown={(e) => { e.preventDefault(); onChange(String(c.id)); setSearch(''); setOpen(false); }}
            >
              <span className="font-medium">{c.name}</span>
              <span className="text-white/40 text-xs ml-2">#{c.id} • {c.email}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

// -------------------- Main Page --------------------
const SuperAdminApiKeysPage = () => {
  const navigate = useNavigate();
  const { logout, user } = useAuth();
  const handleLogout = async () => {
    try {
      await logout();
      navigate('/login');
    } catch (error) {
      console.error('Logout error:', error);
    }
  };
  const { toast } = useToast();

  // The agent catalogue, from the DB. Fetched once here and threaded into the
  // tabs as `agentOptions` so every dropdown on this page stays in sync with the
  // Agent table — adding an agent needs no change to this file.
  const { agents: agentOptions } = useAgents({ includeInactive: true });

  // Tab lives in the URL so the sidebar can drive it. Switching tabs is then a
  // same-route change: this page stays mounted and only the panel swaps, which
  // is what stops every sidebar click from looking like a page reload.
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = searchParams.get('tab') || 'overview';
  const setActiveTab = (tab) => setSearchParams({ tab }, { replace: false });
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState({});
  const [keys, setKeys] = useState([]);
  const [pricing, setPricing] = useState([]);
  const [quotas, setQuotas] = useState([]);
  const [requests, setRequests] = useState([]);
  const [keyEvents, setKeyEvents] = useState([]);
  const [platformKeys, setPlatformKeys] = useState([]);
  const [savingProvider, setSavingProvider] = useState(null);
  const [revokingProvider, setRevokingProvider] = useState(null);

  const [keyFilter, setKeyFilter] = useState({ mode: 'managed' });
  const [quotaFilter, setQuotaFilter] = useState({});
  const [requestFilter, setRequestFilter] = useState({});

  const [assignModal, setAssignModal] = useState({ open: false, replacingKey: null, prefillRequest: null });
  const [assignForm, setAssignForm] = useState({ company_id: '', agent_name: 'frontline_agent', provider: 'openai', api_key: '', reset_tokens: true, managed_tokens: '', renewal_period: 'none', duration_months: '', reset_interval_days: '7' });
  const [approveModal, setApproveModal] = useState({ open: false, request: null, key_cost: '', service_charge: '', discount_pct: '0', admin_note: '', sync_global_pricing: false });
  const [rejectModal, setRejectModal] = useState({ open: false, request: null, note: '' });
  // Edit a request's price/duration/note before payment (pending / payment_pending).
  const [editModal, setEditModal] = useState({ open: false, request: null, key_cost: '', service_charge: '', discount_pct: '0', preferred_duration: 'monthly', admin_note: '' });
  const [editing, setEditing] = useState(false);
  const [adjustModal, setAdjustModal] = useState({ open: false, quota: null, action: '', value: '' });
  const [confirmDialog, setConfirmDialog] = useState({ open: false, title: '', description: '', onConfirm: null });

  const [submitting, setSubmitting] = useState(false);
  const [savingAgent, setSavingAgent] = useState(null);

  const loadAll = async ({ silent = false } = {}) => {
    if (!silent) setLoading(true);
    try {
      const [o, k, p, q, r, pk, ev] = await Promise.all([
        adminApiKeysService.getOverview(),
        adminApiKeysService.listAllKeys(keyFilter),
        adminApiKeysService.listPricing(),
        adminApiKeysService.listQuotas(quotaFilter),
        adminApiKeysService.listRequests(requestFilter),
        adminApiKeysService.listPlatformKeys(),
        // Recorded key lifecycle events — the timeline used to guess expiries
        // from the current key row, which could only ever show the latest one.
        adminApiKeysService.listKeyEvents({ limit: 200 }).catch(() => ({ events: [] })),
      ]);
      setStats(o.stats || {});
      setKeys(k.keys || []);
      setPricing(p.pricing || []);
      setQuotas(q.quotas || []);
      setRequests(r.requests || []);
      setPlatformKeys(pk.platform_keys || []);
      setKeyEvents(ev.events || []);
    } catch (e) {
      if (!silent) toast({ title: 'Load failed', description: String(e.message || e), variant: 'destructive' });
    } finally {
      if (!silent) setLoading(false);
    }
  };

  const savePlatformKey = async (provider, apiKey, onDone) => {
    setSavingProvider(provider);
    try {
      await adminApiKeysService.upsertPlatformKey(provider, apiKey);
      toast({ title: 'Platform key saved', description: `${provider.toUpperCase()} key is now active for all companies.` });
      const pk = await adminApiKeysService.listPlatformKeys();
      setPlatformKeys(pk.platform_keys || []);
      loadAll();
      onDone?.();
    } catch (e) {
      toast({ title: 'Save failed', description: String(e.message || e), variant: 'destructive' });
    } finally { setSavingProvider(null); }
  };

  const handleRevokePlatformKey = async (provider) => {
    setRevokingProvider(provider);
    try {
      await adminApiKeysService.revokePlatformKey(provider);
      toast({ title: 'Key removed', description: `${provider.toUpperCase()} platform key has been revoked.`, variant: 'destructive' });
      const pk = await adminApiKeysService.listPlatformKeys();
      setPlatformKeys(pk.platform_keys || []);
      loadAll();
    } catch (e) {
      toast({ title: 'Remove failed', description: String(e.message || e), variant: 'destructive' });
    } finally { setRevokingProvider(null); }
  };

  useEffect(() => {
    loadAll();

    // Auto-refresh every 30 seconds (silent — no spinner, no error toast)
    const interval = setInterval(() => loadAll({ silent: true }), 30_000);

    // Refresh immediately when user tabs back to this page
    const onVisible = () => { if (document.visibilityState === 'visible') loadAll({ silent: true }); };
    document.addEventListener('visibilitychange', onVisible);

    return () => {
      clearInterval(interval);
      document.removeEventListener('visibilitychange', onVisible);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const reloadKeys = async () => {
    try {
      const k = await adminApiKeysService.listAllKeys(keyFilter);
      setKeys(k.keys || []);
    } catch (e) { toast({ title: 'Failed', description: String(e.message || e), variant: 'destructive' }); }
  };
  const reloadQuotas = async () => {
    try {
      const q = await adminApiKeysService.listQuotas(quotaFilter);
      setQuotas(q.quotas || []);
    } catch (e) { toast({ title: 'Failed', description: String(e.message || e), variant: 'destructive' }); }
  };
  const reloadRequests = async () => {
    try {
      const [r, ev] = await Promise.all([
        adminApiKeysService.listRequests(requestFilter),
        adminApiKeysService.listKeyEvents({ limit: 200 }).catch(() => ({ events: [] })),
      ]);
      setRequests(r.requests || []);
      setKeyEvents(ev.events || []);
    } catch (e) { toast({ title: 'Failed', description: String(e.message || e), variant: 'destructive' }); }
  };

  useEffect(() => { const t = setTimeout(reloadKeys, 300); return () => clearTimeout(t); /* eslint-disable-next-line */ }, [keyFilter]);
  useEffect(() => { const t = setTimeout(reloadQuotas, 300); return () => clearTimeout(t); /* eslint-disable-next-line */ }, [quotaFilter]);
  useEffect(() => { const t = setTimeout(reloadRequests, 300); return () => clearTimeout(t); /* eslint-disable-next-line */ }, [requestFilter]);

  // Default managed-token grant when nothing else supplies one. A key saved
  // with 0 tokens is unusable (every call hard-blocks immediately), so the
  // form starts from a sane figure and submit refuses 0 outright.
  const DEFAULT_MANAGED_TOKENS = '50000';

  const openAssign = (existingOrRequest, prefill = null) => {
    if (prefill) {
      const duration = prefill.preferred_duration || 'monthly';
      const p = pricing.find(x => x.agent_name === prefill.agent_name);
      const defaultTokens = p?.managed_key_tokens ? String(p.managed_key_tokens) : DEFAULT_MANAGED_TOKENS;
      setAssignForm({
        company_id: prefill.company_id,
        agent_name: prefill.agent_name,
        provider: prefill.provider || 'openai',
        api_key: '',
        reset_tokens: true,
        managed_tokens: defaultTokens,
        renewal_period: duration,
        duration_months: duration === 'yearly' ? '12' : duration === 'monthly' ? '1' : '',
      });
      setAssignModal({ open: true, replacingKey: null, prefillRequest: prefill });
    } else if (existingOrRequest) {
      const hasUsage = existingOrRequest.quota?.managed_used_tokens > 0;
      setAssignForm({
        company_id: existingOrRequest.company_id,
        agent_name: existingOrRequest.agent_name,
        provider: existingOrRequest.provider || 'openai',
        api_key: '',
        reset_tokens: !hasUsage,
        managed_tokens: existingOrRequest.quota?.managed_included_tokens > 0
          ? String(existingOrRequest.quota.managed_included_tokens)
          : DEFAULT_MANAGED_TOKENS,
        renewal_period: existingOrRequest.renewal_period || 'none',
        duration_months: '',
        reset_interval_days: String(existingOrRequest.reset_interval_days || 7),
      });
      setAssignModal({ open: true, replacingKey: existingOrRequest, prefillRequest: null });
    } else {
      setAssignForm({ company_id: '', agent_name: 'frontline_agent', provider: 'openai', api_key: '', reset_tokens: true, managed_tokens: DEFAULT_MANAGED_TOKENS, renewal_period: 'none', duration_months: '', reset_interval_days: '7' });
      setAssignModal({ open: true, replacingKey: null, prefillRequest: null });
    }
  };

  const submitAssign = async () => {
    if (!assignForm.company_id || !assignForm.api_key) {
      toast({ title: 'Missing fields', description: 'Company and API key are required.', variant: 'destructive' });
      return;
    }
    // A key with a 0-token grant is dead on arrival: resolve_for_call
    // hard-blocks every request the moment the quota is exhausted, so the
    // company would get a key it can never use. Refuse it here.
    const tokensRaw = String(assignForm.managed_tokens ?? '').trim();
    const tokensNum = Number(tokensRaw);
    if (tokensRaw === '' || !Number.isFinite(tokensNum) || tokensNum <= 0) {
      toast({
        title: 'Tokens required',
        description: 'Enter a token amount greater than 0 — a key with 0 tokens cannot make any calls.',
        variant: 'destructive',
      });
      return;
    }
    setSubmitting(true);
    try {
      const payload = {
        company_id: Number(assignForm.company_id),
        agent_name: assignForm.agent_name,
        provider: assignForm.provider,
        api_key: assignForm.api_key,
        reset_tokens: assignForm.reset_tokens,
        renewal_period: assignForm.renewal_period,
        reset_interval_days: Number(assignForm.reset_interval_days) || 7,
      };
      payload.managed_tokens = tokensRaw;
      if (assignForm.duration_months.trim() !== '') payload.duration_months = Number(assignForm.duration_months);
      if (assignModal.prefillRequest) payload.request_id = assignModal.prefillRequest.id;
      await adminApiKeysService.assignManagedKey(payload);
      toast({ title: 'Key assigned', description: 'Company can now use this managed key.' });
      setAssignModal({ open: false, replacingKey: null, prefillRequest: null });
      loadAll();
    } catch (e) {
      toast({ title: 'Assign failed', description: String(e.message || e), variant: 'destructive' });
    } finally { setSubmitting(false); }
  };

  const revokeOne = (k) => {
    setConfirmDialog({
      open: true,
      title: `Revoke ${k.mode === 'managed' ? 'Managed' : 'BYOK'} Key`,
      description: `Remove the ${k.provider} key for ${k.company_name} — ${k.agent_label}? The company will be notified and lose access immediately.`,
      onConfirm: async () => {
        try {
          await adminApiKeysService.revokeKey(k.id);
          toast({ title: 'Key revoked', description: `${k.company_name} has been notified.` });
          reloadKeys(); loadAll();
        } catch (e) {
          toast({ title: 'Revoke failed', description: String(e.message || e), variant: 'destructive' });
        }
      },
    });
  };

  const savePricing = async (agentName, draft) => {
    setSavingAgent(agentName);
    try {
      await adminApiKeysService.updatePricing(agentName, {
        monthly_flat_usd: draft.monthly_flat_usd,
        service_charge_usd: draft.service_charge_usd,
        free_tokens_on_purchase: Number(draft.free_tokens_on_purchase),
        managed_key_tokens: Number(draft.managed_key_tokens),
        yearly_discount_pct: Number(draft.yearly_discount_pct),
        monthly_discount_pct: Number(draft.monthly_discount_pct),
      });
      toast({ title: 'Pricing saved' });
      const p = await adminApiKeysService.listPricing();
      setPricing(p.pricing || []);
    } catch (e) {
      toast({ title: 'Save failed', description: String(e.message || e), variant: 'destructive' });
    } finally { setSavingAgent(null); }
  };

  const openAdjust = (quota, action) => {
    const defaultVal = action === 'reset' || action === 'reset_managed'
      ? ''
      : action === 'set_managed'
        ? String(quota?.managed_included_tokens ?? 0)
        : action === 'set_included'
          ? String(quota?.included_tokens ?? 0)
          : '1000000';
    setAdjustModal({
      open: true, quota, action, value: defaultVal,
      reset_interval_days: String(quota?.reset_interval_days ?? 7),
      recompute_next: false,
    });
  };

  const submitAdjust = async () => {
    const { quota, action, value } = adjustModal;
    // Reset schedule is edited alongside the token limit; only send it when the
    // admin actually changed the interval (or asked to restart the cycle), so a
    // plain token edit does not silently touch the schedule.
    const newInterval = Math.max(1, Math.min(365, Number(adjustModal.reset_interval_days) || 0));
    const intervalChanged =
      action === 'set_managed' &&
      quota?.key_id &&
      quota?.key_mode === 'managed' &&
      newInterval >= 1 &&
      (newInterval !== Number(quota.reset_interval_days ?? 7) || adjustModal.recompute_next);
    setSubmitting(true);
    try {
      const noValueActions = ['reset', 'reset_managed'];
      const payload = noValueActions.includes(action) ? { action } : { action, value: Number(value) };
      await adminApiKeysService.adjustQuota(quota.id, payload);
      if (intervalChanged) {
        await adminApiKeysService.updateResetSchedule({
          key_id: quota.key_id,
          reset_interval_days: newInterval,
          recompute_next: !!adjustModal.recompute_next,
        });
      }
      toast({
        title: 'Quota updated',
        description: intervalChanged ? `Reset schedule set to every ${newInterval} day(s).` : undefined,
      });
      setAdjustModal({ open: false, quota: null, action: '', value: '', reset_interval_days: '7', recompute_next: false });
      reloadQuotas(); loadAll();
    } catch (e) {
      toast({ title: 'Adjust failed', description: String(e.message || e), variant: 'destructive' });
    } finally { setSubmitting(false); }
  };

  const submitApprove = async () => {
    setSubmitting(true);
    try {
      const discPct = Math.min(100, Math.max(0, parseFloat(approveModal.discount_pct) || 0));
      const rawKey = Number(approveModal.key_cost) || 0;
      const rawSvc = Number(approveModal.service_charge) || 0;
      const multiplier = 1 - discPct / 100;
      await adminApiKeysService.approveRequest(approveModal.request.id, {
        key_cost: parseFloat((rawKey * multiplier).toFixed(2)),
        service_charge: parseFloat((rawSvc * multiplier).toFixed(2)),
        discount_pct: discPct,
        admin_note: approveModal.admin_note,
        sync_global_pricing: approveModal.sync_global_pricing,
      });
      toast({
        title: 'Request approved',
        description: approveModal.sync_global_pricing
          ? 'Company notified to complete payment. Global pricing updated.'
          : 'Company notified to complete payment.',
      });
      setApproveModal({ open: false, request: null, key_cost: '', service_charge: '', discount_pct: '0', admin_note: '', sync_global_pricing: false });
      reloadRequests(); loadAll();
    } catch (e) {
      toast({ title: 'Approve failed', description: String(e.message || e), variant: 'destructive' });
    } finally { setSubmitting(false); }
  };

  const submitEdit = async () => {
    setEditing(true);
    try {
      const discPct = Math.min(100, Math.max(0, parseFloat(editModal.discount_pct) || 0));
      const rawKey = Number(editModal.key_cost) || 0;
      const rawSvc = Number(editModal.service_charge) || 0;
      const multiplier = 1 - discPct / 100;
      await adminApiKeysService.editRequest(editModal.request.id, {
        key_cost: parseFloat((rawKey * multiplier).toFixed(2)),
        service_charge: parseFloat((rawSvc * multiplier).toFixed(2)),
        discount_pct: discPct,
        preferred_duration: editModal.preferred_duration,
        admin_note: editModal.admin_note,
        sync_global_pricing: editModal.sync_global_pricing,
      });
      toast({
        title: 'Request updated',
        description: [
          editModal.request.status === 'payment_pending' ? 'Company notified of the new amount due.' : 'Changes saved.',
          editModal.sync_global_pricing ? 'Global pricing updated.' : '',
        ].filter(Boolean).join(' '),
      });
      setEditModal({ open: false, request: null, key_cost: '', service_charge: '', discount_pct: '0', preferred_duration: 'monthly', admin_note: '', sync_global_pricing: false });
      reloadRequests(); loadAll();
    } catch (e) {
      toast({ title: 'Update failed', description: String(e.message || e), variant: 'destructive' });
    } finally { setEditing(false); }
  };

  const submitReject = async () => {
    setSubmitting(true);
    try {
      await adminApiKeysService.rejectRequest(rejectModal.request.id, rejectModal.note);
      toast({ title: 'Request rejected' });
      setRejectModal({ open: false, request: null, note: '' });
      reloadRequests(); loadAll();
    } catch (e) {
      toast({ title: 'Reject failed', description: String(e.message || e), variant: 'destructive' });
    } finally { setSubmitting(false); }
  };

  return (
    <>
      <Helmet><title>Super Admin — API Keys & Pricing</title></Helmet>
      <div className="min-h-screen overflow-x-hidden" style={{ background: GRADIENT_BG }}>
        <DashboardNavbar
          icon={Settings}
          title="API Keys & Pricing"
          subtitle="Control plane for keys, pricing, quotas & requests"
          user={user}
          userRole="Admin"
          onLogout={handleLogout}
          showNavTabs
          activeSection="admin-api-keys"
          navItems={getAdminNavItems(navigate, { pendingRequests: stats.pending_requests || 0 })}
        />

        <div className="container mx-auto px-4 py-8 max-w-7xl">
          {/* Page title lives in the navbar above — repeating it here just
              pushed the content down. */}

          <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
            {/* Tab strip removed — the sidebar drives ?tab= instead. */}

            <TabsContent value="platform">
              {loading ? <div className="flex justify-center py-20"><Loader2 className="w-8 h-8 animate-spin text-violet-400" /></div>
                : <PlatformTab platformKeys={platformKeys} onSave={savePlatformKey} onRevoke={handleRevokePlatformKey} savingProvider={savingProvider} revokingProvider={revokingProvider} agentOptions={agentOptions} />}
            </TabsContent>
            <TabsContent value="overview">
              {loading ? <div className="flex justify-center py-20"><Loader2 className="w-8 h-8 animate-spin text-violet-400" /></div> : <OverviewTab stats={stats} />}
            </TabsContent>
            <TabsContent value="keys">
              <KeysTab
                keys={keys}
                agentOptions={agentOptions}
                onAssign={openAssign}
                onRevoke={revokeOne}
                onAdjustQuota={(q, key) => {
                  openAdjust({
                    id: q.id,
                    company_name: key.company_name,
                    agent_label: key.agent_label,
                    included_tokens: q.included_tokens,
                    used_tokens: q.used_tokens,
                    managed_included_tokens: q.managed_included_tokens,
                    managed_used_tokens: q.managed_used_tokens,
                    // Needed to edit the weekly reset schedule from this modal.
                    key_id: key.id,
                    key_mode: key.mode,
                    reset_interval_days: key.reset_interval_days ?? 7,
                    next_reset_at: q.next_reset_at,
                  }, 'set_managed');
                }}
                filter={keyFilter}
                setFilter={setKeyFilter}
                onRefresh={reloadKeys}
                loading={loading}
              />
            </TabsContent>
            <TabsContent value="pricing">
              <PricingTab pricing={pricing} onSave={savePricing} savingAgent={savingAgent} />
            </TabsContent>
            <TabsContent value="quotas">
              <QuotasTab quotas={quotas} onAdjust={openAdjust} filter={quotaFilter} setFilter={setQuotaFilter} onRefresh={reloadQuotas} loading={loading} agentOptions={agentOptions} />
            </TabsContent>
            <TabsContent value="reset-logs">
              <ResetLogsTab agentOptions={agentOptions} />
            </TabsContent>
            <TabsContent value="requests">
              <RequestsTab
                requests={requests}
                keyEvents={keyEvents}
                pricing={pricing}
                onApprove={(r) => {
                  // Prefer the request's own price snapshot (an admin may have
                  // already edited this request) and only fall back to global
                  // pricing when the request carries no price yet. Reading
                  // global pricing unconditionally meant an edited request —
                  // or any agent whose global pricing is still 0 — opened the
                  // approve dialog showing 0.00 and discarded the real amount.
                  const p = pricing.find(x => x.agent_name === r.agent_name);
                  // 0 counts as unpriced: requests are created with 0.00, not
                  // null, so a `!= null` test would pin the modal to 0 and hide
                  // the configured global price. Matches the warning banner below.
                  const hasSnapshot =
                    Number(r.key_cost_snapshot ?? 0) > 0 || Number(r.service_charge_snapshot ?? 0) > 0;
                  let keyCost;
                  let svcCharge;
                  let discPct;
                  if (hasSnapshot) {
                    // Snapshots are stored already-discounted (see submitEdit),
                    // so they are used as-is — re-applying the discount here
                    // would deduct it twice.
                    keyCost = Number(r.key_cost_snapshot ?? 0).toFixed(2);
                    svcCharge = Number(r.service_charge_snapshot ?? 0).toFixed(2);
                    discPct = parseFloat(r.discount_pct_snapshot ?? 0);
                  } else {
                    const monthlyDiscountPct = parseFloat(p?.monthly_discount_pct || 0);
                    const monthlyKey = parseFloat(p?.monthly_flat_usd || 0);
                    const monthlySvc = parseFloat(p?.service_charge_usd || 0);
                    keyCost = (monthlyKey * (1 - monthlyDiscountPct / 100)).toFixed(2);
                    svcCharge = (monthlySvc * (1 - monthlyDiscountPct / 100)).toFixed(2);
                    discPct = monthlyDiscountPct;
                  }
                  setApproveModal({ open: true, request: r, key_cost: keyCost, service_charge: svcCharge, discount_pct: String(discPct), admin_note: r.admin_note || '', sync_global_pricing: false });
                }}
                onAssignKey={(r) => openAssign(null, r)}
                onReject={(r) => setRejectModal({ open: true, request: r, note: '' })}
                onEdit={(r) => {
                  // Prefill from the request's current snapshot; fall back to
                  // pricing config when the request has no real price yet.
                  // A snapshot of 0 counts as "unpriced" — requests are created
                  // with 0.00 rather than null, so a `!= null` test made every
                  // fresh request show 0 and hid the configured global price.
                  const p = pricing.find(x => x.agent_name === r.agent_name);
                  const hasSnapshot =
                    Number(r.key_cost_snapshot ?? 0) > 0 || Number(r.service_charge_snapshot ?? 0) > 0;
                  const keyCost = hasSnapshot ? (r.key_cost_snapshot ?? 0) : parseFloat(p?.monthly_flat_usd || 0);
                  const svcCharge = hasSnapshot ? (r.service_charge_snapshot ?? 0) : parseFloat(p?.service_charge_usd || 0);
                  const discPct = hasSnapshot
                    ? (r.discount_pct_snapshot ?? 0)
                    : parseFloat(p?.monthly_discount_pct || 0);
                  setEditModal({
                    open: true, request: r,
                    key_cost: String(keyCost),
                    service_charge: String(svcCharge),
                    discount_pct: String(discPct),
                    preferred_duration: r.preferred_duration || 'monthly',
                    admin_note: r.admin_note || '',
                    sync_global_pricing: false,
                  });
                }}
                filter={requestFilter}
                setFilter={setRequestFilter}
                onRefresh={reloadRequests}
                loading={loading}
              />
            </TabsContent>
          </Tabs>
        </div>
      </div>

      {/* Assign Managed Key Modal */}
      <Dialog open={assignModal.open} onOpenChange={(o) => !o && setAssignModal({ open: false, replacingKey: null, prefillRequest: null })}>
        <DialogContent className="bg-[#120d22] border border-[#2d2342] text-white sm:max-w-3xl w-full max-h-[90vh] overflow-y-auto no-scrollbar">
          <DialogHeader className="pb-2 border-b border-white/8">
            <DialogTitle className="flex items-center gap-2">
              <Key className="w-5 h-5 text-violet-400" />
              {assignModal.replacingKey ? 'Replace Managed Key' : assignModal.prefillRequest ? 'Approve & Assign Key' : 'Assign Managed Key'}
            </DialogTitle>
            <DialogDescription className="text-white/50 text-xs">
              Encrypted on save — only a masked preview is visible afterward.
            </DialogDescription>
          </DialogHeader>

          <div className=" space-y-4">

            {/* Row 1 — 2 columns: Company+Agent | API Key+Provider */}
            <div className="grid grid-cols-2 gap-x-6 gap-y-4">
              {/* COL 1 — Company + Agent */}
              <div className="space-y-4">
                <div>
                  <Label className="text-white/60 text-xs uppercase tracking-wider">Company</Label>
                  <div className="mt-1">
                    <CompanyPicker
                      value={assignForm.company_id}
                      onChange={(id) => setAssignForm({ ...assignForm, company_id: id })}
                      disabled={!!assignModal.replacingKey || !!assignModal.prefillRequest}
                      lockedLabel={(assignModal.replacingKey?.company_name) || (assignModal.prefillRequest?.company_name)}
                    />
                  </div>
                </div>
                <div>
                  <Label className="text-white/60 text-xs uppercase tracking-wider">Agent</Label>
                  <Select
                    value={assignForm.agent_name}
                    onValueChange={(v) => setAssignForm({ ...assignForm, agent_name: v })}
                    disabled={!!assignModal.replacingKey || !!assignModal.prefillRequest}
                  >
                    <SelectTrigger className="bg-[#1a1333] border-[#3a295a] text-white mt-1"><SelectValue /></SelectTrigger>
                    <SelectContent className="bg-[#1a1333] border-[#3a295a] text-white">
                      {agentOptions.map(a => <SelectItem key={a.value} value={a.value}>{a.label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              {/* COL 2 — Provider + API Key */}
              <div className="space-y-4">
                <div>
                  <Label className="text-white/60 text-xs uppercase tracking-wider">Provider</Label>
                  <Select value={assignForm.provider} onValueChange={(v) => setAssignForm({ ...assignForm, provider: v })}>
                    <SelectTrigger className="bg-[#1a1333] border-[#3a295a] text-white mt-1"><SelectValue /></SelectTrigger>
                    <SelectContent className="bg-[#1a1333] border-[#3a295a] text-white">
                      {PROVIDER_OPTIONS.map(p => <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-white/60 text-xs uppercase tracking-wider">API Key</Label>
                  <Input
                    type="password" autoComplete="off" placeholder="sk-..."
                    className="bg-[#1a1333] border-[#3a295a] text-white mt-1 font-mono"
                    value={assignForm.api_key}
                    onChange={(e) => setAssignForm({ ...assignForm, api_key: e.target.value })}
                  />
                </div>
              </div>
            </div>

            {/* Replace key options — full width */}
            {assignModal.replacingKey && (
              <div className="grid grid-cols-2 gap-x-6">
                <div
                  className={`flex items-start gap-3 rounded-lg border p-3 cursor-pointer transition-colors ${
                    assignForm.reset_tokens ? 'border-amber-500/40 bg-amber-500/8' : 'border-white/10 bg-white/3 hover:border-white/20'
                  }`}
                  onClick={() => setAssignForm((f) => ({ ...f, reset_tokens: !f.reset_tokens }))}
                >
                  <div className={`mt-0.5 w-4 h-4 rounded border flex items-center justify-center shrink-0 transition-colors ${
                    assignForm.reset_tokens ? 'bg-amber-500 border-amber-500' : 'border-white/30'
                  }`}>
                    {assignForm.reset_tokens && (
                      <svg className="w-2.5 h-2.5 text-white" fill="none" viewBox="0 0 12 12">
                        <path d="M2 6l3 3 5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    )}
                  </div>
                  <div>
                    <p className="text-sm text-white font-medium">Reset token usage to 0</p>
                    <p className="text-xs text-white/50 mt-0.5">
                      {assignModal.replacingKey.quota?.managed_used_tokens > 0
                        ? `Currently ${formatTokens(assignModal.replacingKey.quota.managed_used_tokens)} used — uncheck to keep history.`
                        : 'No tokens used yet.'}
                    </p>
                  </div>
                </div>
                <div>
                  <Label className="text-white/60 text-xs uppercase tracking-wider">Managed token limit</Label>
                  <Input
                    type="number"
                    placeholder={`Default from pricing: ${formatTokens(pricing.find(p => p.agent_name === assignForm.agent_name)?.managed_key_tokens ?? 0)}`}
                    className="bg-[#1a1333] border-[#3a295a] text-white mt-1"
                    value={assignForm.managed_tokens}
                    onChange={(e) => setAssignForm((f) => ({ ...f, managed_tokens: e.target.value }))}
                  />
                  {assignForm.managed_tokens && !isNaN(parseInt(assignForm.managed_tokens)) && (
                    <p className="text-[10px] text-violet-300/70 mt-1">
                      Will grant: {formatTokens(parseInt(assignForm.managed_tokens))} tokens / week
                    </p>
                  )}
                </div>
              </div>
            )}

            {/* Replace mode — existing key info: full width */}
            {assignModal.replacingKey && (() => {
              const rk = assignModal.replacingKey;
              const renewal = rk.renewal_period;
              const validUntil = rk.valid_until ? new Date(rk.valid_until) : null;
              const daysLeft = validUntil ? Math.ceil((validUntil - new Date()) / (1000 * 60 * 60 * 24)) : null;
              const urgent = daysLeft !== null && daysLeft <= 7;
              return (
                <div className="grid grid-cols-3 gap-4 p-4 bg-[#1a1333] border border-amber-500/20 rounded-xl">
                  <div className="col-span-3 flex items-center gap-2 mb-1">
                    <div className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                    <p className="text-[11px] text-amber-300 uppercase tracking-widest font-semibold">Current Key Info</p>
                  </div>
                  <div className="bg-[#120d22] rounded-lg p-3 border border-[#2d2342]">
                    <p className="text-[10px] text-white/40 uppercase tracking-wider mb-1">Billing Plan</p>
                    <p className="text-sm text-violet-300 font-semibold capitalize">
                      {!renewal || renewal === 'none' ? 'One-time' : renewal}
                    </p>
                    <p className="text-[10px] text-white/40 mt-0.5">
                      {!renewal || renewal === 'none' ? 'Key never expires' : renewal === 'monthly' ? 'Renews monthly' : 'Renews yearly'}
                    </p>
                  </div>
                  <div className="bg-[#120d22] rounded-lg p-3 border border-[#2d2342]">
                    <p className="text-[10px] text-white/40 uppercase tracking-wider mb-1">Token Reset</p>
                    <p className="text-sm font-semibold">
                      {renewal && renewal !== 'none'
                        ? <span className="text-emerald-400">Every {rk.reset_interval_days || 7} days</span>
                        : <span className="text-white/40">No reset</span>
                      }
                    </p>
                    <p className="text-[10px] text-white/40 mt-0.5">
                      {rk.tokens_per_period > 0 ? `${formatTokens(rk.tokens_per_period)} per reset` : '—'}
                    </p>
                  </div>
                  <div className={`bg-[#120d22] rounded-lg p-3 border ${urgent ? 'border-amber-500/40' : 'border-[#2d2342]'}`}>
                    <p className="text-[10px] text-white/40 uppercase tracking-wider mb-1">Key Valid Until</p>
                    {validUntil ? (
                      <>
                        <p className={`text-sm font-semibold ${urgent ? 'text-amber-400' : 'text-white/70'}`}>
                          {validUntil.toLocaleDateString()}
                        </p>
                        <p className={`text-[10px] mt-0.5 ${urgent ? 'text-amber-400' : 'text-white/40'}`}>
                          {daysLeft > 0 ? `${daysLeft} day${daysLeft !== 1 ? 's' : ''} remaining` : 'Expired'}
                        </p>
                      </>
                    ) : (
                      <p className="text-sm text-white/40 font-semibold">Never expires</p>
                    )}
                  </div>
                </div>
              );
            })()}

            {/* Row 2 — Billing plan: full width */}
            {assignModal.prefillRequest ? (
              <div className="grid grid-cols-3 gap-4 p-4 bg-[#1a1333] border border-violet-500/30 rounded-xl">
                <div className="col-span-3 flex items-center justify-between gap-2 mb-1">
                  <div className="flex items-center gap-2">
                    <div className="w-1.5 h-1.5 rounded-full bg-violet-400" />
                    <p className="text-[11px] text-violet-300 uppercase tracking-widest font-semibold">Requested by company</p>
                  </div>
                  {assignModal.prefillRequest?.preferred_duration && (
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-violet-500/20 border border-violet-500/40 text-violet-300 font-semibold capitalize">
                      Requested: {assignModal.prefillRequest.preferred_duration}
                    </span>
                  )}
                </div>
                <div className="bg-[#120d22] rounded-lg p-3 border border-[#2d2342]">
                  <p className="text-[10px] text-white/40 uppercase tracking-wider mb-1">Billing Plan</p>
                  <p className="text-sm text-violet-300 font-semibold">
                    {assignForm.renewal_period === 'none' ? 'One-time' : assignForm.renewal_period === 'monthly' ? 'Monthly' : 'Yearly'}
                  </p>
                  <p className="text-[10px] text-white/40 mt-0.5">
                    {assignForm.renewal_period === 'none' ? 'Key never expires' : assignForm.renewal_period === 'monthly' ? 'Key expires after 1 month' : 'Key expires after 1 year'}
                  </p>
                </div>
                <div className="bg-[#120d22] rounded-lg p-3 border border-[#2d2342]">
                  <p className="text-[10px] text-white/40 uppercase tracking-wider mb-1">Token Reset</p>
                  <p className="text-sm text-emerald-400 font-semibold">
                    {assignForm.renewal_period === 'none' ? 'No reset' : `Every ${assignForm.reset_interval_days || 7} days`}
                  </p>
                  <p className="text-[10px] text-white/40 mt-0.5">
                    {assignForm.renewal_period === 'none' ? 'One-time tokens only' : 'Automatic recurring reset'}
                  </p>
                </div>
                <div className="bg-[#120d22] rounded-lg p-3 border border-[#2d2342]">
                  <p className="text-[10px] text-white/40 uppercase tracking-wider mb-1">Key Valid For</p>
                  <p className="text-sm text-violet-300 font-semibold">
                    {assignForm.duration_months ? `${assignForm.duration_months} month${parseInt(assignForm.duration_months) !== 1 ? 's' : ''}` : 'Auto'}
                  </p>
                  <p className="text-[10px] text-white/40 mt-0.5">Set by company request</p>
                </div>
                <div className="col-span-3">
                  <Label className="text-white/60 text-xs uppercase tracking-wider">Token Limit (per week)</Label>
                  <Input
                    type="number"
                    placeholder={`Default from pricing: ${formatTokens(pricing.find(p => p.agent_name === assignForm.agent_name)?.managed_key_tokens ?? 0)}`}
                    className="bg-[#1a1333] border-[#3a295a] text-white mt-1"
                    value={assignForm.managed_tokens}
                    onChange={(e) => setAssignForm((f) => ({ ...f, managed_tokens: e.target.value }))}
                  />
                  {assignForm.managed_tokens && !isNaN(parseInt(assignForm.managed_tokens)) && (
                    <p className="text-[10px] text-violet-300/70 mt-1">Will grant: {formatTokens(parseInt(assignForm.managed_tokens))} tokens per reset</p>
                  )}
                </div>
                {/* Reset interval — how often the token quota auto-resets. */}
                <div className="col-span-3">
                  <Label className="text-white/60 text-xs uppercase tracking-wider">Reset every</Label>
                  <div className="flex gap-2 mt-1">
                    <Select
                      value={['7', '10', '14', '30'].includes(String(assignForm.reset_interval_days)) ? String(assignForm.reset_interval_days) : 'custom'}
                      onValueChange={(v) => setAssignForm((f) => ({ ...f, reset_interval_days: v === 'custom' ? '' : v }))}
                    >
                      <SelectTrigger className="bg-[#1a1333] border-[#3a295a] text-white flex-1"><SelectValue /></SelectTrigger>
                      <SelectContent className="bg-[#1a1333] border-[#3a295a] text-white">
                        <SelectItem value="7">7 days (weekly)</SelectItem>
                        <SelectItem value="10">10 days</SelectItem>
                        <SelectItem value="14">14 days</SelectItem>
                        <SelectItem value="30">30 days</SelectItem>
                        <SelectItem value="custom">Custom…</SelectItem>
                      </SelectContent>
                    </Select>
                    {!['7', '10', '14', '30'].includes(String(assignForm.reset_interval_days)) && (
                      <Input
                        type="number" min="1" max="365"
                        placeholder="days"
                        className="bg-[#1a1333] border-[#3a295a] text-white w-24 h-10"
                        value={assignForm.reset_interval_days}
                        onChange={(e) => setAssignForm((f) => ({ ...f, reset_interval_days: e.target.value }))}
                      />
                    )}
                  </div>
                  <p className="text-[10px] text-white/40 mt-1">Tokens auto-reset every {assignForm.reset_interval_days || 7} day(s) while renewal is active.</p>
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-y-3">
                {/* Reset interval — how often the token quota auto-resets. */}
                <div>
                  <Label className="text-white/60 text-xs uppercase tracking-wider">Reset every</Label>
                  <div className="flex gap-2 mt-1">
                    <Select
                      value={['7', '10', '14', '30'].includes(String(assignForm.reset_interval_days)) ? String(assignForm.reset_interval_days) : 'custom'}
                      onValueChange={(v) => setAssignForm((f) => ({ ...f, reset_interval_days: v === 'custom' ? '' : v }))}
                    >
                      <SelectTrigger className="bg-[#1a1333] border-[#3a295a] text-white flex-1"><SelectValue /></SelectTrigger>
                      <SelectContent className="bg-[#1a1333] border-[#3a295a] text-white">
                        <SelectItem value="7">7 days (weekly)</SelectItem>
                        <SelectItem value="10">10 days</SelectItem>
                        <SelectItem value="14">14 days</SelectItem>
                        <SelectItem value="30">30 days</SelectItem>
                        <SelectItem value="custom">Custom…</SelectItem>
                      </SelectContent>
                    </Select>
                    {!['7', '10', '14', '30'].includes(String(assignForm.reset_interval_days)) && (
                      <Input
                        type="number" min="1" max="365"
                        placeholder="days"
                        className="bg-[#1a1333] border-[#3a295a] text-white w-24 h-10"
                        value={assignForm.reset_interval_days}
                        onChange={(e) => setAssignForm((f) => ({ ...f, reset_interval_days: e.target.value }))}
                      />
                    )}
                  </div>
                  <p className="text-[10px] text-white/40 mt-1">Tokens auto-reset every {assignForm.reset_interval_days || 7} day(s) while renewal is active.</p>
                </div>
              </div>
            )}
          </div>
          <DialogFooter className="pt-2 border-t border-white/8">
            <Button variant="outline" className="border-white/15 text-white/80" onClick={() => setAssignModal({ open: false, replacingKey: null, prefillRequest: null })}>Cancel</Button>
            <Button className="bg-violet-600 hover:bg-violet-700 text-white" onClick={submitAssign} disabled={submitting}>
              {submitting && <Loader2 className="w-4 h-4 animate-spin mr-2" />}Assign key
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Adjust Quota Modal */}
      <Dialog open={adjustModal.open} onOpenChange={(o) => !o && setAdjustModal({ ...adjustModal, open: false })}>
        <DialogContent className="bg-[#120d22] border border-[#2d2342] text-white">
          <DialogHeader>
            <DialogTitle>
              {['set_managed', 'reset_managed'].includes(adjustModal.action) ? 'Managed Key Tokens' : 'Free Quota'} — {adjustModal.quota?.company_name}
            </DialogTitle>
            <DialogDescription className="text-white/60">
              {adjustModal.quota?.agent_label}
              {adjustModal.action === 'reset' && ` • Free used: ${formatTokens(adjustModal.quota?.used_tokens)} of ${formatTokens(adjustModal.quota?.included_tokens)}`}
              {adjustModal.action === 'reset_managed' && ` • Managed used: ${formatTokens(adjustModal.quota?.managed_used_tokens)} of ${formatTokens(adjustModal.quota?.managed_included_tokens)}`}
              {adjustModal.action === 'set_managed' && ` • Current: ${formatTokens(adjustModal.quota?.managed_included_tokens)}`}
              {adjustModal.action === 'set_included' && ` • Current: ${formatTokens(adjustModal.quota?.included_tokens)}`}
              {adjustModal.action === 'add_tokens' && ` • Current: ${formatTokens(adjustModal.quota?.included_tokens)}`}
            </DialogDescription>
          </DialogHeader>
          {(adjustModal.action === 'reset') && (
            <p className="text-sm text-white/70 py-2">
              Reset free <span className="font-semibold text-white">used_tokens</span> to 0. Included tokens unchanged.
            </p>
          )}
          {(adjustModal.action === 'reset_managed') && (
            <p className="text-sm text-white/70 py-2">
              Reset managed key <span className="font-semibold text-white">used_tokens</span> to 0. The managed token limit stays the same.
            </p>
          )}
          {['set_included', 'add_tokens', 'set_managed'].includes(adjustModal.action) && (
            <div className="space-y-2 py-2">
              <Label className="text-white/70 text-sm">
                {adjustModal.action === 'add_tokens' ? 'Free tokens to add' : adjustModal.action === 'set_included' ? 'New free token limit' : 'New managed key token limit'}
              </Label>
              <Input
                type="number" className="bg-[#1a1333] border-[#3a295a] text-white"
                value={adjustModal.value}
                onChange={(e) => setAdjustModal({ ...adjustModal, value: e.target.value })}
              />
              <p className="text-[11px] text-white/40">
                {adjustModal.action === 'add_tokens' && `Will set free limit to ${formatTokens((adjustModal.quota?.included_tokens || 0) + Number(adjustModal.value || 0))}`}
                {adjustModal.action === 'set_included' && `Will set free limit to ${formatTokens(Number(adjustModal.value || 0))}`}
                {adjustModal.action === 'set_managed' && `Will set managed token limit to ${formatTokens(Number(adjustModal.value || 0))}`}
              </p>
            </div>
          )}
          {/* Weekly reset schedule — editable here so the admin does not have to
              go to the Reset Logs tab just to change how often tokens refill. */}
          {adjustModal.action === 'set_managed' && adjustModal.quota?.key_id && adjustModal.quota?.key_mode === 'managed' && (
            <div className="space-y-2 py-2 border-t border-[#2d2342] mt-1 pt-3">
              <Label className="text-white/70 text-sm">Reset every (days)</Label>
              <Input
                type="number" min="1" max="365"
                className="bg-[#1a1333] border-[#3a295a] text-white"
                value={adjustModal.reset_interval_days}
                onChange={(e) => setAdjustModal({ ...adjustModal, reset_interval_days: e.target.value })}
              />
              {/* <label className="flex items-start gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  className="mt-0.5 accent-violet-500"
                  checked={!!adjustModal.recompute_next}
                  onChange={(e) => setAdjustModal({ ...adjustModal, recompute_next: e.target.checked })}
                />
                <span className="text-[11px] text-white/50 leading-snug">
                  Restart the cycle from now
                  <span className="block text-white/30">
                    Next reset becomes today + {Number(adjustModal.reset_interval_days) || 7} day(s).
                    Leave off to keep the current next reset
                    {adjustModal.quota?.next_reset_at ? ` (${new Date(adjustModal.quota.next_reset_at).toLocaleDateString()})` : ''} and apply the new interval afterwards.
                  </span>
                </span>
              </label> */}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" className="border-white/15 text-white/80" onClick={() => setAdjustModal({ ...adjustModal, open: false })}>Cancel</Button>
            <Button className="bg-violet-600 hover:bg-violet-700 text-white" onClick={submitAdjust} disabled={submitting}>
              {submitting && <Loader2 className="w-4 h-4 animate-spin mr-2" />}Confirm
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Approve Request Modal — sets price, notifies company to pay */}
      <Dialog open={approveModal.open} onOpenChange={(o) => !o && setApproveModal({ ...approveModal, open: false })}>
        <DialogContent className="bg-[#120d22] border border-[#2d2342] text-white">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <CheckCircle2 className="w-5 h-5 text-emerald-400" /> Approve Key Request
            </DialogTitle>
            {/* <DialogDescription className="text-white/60">
              {approveModal.request?.company_name} — {approveModal.request?.agent_label} ({approveModal.request?.provider?.toUpperCase()})
              <br />
              {((approveModal.request?.key_cost_snapshot ?? 0) > 0 || (approveModal.request?.service_charge_snapshot ?? 0) > 0)
                ? 'Pre-filled from this request’s saved price. Edit here to change it for this company only — global pricing stays unchanged.'
                : 'Pre-filled from global pricing. Edit here to set a custom price for this company only — global pricing stays unchanged.'}
            </DialogDescription> */}
          </DialogHeader>
          <div className="space-y-4 py-2">
            {/* Duration badge — what company requested */}
            {approveModal.request?.preferred_duration && (
              <div className="flex items-center gap-2 p-2.5 bg-violet-500/10 border border-violet-500/20 rounded-lg">
                <Clock className="w-4 h-4 text-violet-300 shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-white/70">
                    Company requested a <span className="text-violet-300 font-semibold capitalize">{approveModal.request.preferred_duration}</span> key.
                    {((approveModal.request?.key_cost_snapshot ?? 0) > 0 || (approveModal.request?.service_charge_snapshot ?? 0) > 0)
                      ? ' The saved price for this request is shown below.'
                      : ' Price has been auto-calculated from global pricing below.'}
                  </p>
                </div>
              </div>
            )}
            {(() => {
              const p = pricing.find(x => x.agent_name === approveModal.request?.agent_name);
              const r = approveModal.request;
              // A request that already carries its own price is not blocked by
              // unset global pricing — the snapshot is what gets approved.
              const hasSnapshot = (r?.key_cost_snapshot ?? 0) > 0 || (r?.service_charge_snapshot ?? 0) > 0;
              const notSet = !hasSnapshot && (!p || (Number(p.monthly_flat_usd) === 0 && Number(p.service_charge_usd) === 0));
              return notSet ? (
                <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-3 flex items-start gap-2">
                  <AlertTriangle className="w-4 h-4 text-amber-400 mt-0.5 shrink-0" />
                  <p className="text-xs text-amber-200">
                    Pricing for <span className="font-semibold">{approveModal.request?.agent_label}</span> is not configured yet.
                    Go to the <span className="font-semibold">Pricing tab</span> to set Key Cost and Service Charge first, or enter custom values below.
                  </p>
                </div>
              ) : null;
            })()}
            {(() => {
              const fullTotal = Number(approveModal.key_cost || 0) + Number(approveModal.service_charge || 0);
              const discPct = Math.min(100, Math.max(0, parseFloat(approveModal.discount_pct) || 0));
              const discountedTotal = fullTotal * (1 - discPct / 100);
              const saving = fullTotal - discountedTotal;
              return (
                <div className="space-y-3">
                  <div className="grid grid-cols-3 gap-3">
                    <div>
                      <Label className="text-white/60 text-xs uppercase tracking-wider">Key Cost</Label>
                      <div className="relative mt-1">
                        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-white/40 text-sm">$</span>
                        <Input
                          type="number" min="0" step="0.01" placeholder="0.00"
                          className="bg-[#1a1333] border-[#3a295a] text-white pl-6"
                          value={approveModal.key_cost}
                          onChange={(e) => setApproveModal({ ...approveModal, key_cost: e.target.value })}
                        />
                      </div>
                    </div>
                    <div>
                      <Label className="text-white/60 text-xs uppercase tracking-wider">Service Charge</Label>
                      <div className="relative mt-1">
                        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-white/40 text-sm">$</span>
                        <Input
                          type="number" min="0" step="0.01" placeholder="0.00"
                          className="bg-[#1a1333] border-[#3a295a] text-white pl-6"
                          value={approveModal.service_charge}
                          onChange={(e) => setApproveModal({ ...approveModal, service_charge: e.target.value })}
                        />
                      </div>
                    </div>
                    <div>
                      <Label className="text-white/60 text-xs uppercase tracking-wider">Discount</Label>
                      <div className="relative mt-1">
                        <Input
                          type="number" min="0" max="100" step="1" placeholder="0"
                          className="bg-[#1a1333] border-[#3a295a] text-white pr-7"
                          value={approveModal.discount_pct}
                          onChange={(e) => setApproveModal({ ...approveModal, discount_pct: e.target.value })}
                        />
                        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-white/40 text-sm">%</span>
                      </div>
                    </div>
                  </div>
                  {/* Opt-in: also write this price to the agent's GLOBAL pricing
                      config. Off by default so the per-company override stays
                      the normal behaviour. */}
                  <label className="flex items-start gap-2 px-3 py-2.5 bg-[#1a1333]/60 border border-[#3a295a] rounded-lg cursor-pointer hover:border-violet-500/40 transition-colors">
                    <input
                      type="checkbox"
                      className="mt-0.5 accent-violet-500"
                      checked={!!approveModal.sync_global_pricing}
                      onChange={(e) => setApproveModal({ ...approveModal, sync_global_pricing: e.target.checked })}
                    />
                    <span className="text-xs text-white/70 leading-snug">
                      Also save as <span className="font-semibold text-violet-300">global pricing</span> for {approveModal.request?.agent_label}
                      <span className="block text-[10px] text-amber-300/70 mt-0.5">
                        Updates the Pricing tab — every company will be quoted these values from now on.
                      </span>
                    </span>
                  </label>
                  {fullTotal > 0 && (
                    <div className="flex items-center justify-between px-4 py-2.5 bg-emerald-500/8 border border-emerald-500/20 rounded-lg">
                      <span className="text-sm text-white/60">Total due</span>
                      <div className="flex items-center gap-2">
                        {discPct > 0 && <span className="text-sm text-white/30 line-through">${fullTotal.toFixed(2)}</span>}
                        <span className="text-emerald-300 font-bold text-base">${discountedTotal.toFixed(2)}<span className="text-white/30 text-[10px] font-normal ml-1">/month</span></span>
                        {saving > 0 && <span className="text-[10px] text-emerald-400 bg-emerald-500/15 px-1.5 py-0.5 rounded-full">-${saving.toFixed(2)}</span>}
                      </div>
                    </div>
                  )}
                </div>
              );
            })()}
            <div>
              <Label className="text-white/70 text-sm">Admin note <span className="text-white/40 font-normal">(shown to company)</span></Label>
              <Textarea
                rows={2}
                className="bg-[#1a1333] border-[#3a295a] text-white mt-1"
                placeholder="Optional instructions or context..."
                value={approveModal.admin_note}
                onChange={(e) => setApproveModal({ ...approveModal, admin_note: e.target.value })}
              />
            </div>
            <div className="bg-amber-500/5 border border-amber-500/20 rounded-lg p-3 text-xs text-amber-200/80">
              Company will receive an in-app notification and email with the amount due. The key will only be assigned after payment is confirmed.
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" className="border-white/15 text-white/80" onClick={() => setApproveModal({ open: false, request: null, key_cost: '', service_charge: '', discount_pct: '0', admin_note: '', sync_global_pricing: false })}>Cancel</Button>
            <Button className="bg-emerald-600 hover:bg-emerald-700 text-white" onClick={submitApprove} disabled={submitting}>
              {submitting && <Loader2 className="w-4 h-4 animate-spin mr-2" />}Approve & Notify
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Reject Request Modal */}
      <Dialog open={rejectModal.open} onOpenChange={(o) => !o && setRejectModal({ ...rejectModal, open: false })}>
        <DialogContent className="bg-[#120d22] border border-[#2d2342] text-white">
          <DialogHeader>
            <DialogTitle>Reject Request</DialogTitle>
            <DialogDescription className="text-white/60">
              {rejectModal.request?.company_name} — {rejectModal.request?.agent_label}
            </DialogDescription>
          </DialogHeader>
          <div className="py-2">
            <Label className="text-white/70 text-sm">Reason (shown to user)</Label>
            <Textarea
              rows={3}
              className="bg-[#1a1333] border-[#3a295a] text-white mt-1"
              value={rejectModal.note}
              onChange={(e) => setRejectModal({ ...rejectModal, note: e.target.value })}
              placeholder="Optional note explaining why..."
            />
          </div>
          <DialogFooter>
            <Button variant="outline" className="border-white/15 text-white/80" onClick={() => setRejectModal({ open: false, request: null, note: '' })}>Cancel</Button>
            <Button className="bg-red-600 hover:bg-red-700 text-white" onClick={submitReject} disabled={submitting}>
              {submitting && <Loader2 className="w-4 h-4 animate-spin mr-2" />}Reject
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Request Modal — price/duration/note before payment */}
      <Dialog open={editModal.open} onOpenChange={(o) => !o && setEditModal({ ...editModal, open: false })}>
        <DialogContent className="bg-[#120d22] border border-[#2d2342] text-white sm:max-w-lg w-full">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Pencil className="w-5 h-5 text-violet-400" /> Edit Request
            </DialogTitle>
            <DialogDescription className="text-white/60">
              {editModal.request?.company_name} — {editModal.request?.agent_label} ({editModal.request?.provider?.toUpperCase()})
              {editModal.request?.status === 'payment_pending' && (
                <span className="ml-1 text-yellow-300/80">· editable until the company pays</span>
              )}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-1">
            <div className="space-y-1.5">
              <Label className="text-white/70 text-sm">Billing duration</Label>
              <Select value={editModal.preferred_duration} onValueChange={(v) => setEditModal({ ...editModal, preferred_duration: v })}>
                <SelectTrigger className="bg-[#1a1333] border-[#3a295a] text-white"><SelectValue /></SelectTrigger>
                <SelectContent className="bg-[#1a1333] border-[#3a295a] text-white">
                  <SelectItem value="monthly">Monthly</SelectItem>
                  {/* <SelectItem value="yearly">Yearly</SelectItem> */}
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-1">
                <Label className="text-white/70 text-xs">Key Cost ($)</Label>
                <Input type="number" min="0" step="0.01" className="bg-[#1a1333] border-[#3a295a] text-white"
                  value={editModal.key_cost}
                  onChange={(e) => setEditModal({ ...editModal, key_cost: e.target.value })} />
              </div>
              <div className="space-y-1">
                <Label className="text-white/70 text-xs">Service ($)</Label>
                <Input type="number" min="0" step="0.01" className="bg-[#1a1333] border-[#3a295a] text-white"
                  value={editModal.service_charge}
                  onChange={(e) => setEditModal({ ...editModal, service_charge: e.target.value })} />
              </div>
              <div className="space-y-1">
                <Label className="text-white/70 text-xs">Discount (%)</Label>
                <Input type="number" min="0" max="100" step="1" className="bg-[#1a1333] border-[#3a295a] text-white"
                  value={editModal.discount_pct}
                  onChange={(e) => setEditModal({ ...editModal, discount_pct: e.target.value })} />
              </div>
            </div>
            {(() => {
              const disc = Math.min(100, Math.max(0, parseFloat(editModal.discount_pct) || 0));
              const raw = (Number(editModal.key_cost) || 0) + (Number(editModal.service_charge) || 0);
              const net = (raw * (1 - disc / 100));
              return (
                <p className="text-xs text-white/60">
                  Amount due after discount: <span className="text-emerald-300 font-semibold">${net.toFixed(2)}</span>
                  {disc > 0 && <span className="text-white/30 ml-1 line-through">${raw.toFixed(2)}</span>}
                </p>
              );
            })()}
            <div className="space-y-1.5">
              <Label className="text-white/70 text-sm">Admin note (optional)</Label>
              <Textarea rows={2} className="bg-[#1a1333] border-[#3a295a] text-white"
                value={editModal.admin_note}
                onChange={(e) => setEditModal({ ...editModal, admin_note: e.target.value })}
                placeholder="Internal / company-facing note…" />
            </div>
            {/* Opt-in: also write this price to the agent's GLOBAL pricing config. */}
            <label className="flex items-start gap-2 px-3 py-2.5 bg-[#1a1333]/60 border border-[#3a295a] rounded-lg cursor-pointer hover:border-violet-500/40 transition-colors">
              <input
                type="checkbox"
                className="mt-0.5 accent-violet-500"
                checked={!!editModal.sync_global_pricing}
                onChange={(e) => setEditModal({ ...editModal, sync_global_pricing: e.target.checked })}
              />
              <span className="text-xs text-white/70 leading-snug">
                Also save as <span className="font-semibold text-violet-300">global pricing</span> for {editModal.request?.agent_label}
                <span className="block text-[10px] text-amber-300/70 mt-0.5">
                  Updates the Pricing tab — every company will be quoted these values from now on.
                </span>
              </span>
            </label>
          </div>
          <DialogFooter>
            <Button variant="outline" className="border-white/15 text-white/80" onClick={() => setEditModal({ open: false, request: null, key_cost: '', service_charge: '', discount_pct: '0', preferred_duration: 'monthly', admin_note: '', sync_global_pricing: false })}>Cancel</Button>
            <Button className="bg-violet-600 hover:bg-violet-700 text-white" onClick={submitEdit} disabled={editing}>
              {editing && <Loader2 className="w-4 h-4 animate-spin mr-2" />}Save Changes
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Confirm Dialog */}
      <Dialog open={confirmDialog.open} onOpenChange={(o) => !o && setConfirmDialog({ ...confirmDialog, open: false })}>
        <DialogContent className="bg-[#120d22] border border-[#2d2342] text-white max-w-sm">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-red-300">
              <AlertTriangle className="w-5 h-5" />
              {confirmDialog.title}
            </DialogTitle>
            <DialogDescription className="text-white/60 pt-1">
              {confirmDialog.description}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="mt-2">
            <Button variant="outline" className="border-white/15 text-white/80" onClick={() => setConfirmDialog({ ...confirmDialog, open: false })}>Cancel</Button>
            <Button className="bg-red-600 hover:bg-red-700 text-white" onClick={() => { setConfirmDialog({ ...confirmDialog, open: false }); confirmDialog.onConfirm?.(); }}>
              Confirm
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      
    </>
  );
};

export default SuperAdminApiKeysPage;