import React, { useEffect, useMemo, useState } from 'react';
import { Helmet } from 'react-helmet';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { useToast } from '@/components/ui/use-toast';
import {
  Loader2, Key, ShieldCheck, AlertTriangle, CheckCircle2, XCircle,
  Send, Trash2, ChevronLeft, RefreshCw, Sparkles, Activity, Clock,
  BrainCircuit, Lock, Info
} from 'lucide-react';
import DashboardNavbar from '@/components/common/DashboardNavbar';
import agentKeysService from '@/services/agentKeysService';

const GRADIENT_BG = 'linear-gradient(135deg, #020308 0%, #0a0a1a 25%, #0d0b1f 50%, #0f0a20 75%, #020308 100%)';

const formatTokens = (n) => {
  if (n == null) return '—';
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
};

const modeBadge = (a) => {
  if (a.byok) return { label: 'BYOK Active', class: 'bg-blue-500/15 text-blue-300 border border-blue-500/30' };
  if (a.managed) return { label: 'Managed Active', class: 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30' };
  return { label: 'No key', class: 'bg-gray-500/15 text-gray-400 border border-gray-500/30' };
};

const StatCard = ({ icon: Icon, label, value, accent }) => (
  <div className="bg-[#120d22] border border-[#2d2342] rounded-xl p-4 hover:border-violet-500/30 transition-colors">
    <div className="flex items-center justify-between">
      <div>
        <p className="text-xs uppercase tracking-wider text-white/40 mb-1">{label}</p>
        <p className="text-2xl font-bold text-white">{value}</p>
      </div>
      <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${accent}`}>
        <Icon className="w-5 h-5" />
      </div>
    </div>
  </div>
);

const QuotaBar = ({ quota }) => {
  if (!quota) {
    return <p className="text-sm text-white/40 italic">Quota will be created on first use.</p>;
  }
  const pct = quota.included_tokens > 0 ? Math.min(100, (quota.used_tokens / quota.included_tokens) * 100) : 0;
  const barGradient =
    pct >= 100 ? 'from-red-500 to-rose-500'
    : pct >= 80 ? 'from-amber-400 to-orange-500'
    : 'from-emerald-400 to-teal-500';

  const PROVIDER_META = {
    openai:  { label: 'OpenAI',         accent: 'bg-green-500/15 text-green-300 border-green-500/20'     },
    groq:    { label: 'Groq (Llama)',    accent: 'bg-violet-500/15 text-violet-300 border-violet-500/20'  },
    claude:  { label: 'Claude',          accent: 'bg-orange-500/15 text-orange-300 border-orange-500/20'  },
    gemini:  { label: 'Google Gemini',   accent: 'bg-blue-500/15 text-blue-300 border-blue-500/20'        },
    grok:    { label: 'xAI Grok',        accent: 'bg-red-500/15 text-red-300 border-red-500/20'           },
  };
  const breakdown = quota.provider_breakdown ?? {};
  const providerRows = Object.entries(breakdown)
    .filter(([, tokens]) => tokens > 0)
    .map(([key, tokens]) => ({
      key,
      tokens,
      label:  PROVIDER_META[key]?.label  ?? key.toUpperCase(),
      accent: PROVIDER_META[key]?.accent ?? 'bg-white/10 text-white/60 border-white/20',
    }));

  return (
    <div className="space-y-3">
      {/* Overall */}
      <div className="flex items-center justify-between text-sm">
        <div className="flex items-baseline gap-2">
          <span className="text-white font-semibold text-base">{formatTokens(quota.used_tokens)}</span>
          <span className="text-white/40">/ {formatTokens(quota.included_tokens)}</span>
          <span className="text-white/30 text-xs">total tokens</span>
        </div>
        <span className="text-white/50 text-xs">{pct.toFixed(1)}% used</span>
      </div>
      <div className="w-full h-2 bg-[#1a1333] rounded-full overflow-hidden border border-[#2d2342]">
        <div
          className={`h-full bg-gradient-to-r ${barGradient} transition-all`}
          style={{ width: `${pct}%`, boxShadow: '0 0 8px rgba(139,92,246,0.25)' }}
        />
      </div>

      {/* Per-model breakdown — only show providers that have been used */}
      {providerRows.length > 0 && (
        <div className={`grid gap-2 ${providerRows.length === 1 ? 'grid-cols-1' : 'grid-cols-2'}`}>
          {providerRows.map(p => (
            <div key={p.key} className={`rounded-lg border px-3 py-2 ${p.accent}`}>
              <p className="text-[10px] uppercase font-semibold tracking-wider opacity-80">{p.label}</p>
              <p className="text-sm font-bold mt-0.5">{formatTokens(p.tokens)}</p>
              <p className="text-[10px] opacity-60 mt-0.5">tokens used</p>
            </div>
          ))}
        </div>
      )}

      {quota.byok_tokens_info > 0 && (
        <p className="text-xs text-white/40 flex items-center gap-1">
          <Info className="w-3 h-3" /> BYOK (your own key): {formatTokens(quota.byok_tokens_info)} tokens — info only
        </p>
      )}

      {quota.is_exhausted && (
        <div className="flex items-start gap-2 px-3 py-2 bg-red-500/10 border border-red-500/30 rounded-lg">
          <AlertTriangle className="w-4 h-4 text-red-400 mt-0.5 shrink-0" />
          <div className="text-xs text-red-200">
            <p className="font-semibold">Managed quota exhausted.</p>
            <p className="text-red-300/80">Add your own API key (BYOK) or request a managed key from the admin to continue using this agent.</p>
          </div>
        </div>
      )}
    </div>
  );
};

const AgentCard = ({ agent, pendingReq, onByok, onRevoke, onRequest }) => {
  const m = modeBadge(agent);
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-[#120d22] border border-[#2d2342] rounded-xl overflow-hidden hover:border-violet-500/30 transition-colors"
    >
      <div className="p-5 border-b border-[#2d2342] bg-gradient-to-r from-[#1a1333]/60 to-transparent">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-violet-500/15 border border-violet-500/30 flex items-center justify-center">
              <BrainCircuit className="w-5 h-5 text-violet-300" />
            </div>
            <div>
              <h3 className="text-white font-semibold">{agent.agent_label}</h3>
              <p className="text-xs text-white/40 font-mono">{agent.agent_name}</p>
            </div>
          </div>
          <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${m.class}`}>{m.label}</span>
        </div>
      </div>

      <div className="p-5 space-y-4">
        <QuotaBar quota={agent.quota} />

        {agent.byok && (
          <div className="flex items-center justify-between p-3 bg-blue-500/5 border border-blue-500/20 rounded-lg">
            <div className="flex items-center gap-3">
              <Lock className="w-4 h-4 text-blue-300 shrink-0" />
              <div>
                <p className="text-sm text-white font-medium">Your BYOK key</p>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="text-xs text-white/50 uppercase">{agent.byok.provider}</span>
                  <span className="font-mono text-xs text-white/70">{agent.byok.masked}</span>
                </div>
              </div>
            </div>
            <Button size="sm" variant="ghost" className="text-red-300 hover:text-red-200 hover:bg-red-500/10" onClick={() => onRevoke(agent.agent_name)}>
              <Trash2 className="w-4 h-4" />
            </Button>
          </div>
        )}

        {agent.managed && (
          <div className="flex items-center justify-between p-3 bg-emerald-500/5 border border-emerald-500/20 rounded-lg">
            <div className="flex items-center gap-3">
              <ShieldCheck className="w-4 h-4 text-emerald-300 shrink-0" />
              <div>
                <p className="text-sm text-white font-medium">Managed key (assigned by admin)</p>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="text-xs text-white/50 uppercase">{agent.managed.provider}</span>
                  <span className="font-mono text-xs text-white/70">{agent.managed.masked}</span>
                </div>
              </div>
            </div>
            <Badge variant="outline" className="text-white/60 border-white/20 text-xs">Admin-controlled</Badge>
          </div>
        )}

        {!agent.byok && !agent.managed && agent.default_provider && (
          <div className="flex items-center gap-3 p-3 bg-white/[0.03] border border-white/10 rounded-lg">
            <Activity className="w-4 h-4 text-violet-300/70 shrink-0" />
            <div>
              <p className="text-sm text-white/70 font-medium">Platform key (free tier)</p>
              <p className="text-xs text-white/40 mt-0.5">
                Provider: <span className="uppercase text-white/60">{agent.default_provider}</span>
                {' · '}1M free tokens included with your purchase
              </p>
            </div>
          </div>
        )}

        <div className="flex flex-wrap gap-2 pt-1">
          <Button
            size="sm"
            className="bg-violet-600 hover:bg-violet-700 text-white shadow-[0_0_12px_rgba(139,92,246,0.3)]"
            onClick={() => onByok(agent)}
          >
            <Key className="w-4 h-4 mr-1.5" />
            {agent.byok ? 'Update my key' : 'Add my own key'}
          </Button>
          {!agent.managed && (
            <Button
              size="sm"
              variant="outline"
              className="border-white/15 text-white/80 hover:bg-white/5 hover:text-white"
              onClick={() => onRequest(agent)}
              disabled={!!pendingReq}
            >
              <Send className="w-4 h-4 mr-1.5" />
              {pendingReq ? 'Request pending' : 'Request managed key'}
            </Button>
          )}
        </div>
      </div>
    </motion.div>
  );
};

