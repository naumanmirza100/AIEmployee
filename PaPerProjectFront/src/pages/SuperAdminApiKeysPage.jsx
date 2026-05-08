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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { useToast } from '@/components/ui/use-toast';
import {
  Loader2, Key, ShieldCheck, AlertTriangle, CheckCircle2, XCircle,
  Send, Trash2, ChevronLeft, RefreshCw, DollarSign, Gauge,
  Inbox, Building2, Sparkles, Save, Plus, Info, Settings, Globe, Search
} from 'lucide-react';
import DashboardNavbar from '@/components/common/DashboardNavbar';
import adminApiKeysService from '@/services/adminApiKeysService';

const GRADIENT_BG = 'linear-gradient(135deg, #020308 0%, #0a0a1a 25%, #0d0b1f 50%, #0f0a20 75%, #020308 100%)';
const CARD_CLASS = 'bg-[#120d22] border border-[#2d2342]';
const ROW_CLASS = 'bg-[#0f0a20] border border-[#2d2342] hover:border-violet-500/30 transition-colors';

const PROVIDER_OPTIONS = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'groq', label: 'Groq (Llama)' },
  { value: 'claude', label: 'Claude / Anthropic' },
  { value: 'gemini', label: 'Google Gemini' },
  { value: 'grok', label: 'xAI Grok' },
];

const AGENT_OPTIONS = [
  { value: 'recruitment_agent', label: 'Recruitment Agent' },
  { value: 'marketing_agent', label: 'Marketing Agent' },
  { value: 'project_manager_agent', label: 'Project Manager Agent' },
  { value: 'frontline_agent', label: 'Frontline Agent' },
  { value: 'operations_agent', label: 'Operations Agent' },
];

const formatTokens = (n) => {
  if (n == null) return '—';
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(2)}B`;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
};

const StatCard = ({ icon: Icon, label, value, accent }) => (
  <div className={`${CARD_CLASS} rounded-xl p-4 hover:border-violet-500/30 transition-colors`}>
    <div className="flex items-center justify-between">
      <div>
        <p className="text-[11px] uppercase tracking-wider text-white/40 mb-1">{label}</p>
        <p className="text-2xl font-bold text-white">{value}</p>
      </div>
      <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${accent}`}>
        <Icon className="w-5 h-5" />
      </div>
    </div>
  </div>
);