const RequestRow = ({ r }) => {
  const statusStyle = {
    approved: { icon: CheckCircle2, class: 'text-emerald-300 bg-emerald-500/10 border-emerald-500/30' },
    rejected: { icon: XCircle, class: 'text-red-300 bg-red-500/10 border-red-500/30' },
    pending: { icon: Clock, class: 'text-amber-300 bg-amber-500/10 border-amber-500/30' },
  }[r.status] || { icon: Clock, class: 'text-gray-300 bg-gray-500/10 border-gray-500/30' };
  const Icon = statusStyle.icon;
  return (
    <div className="flex items-center justify-between p-3 bg-[#0f0a20] border border-[#2d2342] rounded-lg hover:border-violet-500/30 transition-colors">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="text-sm text-white font-medium truncate">{r.agent_label}</p>
          <span className="text-xs text-white/40 uppercase">{r.provider}</span>
        </div>
        <p className="text-xs text-white/40 mt-0.5">{new Date(r.created_at).toLocaleString()}</p>
        {r.note && <p className="text-xs text-white/60 mt-1 italic">"{r.note}"</p>}
        {r.admin_note && <p className="text-xs text-violet-300 mt-1">Admin: {r.admin_note}</p>}
      </div>
      <span className={`flex items-center gap-1 text-xs px-2.5 py-1 rounded-full border font-medium ${statusStyle.class}`}>
        <Icon className="w-3 h-3" />
        {r.status}
      </span>
    </div>
  );
};