// -------------------- Platform Keys Tab --------------------
const PlatformKeyRow = ({ row, onSave, saving }) => {
  const [apiKey, setApiKey] = useState('');
  return (
    <div className={`${ROW_CLASS} rounded-lg p-4`}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-violet-500/15 border border-violet-500/30 flex items-center justify-center">
            <Globe className="w-5 h-5 text-violet-300" />
          </div>
          <div>
            <h4 className="text-white font-semibold">{row.provider_label}</h4>
            <p className="text-xs text-white/50 font-mono">
              {row.configured ? row.masked : 'Not configured'}
            </p>
          </div>
        </div>
        <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium border ${
          row.configured && row.status === 'active'
            ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
            : 'bg-gray-500/15 text-gray-400 border-gray-500/30'
        }`}>
          {row.configured && row.status === 'active' ? 'Active' : 'Not set'}
        </span>
      </div>
      <div className="flex items-end gap-2">
        <div className="flex-1">
          <Label className="text-white/60 text-xs">
            {row.configured ? 'Replace key' : 'Paste new key'}
          </Label>
          <Input
            type="password" autoComplete="off" placeholder="sk-..."
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            className="bg-[#1a1333] border-[#3a295a] text-white mt-1 font-mono"
          />
        </div>
        <Button
          className="bg-violet-600 hover:bg-violet-700 text-white"
          disabled={saving || apiKey.length < 10}
          onClick={() => onSave(row.provider, apiKey, () => setApiKey(''))}
        >
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4 mr-1" />}
          Save
        </Button>
      </div>
      {row.updated_at && (
        <p className="text-[10px] text-white/30 mt-2">
          Last updated: {row.updated_by ? `${row.updated_by} • ` : ''}{new Date(row.updated_at).toLocaleString()}
        </p>
      )}
    </div>
  );
};

const PlatformTab = ({ platformKeys, onSave, savingProvider }) => (
  <div className="space-y-3">
    <div className="bg-gradient-to-r from-emerald-500/10 to-teal-500/10 border border-emerald-500/20 rounded-lg p-4 flex items-start gap-3">
      <Globe className="w-5 h-5 text-emerald-300 shrink-0 mt-0.5" />
      <div className="text-sm text-white/70">
        <p className="text-white font-semibold mb-1">Platform keys = the "free tokens" path</p>
        <p className="text-white/60 leading-relaxed">
          Set <span className="text-white font-semibold">one key per provider</span>. Every company uses these keys automatically
          until their per-agent quota (1M default) is exhausted. Keys are encrypted at rest — only the masked preview is shown.
        </p>
      </div>
    </div>
    {platformKeys.map(row => (
      <PlatformKeyRow
        key={row.provider}
        row={row}
        onSave={onSave}
        saving={savingProvider === row.provider}
      />
    ))}
  </div>
);

// -------------------- Overview Tab --------------------
const OverviewTab = ({ stats }) => (
  <div className="space-y-6">
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      <StatCard icon={Building2} label="Companies" value={stats.total_companies} accent="bg-violet-500/15 text-violet-300" />
      <StatCard icon={ShieldCheck} label="Active Keys" value={stats.total_keys} accent="bg-emerald-500/15 text-emerald-300" />
      <StatCard icon={Inbox} label="Pending Requests" value={stats.pending_requests} accent="bg-amber-500/15 text-amber-300" />
      <StatCard icon={AlertTriangle} label="Exhausted Quotas" value={stats.exhausted_quotas} accent={stats.exhausted_quotas > 0 ? 'bg-red-500/15 text-red-300' : 'bg-gray-500/15 text-gray-400'} />
    </div>
    <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
      <StatCard icon={Key} label="Managed Keys" value={stats.managed_keys} accent="bg-emerald-500/15 text-emerald-300" />
      <StatCard icon={Key} label="BYOK Keys" value={stats.byok_keys} accent="bg-blue-500/15 text-blue-300" />
      <StatCard icon={Gauge} label="Active Purchases" value={stats.total_purchases} accent="bg-fuchsia-500/15 text-fuchsia-300" />
    </div>

    <Card className={CARD_CLASS}>
      <CardHeader>
        <CardTitle className="text-white flex items-center gap-2">
          <Gauge className="w-5 h-5 text-violet-400" /> Token Ledger
        </CardTitle>
        <CardDescription className="text-white/50">Aggregate token usage across all companies and agents.</CardDescription>
      </CardHeader>
      <CardContent className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="p-4 bg-[#1a1333] border border-[#2d2342] rounded-lg">
          <p className="text-xs text-white/40 uppercase mb-1">Included (managed)</p>
          <p className="text-xl font-bold text-white">{formatTokens(stats.total_included_tokens)}</p>
        </div>
        <div className="p-4 bg-[#1a1333] border border-[#2d2342] rounded-lg">
          <p className="text-xs text-white/40 uppercase mb-1">Used (managed)</p>
          <p className="text-xl font-bold text-violet-300">{formatTokens(stats.total_used_tokens)}</p>
        </div>
        <div className="p-4 bg-[#1a1333] border border-[#2d2342] rounded-lg">
          <p className="text-xs text-white/40 uppercase mb-1">BYOK info (non-billable)</p>
          <p className="text-xl font-bold text-blue-300">{formatTokens(stats.total_byok_info_tokens)}</p>
        </div>
      </CardContent>
    </Card>
  </div>
);

// -------------------- Keys Tab --------------------
const KeysTab = ({ keys, onAssign, onRevoke, filter, setFilter, onRefresh, loading }) => (
  <div className="space-y-4">
    <div className="flex items-center gap-2 flex-wrap">
      <Input
        placeholder="Search company..."
        value={filter.search || ''}
        onChange={(e) => setFilter({ ...filter, search: e.target.value })}
        className="bg-[#1a1333] border-[#3a295a] text-white w-60 placeholder:text-white/30"
      />
      <Select value={filter.mode || 'all'} onValueChange={(v) => setFilter({ ...filter, mode: v === 'all' ? '' : v })}>
        <SelectTrigger className="w-40 bg-[#1a1333] border-[#3a295a] text-white"><SelectValue placeholder="All modes" /></SelectTrigger>
        <SelectContent className="bg-[#1a1333] border-[#3a295a] text-white">
          <SelectItem value="all">All modes</SelectItem>
          <SelectItem value="managed">Managed</SelectItem>
          <SelectItem value="byok">BYOK</SelectItem>
        </SelectContent>
      </Select>
      <Select value={filter.agent_name || 'all'} onValueChange={(v) => setFilter({ ...filter, agent_name: v === 'all' ? '' : v })}>
        <SelectTrigger className="w-52 bg-[#1a1333] border-[#3a295a] text-white"><SelectValue placeholder="All agents" /></SelectTrigger>
        <SelectContent className="bg-[#1a1333] border-[#3a295a] text-white">
          <SelectItem value="all">All agents</SelectItem>
          {AGENT_OPTIONS.map(a => <SelectItem key={a.value} value={a.value}>{a.label}</SelectItem>)}
        </SelectContent>
      </Select>
      <Button variant="outline" className="border-white/15 text-white/80 hover:bg-white/5 hover:text-white" onClick={onRefresh} disabled={loading}>
        {loading ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <RefreshCw className="w-4 h-4 mr-1" />} Refresh
      </Button>
      <Button className="bg-violet-600 hover:bg-violet-700 text-white ml-auto" onClick={() => onAssign(null)}>
        <Plus className="w-4 h-4 mr-1" /> Assign Managed Key
      </Button>
    </div>

    {keys.length === 0 ? (
      <Card className={CARD_CLASS}>
        <CardContent className="p-12 text-center text-white/50">
          <Key className="w-10 h-10 text-white/20 mx-auto mb-3" />
          No keys match the current filters.
        </CardContent>
      </Card>
    ) : (
      <div className="space-y-2">
        {keys.map(k => (
          <div key={k.id} className={`${ROW_CLASS} rounded-lg p-4 flex items-center justify-between gap-4`}>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-white font-semibold truncate">{k.company_name}</span>
                <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
                  k.mode === 'managed'
                    ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30'
                    : 'bg-blue-500/15 text-blue-300 border border-blue-500/30'
                }`}>{k.mode}</span>
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-violet-500/15 text-violet-300 border border-violet-500/30">{k.provider}</span>
              </div>
              <p className="text-xs text-white/50 mt-1">{k.agent_label} • <span className="font-mono text-white/70">{k.masked}</span></p>
              <p className="text-[10px] text-white/30 mt-0.5">
                {k.assigned_by ? `Assigned by ${k.assigned_by}` : 'Self-added'} • {new Date(k.updated_at).toLocaleString()}
              </p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {k.mode === 'managed' && (
                <Button size="sm" className="bg-violet-600 hover:bg-violet-700 text-white" onClick={() => onAssign(k)}>
                  Replace
                </Button>
              )}
              <Button size="sm" variant="ghost" className="text-red-300 hover:text-red-200 hover:bg-red-500/10" onClick={() => onRevoke(k)}>
                <Trash2 className="w-4 h-4" />
              </Button>
            </div>
          </div>
        ))}
      </div>
    )}
  </div>
);

// -------------------- Pricing Tab --------------------
const PricingRow = ({ row, onSave, saving }) => {
  const [draft, setDraft] = useState({
    monthly_flat_usd: row.monthly_flat_usd,
    service_charge_usd: row.service_charge_usd,
    free_tokens_on_purchase: row.free_tokens_on_purchase,
  });
  const dirty = useMemo(() =>
    String(draft.monthly_flat_usd) !== String(row.monthly_flat_usd) ||
    String(draft.service_charge_usd) !== String(row.service_charge_usd) ||
    Number(draft.free_tokens_on_purchase) !== Number(row.free_tokens_on_purchase),
    [draft, row]
  );
  return (
    <div className={`${ROW_CLASS} rounded-lg p-4`}>
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-white font-semibold">{row.agent_label}</h4>
        <span className="text-[10px] text-white/40 font-mono">{row.agent_name}</span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
        <div>
          <Label className="text-white/60 text-xs">Monthly Flat (USD)</Label>
          <Input
            type="number" step="0.01"
            className="bg-[#1a1333] border-[#3a295a] text-white mt-1"
            value={draft.monthly_flat_usd}
            onChange={(e) => setDraft({ ...draft, monthly_flat_usd: e.target.value })}
          />
        </div>
        <div>
          <Label className="text-white/60 text-xs">Service Charge (USD)</Label>
          <Input
            type="number" step="0.01"
            className="bg-[#1a1333] border-[#3a295a] text-white mt-1"
            value={draft.service_charge_usd}
            onChange={(e) => setDraft({ ...draft, service_charge_usd: e.target.value })}
          />
        </div>
        <div>
          <Label className="text-white/60 text-xs">Free Tokens on Purchase</Label>
          <Input
            type="number"
            className="bg-[#1a1333] border-[#3a295a] text-white mt-1"
            value={draft.free_tokens_on_purchase}
            onChange={(e) => setDraft({ ...draft, free_tokens_on_purchase: e.target.value })}
          />
          <p className="text-[10px] text-white/40 mt-1">Currently: {formatTokens(Number(draft.free_tokens_on_purchase))}</p>
        </div>
      </div>
      <div className="flex items-center justify-between">
        <span className="text-[11px] text-white/30">
          Last updated: {row.updated_by ? `${row.updated_by} • ` : ''}{new Date(row.updated_at).toLocaleString()}
        </span>
        <Button
          size="sm"
          disabled={!dirty || saving}
          className="bg-violet-600 hover:bg-violet-700 text-white disabled:opacity-40"
          onClick={() => onSave(row.agent_name, draft)}
        >
          {saving ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <Save className="w-4 h-4 mr-1" />}
          Save
        </Button>
      </div>
    </div>
  );
};