const AgentKeysSettingsPage = () => {
  const navigate = useNavigate();
  const { toast } = useToast();

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [agents, setAgents] = useState([]);
  const [providers, setProviders] = useState([]);
  const [requests, setRequests] = useState([]);

  const [byokModal, setByokModal] = useState({ open: false, agent: null, provider: 'openai', apiKey: '' });
  const [requestModal, setRequestModal] = useState({ open: false, agent: null, provider: 'openai', note: '' });
  const [submitting, setSubmitting] = useState(false);

  const stats = useMemo(() => {
    const totalAgents = agents.length;
    const byokCount = agents.filter(a => a.byok).length;
    const managedCount = agents.filter(a => a.managed).length;
    const pendingReqs = requests.filter(r => r.status === 'pending').length;
    const exhausted = agents.filter(a => a.quota?.is_exhausted).length;
    return { totalAgents, byokCount, managedCount, pendingReqs, exhausted };
  }, [agents, requests]);

  const loadData = async ({ silent = false } = {}) => {
    if (!silent) setLoading(true);
    else setRefreshing(true);
    try {
      const [keys, reqs] = await Promise.all([
        agentKeysService.listAgentKeys(),
        agentKeysService.listKeyRequests(),
      ]);
      setAgents(keys.agents || []);
      setProviders(keys.providers || []);
      setRequests(reqs.requests || []);
    } catch (e) {
      toast({ title: 'Failed to load', description: String(e.message || e), variant: 'destructive' });
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => { loadData(); }, []);

  const openByok = (agent) => setByokModal({ open: true, agent, provider: agent.byok?.provider || 'openai', apiKey: '' });
  const openRequest = (agent) => setRequestModal({ open: true, agent, provider: 'openai', note: '' });

  const submitByok = async () => {
    if (!byokModal.apiKey || byokModal.apiKey.length < 10) {
      toast({ title: 'Invalid key', description: 'API key looks too short to be valid.', variant: 'destructive' });
      return;
    }
    setSubmitting(true);
    try {
      await agentKeysService.upsertByokKey({
        agent_name: byokModal.agent.agent_name,
        provider: byokModal.provider,
        api_key: byokModal.apiKey,
      });
      toast({ title: 'Key saved', description: 'Your BYOK key is now active for this agent.' });
      setByokModal({ open: false, agent: null, provider: 'openai', apiKey: '' });
      loadData({ silent: true });
    } catch (e) {
      toast({ title: 'Save failed', description: String(e.message || e), variant: 'destructive' });
    } finally {
      setSubmitting(false);
    }
  };

  const revokeByok = async (agentName) => {
    if (!window.confirm('Remove your BYOK key for this agent? The managed key (if any) will be used instead.')) return;
    try {
      await agentKeysService.revokeByokKey(agentName);
      toast({ title: 'BYOK key removed' });
      loadData({ silent: true });
    } catch (e) {
      toast({ title: 'Revoke failed', description: String(e.message || e), variant: 'destructive' });
    }
  };

  const submitRequest = async () => {
    setSubmitting(true);
    try {
      const res = await agentKeysService.createKeyRequest({
        agent_name: requestModal.agent.agent_name,
        provider: requestModal.provider,
        note: requestModal.note,
      });
      toast({
        title: res.already_pending ? 'Request already pending' : 'Request sent',
        description: 'Admin will review and assign a managed key.',
      });
      setRequestModal({ open: false, agent: null, provider: 'openai', note: '' });
      loadData({ silent: true });
    } catch (e) {
      toast({ title: 'Request failed', description: String(e.message || e), variant: 'destructive' });
    } finally {
      setSubmitting(false);
    }
  };

  const pendingByAgent = useMemo(() => {
    const map = {};
    requests.filter(r => r.status === 'pending').forEach(r => { map[r.agent_name] = r; });
    return map;
  }, [requests]);

  return (
    <>
      <Helmet><title>API Keys & Quota — AIEmployee</title></Helmet>
      <div className="min-h-screen overflow-x-hidden" style={{ background: GRADIENT_BG }}>
        <DashboardNavbar
          icon={Key}
          title="API Keys & Token Quota"
          subtitle="Manage BYOK keys, quotas, and managed-key requests"
        />

        <div className="container mx-auto px-4 py-8 max-w-6xl">
          {/* Header row */}
          <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
            <div>
              <button
                onClick={() => navigate('/company/dashboard')}
                className="flex items-center gap-1 text-sm text-white/50 hover:text-white mb-2 transition-colors"
              >
                <ChevronLeft className="w-4 h-4" /> Back to dashboard
              </button>
              <h1 className="text-2xl sm:text-3xl font-bold text-white flex items-center gap-2">
                <Sparkles className="w-6 h-6 text-violet-400" />
                API Keys & Token Quota
              </h1>
              <p className="text-sm text-white/50 mt-1">Bring your own LLM key, or request a managed one — your call.</p>
            </div>
            <Button
              variant="outline"
              className="border-white/15 text-white/80 hover:bg-white/5 hover:text-white"
              onClick={() => loadData({ silent: true })}
              disabled={refreshing || loading}
            >
              {refreshing ? <Loader2 className="w-4 h-4 animate-spin mr-1.5" /> : <RefreshCw className="w-4 h-4 mr-1.5" />}
              Refresh
            </Button>
          </div>

          {/* Stat cards */}
          {!loading && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
              <StatCard icon={BrainCircuit} label="Purchased Agents" value={stats.totalAgents} accent="bg-violet-500/15 text-violet-300" />
              <StatCard icon={Lock} label="BYOK Keys" value={stats.byokCount} accent="bg-blue-500/15 text-blue-300" />
              <StatCard icon={ShieldCheck} label="Managed Keys" value={stats.managedCount} accent="bg-emerald-500/15 text-emerald-300" />
              <StatCard icon={stats.exhausted > 0 ? AlertTriangle : Activity} label="Exhausted" value={stats.exhausted} accent={stats.exhausted > 0 ? 'bg-red-500/15 text-red-300' : 'bg-gray-500/15 text-gray-400'} />
            </div>
          )}

          {/* Info banner */}
          <div className="mb-6 bg-gradient-to-r from-violet-500/10 to-fuchsia-500/10 border border-violet-500/20 rounded-xl p-4 flex items-start gap-3">
            <Info className="w-5 h-5 text-violet-300 shrink-0 mt-0.5" />
            <div className="text-sm text-white/70">
              <p className="text-white font-medium mb-1">How this works</p>
              <p className="text-white/60 leading-relaxed">
                Each agent you purchase includes <span className="text-white font-semibold">1M free tokens</span> via a platform-managed key.
                When those run out, you can either <span className="text-blue-300">add your own API key (BYOK)</span> to pay the provider directly,
                or <span className="text-emerald-300">request a managed key</span> from the admin. Keys are encrypted at rest and never shown in plaintext.
              </p>
            </div>
          </div>

          {/* Agents list */}
          {loading ? (
            <div className="flex justify-center py-20">
              <Loader2 className="w-8 h-8 animate-spin text-violet-400" />
            </div>
          ) : agents.length === 0 ? (
            <Card className="bg-[#120d22] border border-[#2d2342]">
              <CardContent className="p-12 text-center">
                <BrainCircuit className="w-12 h-12 text-white/20 mx-auto mb-4" />
                <h3 className="text-white font-semibold mb-2">No agents purchased yet</h3>
                <p className="text-sm text-white/50 mb-4">Buy an agent from the dashboard to start configuring API keys and token quotas.</p>
                <Button className="bg-violet-600 hover:bg-violet-700 text-white" onClick={() => navigate('/company/dashboard')}>
                  Go to dashboard
                </Button>
              </CardContent>
            </Card>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {agents.map(a => (
                <AgentCard
                  key={a.agent_name}
                  agent={a}
                  pendingReq={pendingByAgent[a.agent_name]}
                  onByok={openByok}
                  onRevoke={revokeByok}
                  onRequest={openRequest}
                />
              ))}
            </div>
          )}

          {/* Requests history */}
          {requests.length > 0 && (
            <Card className="bg-[#120d22] border border-[#2d2342] mt-6">
              <CardHeader>
                <CardTitle className="text-white flex items-center gap-2">
                  <Send className="w-5 h-5 text-violet-400" /> Key Requests
                </CardTitle>
                <CardDescription className="text-white/50">
                  {stats.pendingReqs > 0
                    ? `${stats.pendingReqs} request${stats.pendingReqs > 1 ? 's' : ''} awaiting admin review.`
                    : 'No pending requests.'}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                {requests.map(r => <RequestRow key={r.id} r={r} />)}
              </CardContent>
            </Card>
          )}
        </div>
      </div>

      {/* BYOK modal */}
      <Dialog open={byokModal.open} onOpenChange={(o) => !o && setByokModal({ ...byokModal, open: false })}>
        <DialogContent className="bg-[#120d22] border border-[#2d2342] text-white">
          <DialogHeader>
            <DialogTitle className="text-white flex items-center gap-2">
              <Key className="w-5 h-5 text-violet-400" />
              {byokModal.agent?.byok ? 'Update' : 'Add'} BYOK Key
            </DialogTitle>
            <DialogDescription className="text-white/60">
              {byokModal.agent?.agent_label} — your key is encrypted at rest and never displayed in plaintext after save.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-3">
            <div className="space-y-1.5">
              <Label className="text-white/70 text-sm">Provider</Label>
              <Select value={byokModal.provider} onValueChange={(v) => setByokModal({ ...byokModal, provider: v })}>
                <SelectTrigger className="bg-[#1a1333] border-[#3a295a] text-white"><SelectValue /></SelectTrigger>
                <SelectContent className="bg-[#1a1333] border-[#3a295a] text-white">
                  {providers.map(p => <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-white/70 text-sm">API Key</Label>
              <Input
                type="password"
                autoComplete="off"
                placeholder="sk-..."
                className="bg-[#1a1333] border-[#3a295a] text-white font-mono placeholder:text-white/30"
                value={byokModal.apiKey}
                onChange={(e) => setByokModal({ ...byokModal, apiKey: e.target.value })}
              />
              <p className="text-xs text-white/40 flex items-center gap-1">
                <Lock className="w-3 h-3" /> Encrypted with Fernet before storage.
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" className="border-white/15 text-white/80 hover:bg-white/5" onClick={() => setByokModal({ ...byokModal, open: false })}>Cancel</Button>
            <Button className="bg-violet-600 hover:bg-violet-700 text-white" onClick={submitByok} disabled={submitting}>
              {submitting && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}Save key
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Key request modal */}
      <Dialog open={requestModal.open} onOpenChange={(o) => !o && setRequestModal({ ...requestModal, open: false })}>
        <DialogContent className="bg-[#120d22] border border-[#2d2342] text-white">
          <DialogHeader>
            <DialogTitle className="text-white flex items-center gap-2">
              <Send className="w-5 h-5 text-violet-400" />
              Request Managed Key
            </DialogTitle>
            <DialogDescription className="text-white/60">
              {requestModal.agent?.agent_label} — admin will review and assign a platform key on approval.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-3">
            <div className="space-y-1.5">
              <Label className="text-white/70 text-sm">Preferred provider</Label>
              <Select value={requestModal.provider} onValueChange={(v) => setRequestModal({ ...requestModal, provider: v })}>
                <SelectTrigger className="bg-[#1a1333] border-[#3a295a] text-white"><SelectValue /></SelectTrigger>
                <SelectContent className="bg-[#1a1333] border-[#3a295a] text-white">
                  {providers.map(p => <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-white/70 text-sm">Note for admin (optional)</Label>
              <Textarea
                rows={3}
                className="bg-[#1a1333] border-[#3a295a] text-white placeholder:text-white/30"
                placeholder="Briefly explain why you need a managed key..."
                value={requestModal.note}
                onChange={(e) => setRequestModal({ ...requestModal, note: e.target.value })}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" className="border-white/15 text-white/80 hover:bg-white/5" onClick={() => setRequestModal({ ...requestModal, open: false })}>Cancel</Button>
            <Button className="bg-violet-600 hover:bg-violet-700 text-white" onClick={submitRequest} disabled={submitting}>
              {submitting && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}Send request
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default AgentKeysSettingsPage;