const PricingTab = ({ pricing, onSave, savingAgent }) => (
  <div className="space-y-3">
    <div className="bg-gradient-to-r from-violet-500/10 to-fuchsia-500/10 border border-violet-500/20 rounded-lg p-3 flex items-start gap-2">
      <Info className="w-4 h-4 text-violet-300 mt-0.5 shrink-0" />
      <p className="text-xs text-white/70">
        Changes apply to <span className="text-white font-semibold">future purchases only</span> — existing token quotas are snapshotted at purchase time.
      </p>
    </div>
    {pricing.map(row => <PricingRow key={row.agent_name} row={row} onSave={onSave} saving={savingAgent === row.agent_name} />)}
  </div>
);

// -------------------- Quotas Tab --------------------
const QuotasTab = ({ quotas, onAdjust, filter, setFilter, onRefresh, loading }) => (
  <div className="space-y-4">
    <div className="flex items-center gap-2 flex-wrap">
      <Input
        placeholder="Search company..."
        value={filter.search || ''}
        onChange={(e) => setFilter({ ...filter, search: e.target.value })}
        className="bg-[#1a1333] border-[#3a295a] text-white w-60 placeholder:text-white/30"
      />
      <Select value={filter.agent_name || 'all'} onValueChange={(v) => setFilter({ ...filter, agent_name: v === 'all' ? '' : v })}>
        <SelectTrigger className="w-52 bg-[#1a1333] border-[#3a295a] text-white"><SelectValue placeholder="All agents" /></SelectTrigger>
        <SelectContent className="bg-[#1a1333] border-[#3a295a] text-white">
          <SelectItem value="all">All agents</SelectItem>
          {AGENT_OPTIONS.map(a => <SelectItem key={a.value} value={a.value}>{a.label}</SelectItem>)}
        </SelectContent>
      </Select>
      <Button variant="outline" className="border-white/15 text-white/80 hover:bg-white/5 hover:text-white" onClick={onRefresh} disabled={loading}>
        {loading ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <RefreshCw className="w-4 h-4 mr-1" />} Refresh
      </Button>
    </div>
    {quotas.length === 0 ? (
      <Card className={CARD_CLASS}>
        <CardContent className="p-12 text-center text-white/50">No quotas match.</CardContent>
      </Card>
    ) : (
      <div className="space-y-2">
        {quotas.map(q => {
          const pct = q.included_tokens > 0 ? Math.min(100, (q.used_tokens / q.included_tokens) * 100) : 0;
          const bar = pct >= 100 ? 'from-red-500 to-rose-500' : pct >= 80 ? 'from-amber-400 to-orange-500' : 'from-emerald-400 to-teal-500';
          return (
            <div key={q.id} className={`${ROW_CLASS} rounded-lg p-4`}>
              <div className="flex items-center justify-between mb-2 gap-3">
                <div className="min-w-0 flex-1">
                  <p className="text-white font-semibold truncate">{q.company_name}</p>
                  <p className="text-xs text-white/50">{q.agent_label}</p>
                </div>
                <div className="text-right shrink-0">
                  <p className="text-sm text-white">
                    <span className="font-semibold">{formatTokens(q.used_tokens)}</span>
                    <span className="text-white/40"> / {formatTokens(q.included_tokens)}</span>
                  </p>
                  <p className="text-[10px] text-white/40">{pct.toFixed(1)}% used</p>
                </div>
              </div>
              <div className="w-full h-1.5 bg-[#1a1333] rounded-full overflow-hidden border border-[#2d2342] mb-3">
                <div className={`h-full bg-gradient-to-r ${bar}`} style={{ width: `${pct}%` }} />
              </div>
              <div className="flex items-center gap-2 justify-end">
                <Button size="sm" variant="outline" className="border-white/15 text-white/80 hover:bg-white/5 hover:text-white" onClick={() => onAdjust(q, 'reset')}>
                  Reset used
                </Button>
                <Button size="sm" variant="outline" className="border-white/15 text-white/80 hover:bg-white/5 hover:text-white" onClick={() => onAdjust(q, 'add_tokens')}>
                  + Add tokens
                </Button>
                <Button size="sm" variant="outline" className="border-white/15 text-white/80 hover:bg-white/5 hover:text-white" onClick={() => onAdjust(q, 'set_included')}>
                  Set quota
                </Button>
              </div>
            </div>
          );
        })}
      </div>
    )}
  </div>
);

// -------------------- Requests Tab --------------------
const RequestsTab = ({ requests, onApprove, onReject, filter, setFilter, onRefresh, loading }) => (
  <div className="space-y-4">
    <div className="flex items-center gap-2 flex-wrap">
      <Select value={filter.status || 'all'} onValueChange={(v) => setFilter({ ...filter, status: v === 'all' ? '' : v })}>
        <SelectTrigger className="w-40 bg-[#1a1333] border-[#3a295a] text-white"><SelectValue placeholder="All" /></SelectTrigger>
        <SelectContent className="bg-[#1a1333] border-[#3a295a] text-white">
          <SelectItem value="all">All</SelectItem>
          <SelectItem value="pending">Pending</SelectItem>
          <SelectItem value="approved">Approved</SelectItem>
          <SelectItem value="rejected">Rejected</SelectItem>
        </SelectContent>
      </Select>
      <Input
        placeholder="Search company..."
        value={filter.search || ''}
        onChange={(e) => setFilter({ ...filter, search: e.target.value })}
        className="bg-[#1a1333] border-[#3a295a] text-white w-60 placeholder:text-white/30"
      />
      <Button variant="outline" className="border-white/15 text-white/80 hover:bg-white/5 hover:text-white" onClick={onRefresh} disabled={loading}>
        {loading ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : <RefreshCw className="w-4 h-4 mr-1" />} Refresh
      </Button>
    </div>
    {requests.length === 0 ? (
      <Card className={CARD_CLASS}>
        <CardContent className="p-12 text-center text-white/50">
          <Inbox className="w-10 h-10 text-white/20 mx-auto mb-2" /> No requests.
        </CardContent>
      </Card>
    ) : (
      <div className="space-y-2">
        {requests.map(r => {
          const s = {
            pending: { class: 'bg-amber-500/15 text-amber-300 border-amber-500/30', icon: <Info className="w-3 h-3" /> },
            approved: { class: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30', icon: <CheckCircle2 className="w-3 h-3" /> },
            rejected: { class: 'bg-red-500/15 text-red-300 border-red-500/30', icon: <XCircle className="w-3 h-3" /> },
          }[r.status];
          return (
            <div key={r.id} className={`${ROW_CLASS} rounded-lg p-4`}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-white font-semibold">{r.company_name}</p>
                    <span className={`flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full border font-medium ${s.class}`}>
                      {s.icon}{r.status}
                    </span>
                  </div>
                  <p className="text-xs text-white/60 mt-0.5">{r.agent_label} — preferred: <span className="uppercase">{r.provider}</span></p>
                  {r.note && <p className="text-xs text-white/60 mt-1 italic">"{r.note}"</p>}
                  {r.admin_note && <p className="text-xs text-violet-300 mt-1">Admin: {r.admin_note}</p>}
                  <p className="text-[10px] text-white/30 mt-1">
                    {r.requested_by} • {new Date(r.created_at).toLocaleString()}
                  </p>
                </div>
                {r.status === 'pending' && (
                  <div className="flex items-center gap-2 shrink-0">
                    <Button size="sm" className="bg-emerald-600 hover:bg-emerald-700 text-white" onClick={() => onApprove(r)}>
                      <CheckCircle2 className="w-4 h-4 mr-1" /> Approve
                    </Button>
                    <Button size="sm" variant="outline" className="border-red-500/40 text-red-300 hover:bg-red-500/10" onClick={() => onReject(r)}>
                      <XCircle className="w-4 h-4 mr-1" /> Reject
                    </Button>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    )}
  </div>
);

// -------------------- Company Picker (searchable) --------------------
const CompanyPicker = ({ value, onChange, disabled }) => {
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
          value={selected ? `${selected.name} (#${selected.id})` : search}
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
  const { toast } = useToast();

  const [activeTab, setActiveTab] = useState('platform');
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState({});
  const [keys, setKeys] = useState([]);
  const [pricing, setPricing] = useState([]);
  const [quotas, setQuotas] = useState([]);
  const [requests, setRequests] = useState([]);
  const [platformKeys, setPlatformKeys] = useState([]);
  const [savingProvider, setSavingProvider] = useState(null);

  const [keyFilter, setKeyFilter] = useState({});
  const [quotaFilter, setQuotaFilter] = useState({});
  const [requestFilter, setRequestFilter] = useState({});

  const [assignModal, setAssignModal] = useState({ open: false, replacingKey: null, prefillRequest: null });
  const [assignForm, setAssignForm] = useState({ company_id: '', agent_name: 'frontline_agent', provider: 'openai', api_key: '' });
  const [rejectModal, setRejectModal] = useState({ open: false, request: null, note: '' });
  const [adjustModal, setAdjustModal] = useState({ open: false, quota: null, action: '', value: '' });

  const [submitting, setSubmitting] = useState(false);
  const [savingAgent, setSavingAgent] = useState(null);

  const loadAll = async () => {
    setLoading(true);
    try {
      const [o, k, p, q, r, pk] = await Promise.all([
        adminApiKeysService.getOverview(),
        adminApiKeysService.listAllKeys(keyFilter),
        adminApiKeysService.listPricing(),
        adminApiKeysService.listQuotas(quotaFilter),
        adminApiKeysService.listRequests(requestFilter),
        adminApiKeysService.listPlatformKeys(),
      ]);
      setStats(o.stats || {});
      setKeys(k.keys || []);
      setPricing(p.pricing || []);
      setQuotas(q.quotas || []);
      setRequests(r.requests || []);
      setPlatformKeys(pk.platform_keys || []);
    } catch (e) {
      toast({ title: 'Load failed', description: String(e.message || e), variant: 'destructive' });
    } finally {
      setLoading(false);
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

  useEffect(() => { loadAll(); /* eslint-disable-next-line */ }, []);

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
      const r = await adminApiKeysService.listRequests(requestFilter);
      setRequests(r.requests || []);
    } catch (e) { toast({ title: 'Failed', description: String(e.message || e), variant: 'destructive' }); }
  };

  useEffect(() => { const t = setTimeout(reloadKeys, 300); return () => clearTimeout(t); /* eslint-disable-next-line */ }, [keyFilter]);
  useEffect(() => { const t = setTimeout(reloadQuotas, 300); return () => clearTimeout(t); /* eslint-disable-next-line */ }, [quotaFilter]);
  useEffect(() => { const t = setTimeout(reloadRequests, 300); return () => clearTimeout(t); /* eslint-disable-next-line */ }, [requestFilter]);

  const openAssign = (existingOrRequest, prefill = null) => {
    if (prefill) {
      setAssignForm({
        company_id: prefill.company_id,
        agent_name: prefill.agent_name,
        provider: prefill.provider || 'openai',
        api_key: '',
      });
      setAssignModal({ open: true, replacingKey: null, prefillRequest: prefill });
    } else if (existingOrRequest) {
      setAssignForm({
        company_id: existingOrRequest.company_id,
        agent_name: existingOrRequest.agent_name,
        provider: existingOrRequest.provider || 'openai',
        api_key: '',
      });
      setAssignModal({ open: true, replacingKey: existingOrRequest, prefillRequest: null });
    } else {
      setAssignForm({ company_id: '', agent_name: 'frontline_agent', provider: 'openai', api_key: '' });
      setAssignModal({ open: true, replacingKey: null, prefillRequest: null });
    }
  };

  const submitAssign = async () => {
    if (!assignForm.company_id || !assignForm.api_key) {
      toast({ title: 'Missing fields', description: 'Company and API key are required.', variant: 'destructive' });
      return;
    }
    setSubmitting(true);
    try {
      const payload = {
        company_id: Number(assignForm.company_id),
        agent_name: assignForm.agent_name,
        provider: assignForm.provider,
        api_key: assignForm.api_key,
      };
      if (assignModal.prefillRequest) payload.request_id = assignModal.prefillRequest.id;
      await adminApiKeysService.assignManagedKey(payload);
      toast({ title: 'Key assigned', description: 'Company can now use this managed key.' });
      setAssignModal({ open: false, replacingKey: null, prefillRequest: null });
      loadAll();
    } catch (e) {
      toast({ title: 'Assign failed', description: String(e.message || e), variant: 'destructive' });
    } finally { setSubmitting(false); }
  };

  const revokeOne = async (k) => {
    if (!window.confirm(`Revoke ${k.mode} key for ${k.company_name} — ${k.agent_label}?`)) return;
    try {
      await adminApiKeysService.revokeKey(k.id);
      toast({ title: 'Revoked' });
      reloadKeys(); loadAll();
    } catch (e) {
      toast({ title: 'Revoke failed', description: String(e.message || e), variant: 'destructive' });
    }
  };

  const savePricing = async (agentName, draft) => {
    setSavingAgent(agentName);
    try {
      await adminApiKeysService.updatePricing(agentName, {
        monthly_flat_usd: draft.monthly_flat_usd,
        service_charge_usd: draft.service_charge_usd,
        free_tokens_on_purchase: Number(draft.free_tokens_on_purchase),
      });
      toast({ title: 'Pricing saved' });
      const p = await adminApiKeysService.listPricing();
      setPricing(p.pricing || []);
    } catch (e) {
      toast({ title: 'Save failed', description: String(e.message || e), variant: 'destructive' });
    } finally { setSavingAgent(null); }
  };

  const openAdjust = (quota, action) => {
    setAdjustModal({ open: true, quota, action, value: action === 'reset' ? '' : '1000000' });
  };

  const submitAdjust = async () => {
    const { quota, action, value } = adjustModal;
    setSubmitting(true);
    try {
      const payload = action === 'reset' ? { action } : { action, value: Number(value) };
      await adminApiKeysService.adjustQuota(quota.id, payload);
      toast({ title: 'Quota updated' });
      setAdjustModal({ open: false, quota: null, action: '', value: '' });
      reloadQuotas(); loadAll();
    } catch (e) {
      toast({ title: 'Adjust failed', description: String(e.message || e), variant: 'destructive' });
    } finally { setSubmitting(false); }
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
        <DashboardNavbar icon={Settings} title="Super Admin — API Keys" subtitle="Control plane for keys, pricing, quotas & requests" />

        <div className="container mx-auto px-4 py-8 max-w-7xl">
          <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
            <div>
              <button onClick={() => navigate('/admin/dashboard')} className="flex items-center gap-1 text-sm text-white/50 hover:text-white mb-2 transition-colors">
                <ChevronLeft className="w-4 h-4" /> Back to admin dashboard
              </button>
              <h1 className="text-2xl sm:text-3xl font-bold text-white flex items-center gap-2">
                <Sparkles className="w-6 h-6 text-violet-400" /> API Keys Control Panel
              </h1>
              <p className="text-sm text-white/50 mt-1">Assign managed keys, set pricing, adjust quotas, review requests.</p>
            </div>
          </div>

          <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
            <TabsList className="bg-[#1a1333] border border-[#3a295a] rounded-xl p-1 flex gap-1 h-auto flex-wrap mb-6">
              {[
                { value: 'platform', icon: Globe, label: 'Platform Keys' },
                { value: 'overview', icon: Gauge, label: 'Overview' },
                { value: 'keys', icon: Key, label: 'Per-Company Keys' },
                { value: 'pricing', icon: DollarSign, label: 'Pricing' },
                { value: 'quotas', icon: Gauge, label: 'Quotas' },
                { value: 'requests', icon: Inbox, label: `Requests${stats.pending_requests ? ` (${stats.pending_requests})` : ''}` },
              ].map(t => (
                <TabsTrigger
                  key={t.value}
                  value={t.value}
                  className="flex items-center gap-2 data-[state=active]:bg-violet-600 data-[state=active]:text-white data-[state=active]:shadow-[0_0_12px_rgba(139,92,246,0.3)] text-white/60 hover:text-white"
                >
                  <t.icon className="h-4 w-4" />
                  <span className="text-sm">{t.label}</span>
                </TabsTrigger>
              ))}
            </TabsList>

            <TabsContent value="platform">
              {loading ? <div className="flex justify-center py-20"><Loader2 className="w-8 h-8 animate-spin text-violet-400" /></div>
                : <PlatformTab platformKeys={platformKeys} onSave={savePlatformKey} savingProvider={savingProvider} />}
            </TabsContent>
            <TabsContent value="overview">
              {loading ? <div className="flex justify-center py-20"><Loader2 className="w-8 h-8 animate-spin text-violet-400" /></div> : <OverviewTab stats={stats} />}
            </TabsContent>
            <TabsContent value="keys">
              <KeysTab keys={keys} onAssign={openAssign} onRevoke={revokeOne} filter={keyFilter} setFilter={setKeyFilter} onRefresh={reloadKeys} loading={loading} />
            </TabsContent>
            <TabsContent value="pricing">
              <PricingTab pricing={pricing} onSave={savePricing} savingAgent={savingAgent} />
            </TabsContent>
            <TabsContent value="quotas">
              <QuotasTab quotas={quotas} onAdjust={openAdjust} filter={quotaFilter} setFilter={setQuotaFilter} onRefresh={reloadQuotas} loading={loading} />
            </TabsContent>
            <TabsContent value="requests">
              <RequestsTab
                requests={requests}
                onApprove={(r) => openAssign(null, r)}
                onReject={(r) => setRejectModal({ open: true, request: r, note: '' })}
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
        <DialogContent className="bg-[#120d22] border border-[#2d2342] text-white">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Key className="w-5 h-5 text-violet-400" />
              {assignModal.replacingKey ? 'Replace Managed Key' : assignModal.prefillRequest ? 'Approve & Assign Key' : 'Assign Managed Key'}
            </DialogTitle>
            <DialogDescription className="text-white/60">
              The key is encrypted on save. Only a masked preview will be visible afterward.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div>
              <Label className="text-white/70 text-sm">Company</Label>
              <div className="mt-1">
                <CompanyPicker
                  value={assignForm.company_id}
                  onChange={(id) => setAssignForm({ ...assignForm, company_id: id })}
                  disabled={!!assignModal.replacingKey || !!assignModal.prefillRequest}
                />
              </div>
              {(assignModal.replacingKey || assignModal.prefillRequest) && (
                <p className="text-[11px] text-white/50 mt-1">
                  Locked: {(assignModal.replacingKey?.company_name) || (assignModal.prefillRequest?.company_name)}
                </p>
              )}
            </div>
            <div>
              <Label className="text-white/70 text-sm">Agent</Label>
              <Select
                value={assignForm.agent_name}
                onValueChange={(v) => setAssignForm({ ...assignForm, agent_name: v })}
                disabled={!!assignModal.replacingKey || !!assignModal.prefillRequest}
              >
                <SelectTrigger className="bg-[#1a1333] border-[#3a295a] text-white mt-1"><SelectValue /></SelectTrigger>
                <SelectContent className="bg-[#1a1333] border-[#3a295a] text-white">
                  {AGENT_OPTIONS.map(a => <SelectItem key={a.value} value={a.value}>{a.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-white/70 text-sm">Provider</Label>
              <Select value={assignForm.provider} onValueChange={(v) => setAssignForm({ ...assignForm, provider: v })}>
                <SelectTrigger className="bg-[#1a1333] border-[#3a295a] text-white mt-1"><SelectValue /></SelectTrigger>
                <SelectContent className="bg-[#1a1333] border-[#3a295a] text-white">
                  {PROVIDER_OPTIONS.map(p => <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-white/70 text-sm">API Key</Label>
              <Input
                type="password" autoComplete="off" placeholder="sk-..."
                className="bg-[#1a1333] border-[#3a295a] text-white mt-1 font-mono"
                value={assignForm.api_key}
                onChange={(e) => setAssignForm({ ...assignForm, api_key: e.target.value })}
              />
            </div>
          </div>
          <DialogFooter>
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
            <DialogTitle>Adjust Quota — {adjustModal.quota?.company_name}</DialogTitle>
            <DialogDescription className="text-white/60">
              {adjustModal.quota?.agent_label} • used {formatTokens(adjustModal.quota?.used_tokens)} of {formatTokens(adjustModal.quota?.included_tokens)}
            </DialogDescription>
          </DialogHeader>
          {adjustModal.action === 'reset' ? (
            <p className="text-sm text-white/70 py-2">
              Reset <span className="font-semibold text-white">used_tokens</span> to 0. Included tokens unchanged. This gives the company a clean slate for the current period.
            </p>
          ) : (
            <div className="space-y-2 py-2">
              <Label className="text-white/70 text-sm">
                {adjustModal.action === 'add_tokens' ? 'Tokens to add' : 'New included tokens'}
              </Label>
              <Input
                type="number" className="bg-[#1a1333] border-[#3a295a] text-white"
                value={adjustModal.value}
                onChange={(e) => setAdjustModal({ ...adjustModal, value: e.target.value })}
              />
              <p className="text-[11px] text-white/40">
                {adjustModal.action === 'add_tokens' && `Will set included to ${formatTokens((adjustModal.quota?.included_tokens || 0) + Number(adjustModal.value || 0))}`}
                {adjustModal.action === 'set_included' && `Will set included to ${formatTokens(Number(adjustModal.value || 0))}`}
              </p>
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
    </>
  );
};

export default SuperAdminApiKeysPage;
