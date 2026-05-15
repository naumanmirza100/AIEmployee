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
  Inbox, Building2, Sparkles, Save, Plus, Info, Settings, Globe, Search, Clock, CreditCard
} from 'lucide-react';
import DashboardNavbar from '@/components/common/DashboardNavbar';
import adminApiKeysService from '@/services/adminApiKeysService';

const GRADIENT_BG = 'linear-gradient(135deg, #020308 0%, #0a0a1a 25%, #0d0b1f 50%, #0f0a20 75%, #020308 100%)';
const CARD_CLASS = 'bg-[#120d22] border border-[#2d2342]';
const ROW_CLASS = 'bg-[#0f0a20] border border-[#2d2342] hover:border-violet-500/30 transition-colors';

const ProviderLogo = ({ provider, size = 20 }) => {
  const s = size;
  switch (provider) {
    case 'groq': return (
      <svg width={s} height={s} viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="32" cy="32" r="32" fill="#F55036"/>
        <path d="M44 26H36V38H44C44 38 48 38 48 32C48 26 44 26 44 26Z" fill="white"/>
        <path d="M20 26C20 26 16 26 16 32C16 38 20 38 20 38H32V32H24V30H32V26H20Z" fill="white"/>
      </svg>
    );
    case 'openai': return (
      <svg width={s} height={s} viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="32" cy="32" r="32" fill="#10a37f"/>
        <path d="M46 28.5C46 22.7 41.3 18 35.5 18C32.4 18 29.6 19.3 27.6 21.4C26.7 21.1 25.7 21 24.7 21C19.7 21 15.7 25 15.7 30C15.7 30.9 15.8 31.8 16.1 32.6C14.8 33.9 14 35.7 14 37.7C14 41.7 17.3 45 21.3 45C22.3 45 23.2 44.8 24.1 44.4C25.8 45.4 27.7 46 29.8 46C33 46 35.9 44.6 37.9 42.4C38.4 42.5 38.9 42.5 39.4 42.5C44.1 42.5 48 38.6 48 33.9C48 31.9 47.3 30.1 46.1 28.7L46 28.5Z" fill="white" opacity="0.9"/>
      </svg>
    );
    case 'claude': return (
      <svg width={s} height={s} viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="32" cy="32" r="32" fill="#CC785C"/>
        <text x="32" y="42" textAnchor="middle" fontSize="28" fontWeight="bold" fill="white" fontFamily="serif">A</text>
      </svg>
    );
    case 'gemini': return (
      <svg width={s} height={s} viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="32" cy="32" r="32" fill="#1a73e8"/>
        <path d="M32 14C32 14 22 32 32 32C42 32 32 50 32 50C32 50 42 32 32 32C22 32 32 14 32 14Z" fill="white"/>
      </svg>
    );
    case 'grok': return (
      <svg width={s} height={s} viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="32" cy="32" r="32" fill="#000"/>
        <text x="32" y="42" textAnchor="middle" fontSize="28" fontWeight="bold" fill="white" fontFamily="sans-serif">X</text>
      </svg>
    );
    default: return (
      <div style={{ width: s, height: s }} className="rounded-full bg-violet-500/30 flex items-center justify-center text-white text-xs font-bold">
        {provider[0]?.toUpperCase()}
      </div>
    );
  }
};

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
    {/* Row 1: Company & request health */}
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      <StatCard icon={Building2} label="Companies" value={stats.total_companies ?? '—'} accent="bg-violet-500/15 text-violet-300" />
      <StatCard icon={Gauge} label="Active Purchases" value={stats.total_purchases ?? '—'} accent="bg-fuchsia-500/15 text-fuchsia-300" />
      <StatCard icon={Inbox} label="Pending Requests" value={stats.pending_requests ?? '—'} accent={stats.pending_requests > 0 ? 'bg-amber-500/15 text-amber-300' : 'bg-gray-500/15 text-gray-400'} />
      <StatCard icon={Globe} label="Platform Keys Set" value={stats.platform_keys_configured ?? '—'} accent={stats.platform_keys_configured > 0 ? 'bg-emerald-500/15 text-emerald-300' : 'bg-red-500/15 text-red-300'} />
    </div>

    {/* Row 2: Keys breakdown */}
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      <StatCard icon={ShieldCheck} label="Active Keys (Total)" value={stats.total_keys ?? '—'} accent="bg-emerald-500/15 text-emerald-300" />
      <StatCard icon={Key} label="Managed Keys" value={stats.managed_keys ?? '—'} accent="bg-emerald-500/15 text-emerald-300" />
      <StatCard icon={Key} label="BYOK Keys" value={stats.byok_keys ?? '—'} accent="bg-blue-500/15 text-blue-300" />
      {/* Exhausted Quotas — dual number card */}
      {(() => {
        const hasExhausted = (stats.exhausted_quotas > 0 || stats.exhausted_managed_quotas > 0);
        const accent = hasExhausted ? 'bg-red-500/15 text-red-300' : 'bg-gray-500/15 text-gray-400';
        return (
          <div className={`${CARD_CLASS} rounded-xl p-4 hover:border-violet-500/30 transition-colors`}>
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <p className="text-[11px] uppercase tracking-wider text-white/40 mb-2">Exhausted Quotas</p>
                <div className="flex items-end gap-3">
                  <div>
                    <p className="text-2xl font-bold text-white leading-none">{stats.exhausted_quotas ?? 0}</p>
                    <p className="text-[10px] text-white/40 mt-1">free</p>
                  </div>
                  <span className="text-white/20 text-lg mb-4">·</span>
                  <div>
                    <p className="text-2xl font-bold text-white leading-none">{stats.exhausted_managed_quotas ?? 0}</p>
                    <p className="text-[10px] text-white/40 mt-1">managed</p>
                  </div>
                </div>
              </div>
              <div className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${accent}`}>
                <AlertTriangle className="w-5 h-5" />
              </div>
            </div>
          </div>
        );
      })()}
    </div>

    {/* Token Ledger */}
    <Card className={CARD_CLASS}>
      <CardHeader>
        <CardTitle className="text-white flex items-center gap-2">
          <Gauge className="w-5 h-5 text-violet-400" /> Token Ledger
        </CardTitle>
        <CardDescription className="text-white/50">Aggregate token usage across all companies and agents.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Free platform tokens */}
        <div>
          <p className="text-xs text-white/40 uppercase tracking-wider mb-2">Free Platform Tokens</p>
          <div className="grid grid-cols-2 gap-3">
            <div className="p-4 bg-[#1a1333] border border-[#2d2342] rounded-lg">
              <p className="text-xs text-white/40 uppercase mb-1">Included</p>
              <p className="text-xl font-bold text-white">{formatTokens(stats.total_included_tokens)}</p>
            </div>
            <div className="p-4 bg-[#1a1333] border border-[#2d2342] rounded-lg">
              <p className="text-xs text-white/40 uppercase mb-1">Used</p>
              <p className="text-xl font-bold text-violet-300">{formatTokens(stats.total_used_tokens)}</p>
            </div>
          </div>
        </div>
        {/* Managed key tokens */}
        <div>
          <p className="text-xs text-white/40 uppercase tracking-wider mb-2">Managed Key Tokens</p>
          <div className="grid grid-cols-2 gap-3">
            <div className="p-4 bg-[#1a1333] border border-[#2d2342] rounded-lg">
              <p className="text-xs text-white/40 uppercase mb-1">Included</p>
              <p className="text-xl font-bold text-white">{formatTokens(stats.total_managed_included_tokens)}</p>
            </div>
            <div className="p-4 bg-[#1a1333] border border-[#2d2342] rounded-lg">
              <p className="text-xs text-white/40 uppercase mb-1">Used</p>
              <p className="text-xl font-bold text-emerald-300">{formatTokens(stats.total_managed_used_tokens)}</p>
            </div>
          </div>
        </div>
        {/* BYOK info */}
        <div className="p-4 bg-[#1a1333] border border-[#2d2342] rounded-lg">
          <p className="text-xs text-white/40 uppercase mb-1">BYOK (tracked, info only)</p>
          <p className="text-xl font-bold text-blue-300">{formatTokens(stats.total_byok_info_tokens)}</p>
        </div>
        {/* Per-provider breakdown */}
        {stats.provider_totals && Object.keys(stats.provider_totals).length > 0 && (
          <div>
            <p className="text-xs text-white/40 uppercase mb-2">By Provider</p>
            <div className="flex flex-wrap gap-2">
              {Object.entries(stats.provider_totals).map(([provider, tokens]) => (
                <div key={provider} className="p-3 bg-[#1a1333] border border-[#2d2342] rounded-lg text-center hover:border-violet-500/30 transition-colors min-w-[110px]">
                  <div className="flex items-center justify-center mb-1.5">
                    <ProviderLogo provider={provider} size={24} />
                  </div>
                  <p className="text-[10px] uppercase font-semibold text-white/50 tracking-wider">{provider}</p>
                  <p className="text-base font-bold text-white mt-1">{formatTokens(tokens)}</p>
                  <p className="text-[10px] text-white/30 mt-0.5">tokens</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  </div>
);

// -------------------- Keys Tab --------------------
const KeysTab = ({ keys, onAssign, onRevoke, onAdjustQuota, filter, setFilter, onRefresh, loading }) => (
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
        {keys.map(k => {
          const q = k.quota;
          const freePct = q && q.included_tokens > 0 ? Math.min(100, (q.used_tokens / q.included_tokens) * 100) : 0;
          const mPct = q && q.managed_included_tokens > 0 ? Math.min(100, (q.managed_used_tokens / q.managed_included_tokens) * 100) : 0;
          const freeBar = freePct >= 100 ? 'bg-red-500' : freePct >= 80 ? 'bg-amber-400' : 'bg-emerald-400';
          const mBar = mPct >= 100 ? 'bg-red-500' : mPct >= 80 ? 'bg-amber-400' : 'bg-violet-500';
          return (
            <div key={k.id} className={`${ROW_CLASS} rounded-lg p-4`}>
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-white font-semibold truncate">{k.company_name}</span>
                    <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium ${
                      k.status === 'revoked'
                        ? 'bg-red-500/15 text-red-300 border border-red-500/30'
                        : k.mode === 'managed'
                          ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30'
                          : 'bg-blue-500/15 text-blue-300 border border-blue-500/30'
                    }`}>{k.status === 'revoked' ? 'revoked' : k.mode}</span>
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-violet-500/15 text-violet-300 border border-violet-500/30">{k.provider}</span>
                  </div>
                  <p className="text-xs text-white/50 mt-1">{k.agent_label} • <span className="font-mono text-white/70">{k.masked}</span></p>
                  <p className="text-[10px] text-white/30 mt-0.5">
                    {k.assigned_by ? `Assigned by ${k.assigned_by}` : 'Self-added'} • {new Date(k.updated_at).toLocaleString()}
                  </p>

                  {/* Token usage */}
                  {q ? (
                    <div className="mt-3 space-y-2">
                      {/* <div>
                        <div className="flex items-center justify-between text-[10px] text-white/40 mb-1">
                          <span>Free tokens</span>
                          <span>{formatTokens(Math.min(q.used_tokens, q.included_tokens))} / {formatTokens(q.included_tokens)} ({freePct.toFixed(0)}%)</span>
                        </div>
                        <div className="w-full h-1.5 bg-[#1a1333] rounded-full overflow-hidden border border-[#2d2342]">
                          <div className={`h-full ${freeBar} transition-all`} style={{ width: `${freePct}%` }} />
                        </div>
                      </div> */}
                      {q.managed_included_tokens > 0 && (
                        <div>
                          <div className="flex items-center justify-between text-[10px] text-white/40 mb-1">
                            <span>Managed key tokens</span>
                            <span>{formatTokens(Math.min(q.managed_used_tokens, q.managed_included_tokens))} / {formatTokens(q.managed_included_tokens)} ({mPct.toFixed(0)}%)</span>
                          </div>
                          <div className="w-full h-1.5 bg-[#1a1333] rounded-full overflow-hidden border border-[#2d2342]">
                            <div className={`h-full ${mBar} transition-all`} style={{ width: `${mPct}%` }} />
                          </div>
                        </div>
                      )}
                    </div>
                  ) : (
                    <p className="text-[10px] text-white/25 mt-2 italic">No quota record yet</p>
                  )}
                </div>

                <div className="flex flex-col items-end gap-2 shrink-0">
                  {q && (
                    <Button size="sm" variant="outline" className="border-white/15 text-white/70 hover:bg-white/5 hover:text-white text-xs" onClick={() => onAdjustQuota(q, k)}>
                      {/* <Gauge className="w-3 h-3 mr-1" /> */}
                       Edit tokens
                    </Button>
                  )}
                  {k.status === 'revoked' ? (
                    <Button size="sm" className=" bg-violet-600 hover:bg-violet-700 text-white" onClick={() => onAssign(k)}>
                      Re-assign
                    </Button>
                  ) : (
                    <>
                      {k.mode === 'managed' && (
                        <Button size="sm" className="pr-4 pl-4 bg-violet-600 hover:bg-violet-700 text-white" onClick={() => onAssign(k)}>
                          Replace
                        </Button>
                      )}
                      <Button size="sm" variant="ghost" className="text-red-300 hover:text-red-200 hover:bg-red-500/10" onClick={() => onRevoke(k)}>
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </>
                  )}
                </div>
              </div>
            </div>
          );
        })}
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
    managed_key_tokens: row.managed_key_tokens ?? 0,
  });
  const dirty = useMemo(() =>
    String(draft.monthly_flat_usd) !== String(row.monthly_flat_usd) ||
    String(draft.service_charge_usd) !== String(row.service_charge_usd) ||
    Number(draft.free_tokens_on_purchase) !== Number(row.free_tokens_on_purchase) ||
    Number(draft.managed_key_tokens) !== Number(row.managed_key_tokens ?? 0),
    [draft, row]
  );
  return (
    <div className={`${ROW_CLASS} rounded-lg p-4`}>
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-white font-semibold">{row.agent_label}</h4>
        <span className="text-[10px] text-white/40 font-mono">{row.agent_name}</span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
        <div>
          <Label className="text-white/60 text-xs">Key Cost (USD) <span className="text-white/30">— pre-filled in Approve modal</span></Label>
          <Input
            type="number" step="0.01"
            className="bg-[#1a1333] border-[#3a295a] text-white mt-1"
            value={draft.monthly_flat_usd}
            onChange={(e) => setDraft({ ...draft, monthly_flat_usd: e.target.value })}
          />
        </div>
        <div>
          <Label className="text-white/60 text-xs">Service Charge (USD) <span className="text-white/30">— pre-filled in Approve modal</span></Label>
          <Input
            type="number" step="0.01"
            className="bg-[#1a1333] border-[#3a295a] text-white mt-1"
            value={draft.service_charge_usd}
            onChange={(e) => setDraft({ ...draft, service_charge_usd: e.target.value })}
          />
        </div>
        <div>
          <Label className="text-white/60 text-xs">Free Platform Tokens <span className="text-white/30">— included with agent purchase</span></Label>
          <Input
            type="number"
            className="bg-[#1a1333] border-[#3a295a] text-white mt-1"
            value={draft.free_tokens_on_purchase}
            onChange={(e) => setDraft({ ...draft, free_tokens_on_purchase: e.target.value })}
          />
          <p className="text-[10px] text-white/40 mt-1">{formatTokens(Number(draft.free_tokens_on_purchase))} — updates all existing quotas on save</p>
        </div>
        <div>
          <Label className="text-white/60 text-xs">Managed Key Tokens <span className="text-white/30">— granted when paid key is assigned</span></Label>
          <Input
            type="number"
            className="bg-[#1a1333] border-[#3a295a] text-white mt-1"
            value={draft.managed_key_tokens}
            onChange={(e) => setDraft({ ...draft, managed_key_tokens: e.target.value })}
          />
          <p className="text-[10px] text-white/40 mt-1">{formatTokens(Number(draft.managed_key_tokens))}</p>
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
      <p className="text-xs text-white/70 leading-relaxed">
        <span className="text-white font-semibold">Key Cost</span> and <span className="text-white font-semibold">Service Charge</span> are pre-filled in the Approve Request modal — admin can still override them per company.{' '}
        <span className="text-white font-semibold">Free Tokens</span> are automatically granted when a managed key is assigned.
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
          const mPct = q.managed_included_tokens > 0 ? Math.min(100, (q.managed_used_tokens / q.managed_included_tokens) * 100) : 0;
          const mBar = mPct >= 100 ? 'from-red-500 to-rose-500' : mPct >= 80 ? 'from-amber-400 to-orange-500' : 'from-violet-500 to-purple-500';
          return (
            <div key={q.id} className={`${ROW_CLASS} rounded-lg p-4`}>
              <div className="flex items-center justify-between mb-2 gap-3">
                <div className="min-w-0 flex-1">
                  <p className="text-white font-semibold truncate">{q.company_name}</p>
                  <p className="text-xs text-white/50">{q.agent_label}</p>
                </div>
              </div>

              {/* Free platform tokens */}
              <div className="mb-3">
                <div className="flex items-center justify-between text-[10px] text-white/40 mb-1">
                  <span className="uppercase tracking-wider font-medium">Free platform tokens</span>
                  <span>
                    {formatTokens(Math.min(q.used_tokens, q.included_tokens))} / {formatTokens(q.included_tokens)}
                    <span className="ml-1 text-white/30">({pct.toFixed(1)}% used)</span>
                  </span>
                </div>
                <div className="w-full h-1.5 bg-[#1a1333] rounded-full overflow-hidden border border-[#2d2342]">
                  <div className={`h-full bg-gradient-to-r ${bar}`} style={{ width: `${pct}%` }} />
                </div>
              </div>

              {/* Managed key tokens */}
              {q.managed_included_tokens > 0 && (
                <div className="mb-3">
                  <div className="flex items-center justify-between text-[10px] text-white/40 mb-1">
                    <span className="uppercase tracking-wider font-medium">Managed key tokens</span>
                    <span>
                      {formatTokens(Math.min(q.managed_used_tokens, q.managed_included_tokens))} / {formatTokens(q.managed_included_tokens)}
                      <span className="ml-1 text-white/30">({mPct.toFixed(1)}% used)</span>
                    </span>
                  </div>
                  <div className="w-full h-1.5 bg-[#1a1333] rounded-full overflow-hidden border border-[#2d2342]">
                    <div className={`h-full bg-gradient-to-r ${mBar}`} style={{ width: `${mPct}%` }} />
                  </div>
                </div>
              )}

              {q.provider_breakdown && Object.keys(q.provider_breakdown).length > 0 && (
                <div className="flex flex-wrap gap-1.5 mb-3">
                  {Object.entries(q.provider_breakdown).map(([provider, tokens]) => (
                    <span key={provider} className="text-[10px] px-2 py-0.5 rounded-full bg-[#1a1333] border border-[#2d2342] text-white/60">
                      <span className="text-white/80 font-semibold uppercase">{provider}</span>
                      {' '}{formatTokens(Math.min(tokens, q.included_tokens))}
                    </span>
                  ))}
                </div>
              )}

              <div className="flex items-center gap-2 justify-between flex-wrap">
                <div className="flex items-center gap-2">
                <span className="text-[10px] text-white/25 mr-auto">Free quota:</span>
                <Button size="sm" variant="outline" className="border-white/15 text-white/70 hover:bg-white/5 hover:text-white text-xs" onClick={() => onAdjust(q, 'reset')}>
                  Reset used
                </Button>
                {/* <Button size="sm" variant="outline" className="border-white/15 text-white/70 hover:bg-white/5 hover:text-white text-xs" onClick={() => onAdjust(q, 'add_tokens')}>
                  + Add
                </Button> */}
                <Button size="sm" variant="outline" className="border-white/15 text-white/70 hover:bg-white/5 hover:text-white text-xs" onClick={() => onAdjust(q, 'set_included')}>
                  Set
                </Button>
                </div>
                <div className="flex items-center gap-2">
                <span className="text-[10px] text-white/25 ml-2">Managed:</span>
                <Button size="sm" variant="outline" className="border-violet-500/30 text-violet-300 hover:bg-violet-500/10 text-xs" onClick={() => onAdjust(q, 'set_managed')}>
                  Set tokens
                </Button>
                <Button size="sm" variant="outline" className="border-violet-500/30 text-violet-300 hover:bg-violet-500/10 text-xs" onClick={() => onAdjust(q, 'reset_managed')}>
                  Reset used
                </Button>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    )}
  </div>
);

// -------------------- Requests Tab --------------------
const REQUEST_STATUS_META = {
  pending:          { label: 'Pending',           cls: 'bg-amber-500/15 text-amber-300 border-amber-500/30',     Icon: Clock },
  payment_pending:  { label: 'Payment Required',  cls: 'bg-yellow-500/15 text-yellow-300 border-yellow-500/30', Icon: DollarSign },
  payment_received: { label: 'Payment Received',  cls: 'bg-blue-500/15 text-blue-300 border-blue-500/30',       Icon: CreditCard },
  key_assigned:     { label: 'Key Assigned',      cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30', Icon: ShieldCheck },
  approved:         { label: 'Approved',          cls: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30', Icon: CheckCircle2 },
  rejected:         { label: 'Rejected',          cls: 'bg-red-500/15 text-red-300 border-red-500/30',           Icon: XCircle },
  revoked:          { label: 'Revoked',           cls: 'bg-orange-500/15 text-orange-300 border-orange-500/30',  Icon: XCircle },
};

const RequestsTab = ({ requests, onApprove, onAssignKey, onReject, filter, setFilter, onRefresh, loading, pricing }) => (
  <div className="space-y-4">
    <div className="flex items-center gap-2 flex-wrap">
      <Select value={filter.status || 'all'} onValueChange={(v) => setFilter({ ...filter, status: v === 'all' ? '' : v })}>
        <SelectTrigger className="w-48 bg-[#1a1333] border-[#3a295a] text-white"><SelectValue placeholder="All statuses" /></SelectTrigger>
        <SelectContent className="bg-[#1a1333] border-[#3a295a] text-white">
          <SelectItem value="all">All statuses</SelectItem>
          <SelectItem value="pending">Pending</SelectItem>
          <SelectItem value="payment_pending">Payment Required</SelectItem>
          <SelectItem value="payment_received">Payment Received</SelectItem>
          <SelectItem value="key_assigned">Key Assigned</SelectItem>
          <SelectItem value="approved">Approved (legacy)</SelectItem>
          <SelectItem value="rejected">Rejected</SelectItem>
          <SelectItem value="revoked">Revoked</SelectItem>
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
          const meta = REQUEST_STATUS_META[r.status] || REQUEST_STATUS_META.pending;
          const { Icon } = meta;
          const total = ((r.key_cost_snapshot ?? 0) + (r.service_charge_snapshot ?? 0));
          const agentPricing = pricing?.find(p => p.agent_name === r.agent_name);
          return (
            <div key={r.id} className={`${ROW_CLASS} rounded-lg p-4`}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-white font-semibold">{r.company_name}</p>
                    <span className={`flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full border font-medium ${meta.cls}`}>
                      <Icon className="w-3 h-3" />{meta.label}
                    </span>
                  </div>
                  <p className="text-xs text-white/60 mt-0.5">{r.agent_label} — <span className="uppercase">{r.provider}</span></p>
                  {r.note && <p className="text-xs text-white/60 mt-1 italic">"{r.note}"</p>}
                  {r.admin_note && <p className="text-xs text-violet-300 mt-1">Note: {r.admin_note}</p>}
                  {r.status === 'payment_pending' && total > 0 && (
                    <p className="text-xs text-yellow-300 mt-1">
                      Amount due: <span className="font-semibold">${total.toFixed(2)}</span>
                      <span className="text-white/40 ml-1">(key ${(r.key_cost_snapshot ?? 0).toFixed(2)} + service ${(r.service_charge_snapshot ?? 0).toFixed(2)})</span>
                    </p>
                  )}
                  {r.status === 'payment_received' && r.amount_paid != null && (
                    <p className="text-xs text-blue-300 mt-1">
                      Payment confirmed: <span className="font-semibold">${r.amount_paid.toFixed(2)}</span>
                      {r.paid_at && <span className="text-white/40 ml-1">• {new Date(r.paid_at).toLocaleString()}</span>}
                    </p>
                  )}
                  {agentPricing && agentPricing.managed_key_tokens > 0 && ['payment_pending', 'payment_received', 'key_assigned'].includes(r.status) && (
                    <p className="text-xs text-violet-300 mt-1">
                      <span className="text-white/40">Managed key tokens:</span>{' '}
                      <span className="font-semibold">{formatTokens(agentPricing.managed_key_tokens)}</span>
                      {' '}<span className="text-white/30">will be granted on key assignment</span>
                    </p>
                  )}
                  <p className="text-[10px] text-white/30 mt-1">
                    {r.requested_by} • {new Date(r.created_at).toLocaleString()}
                  </p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {r.status === 'pending' && (
                    <>
                      <Button size="sm" className="bg-emerald-600 hover:bg-emerald-700 text-white" onClick={() => onApprove(r)}>
                        <CheckCircle2 className="w-4 h-4 mr-1" /> Approve
                      </Button>
                      <Button size="sm" variant="outline" className="border-red-500/40 text-red-300 hover:bg-red-500/10" onClick={() => onReject(r)}>
                        <XCircle className="w-4 h-4 mr-1" /> Reject
                      </Button>
                    </>
                  )}
                  {r.status === 'payment_pending' && (
                    <span className="text-[10px] text-yellow-300/70 italic">Awaiting payment</span>
                  )}
                  {r.status === 'payment_received' && (
                    <Button size="sm" className="bg-violet-600 hover:bg-violet-700 text-white" onClick={() => onAssignKey(r)}>
                      <Key className="w-4 h-4 mr-1" /> Assign Key
                    </Button>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    )}
  </div>
);

// -------------------- Company Picker (searchable) --------------------
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
  const { toast } = useToast();

  const [activeTab, setActiveTab] = useState('overview');
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState({});
  const [keys, setKeys] = useState([]);
  const [pricing, setPricing] = useState([]);
  const [quotas, setQuotas] = useState([]);
  const [requests, setRequests] = useState([]);
  const [platformKeys, setPlatformKeys] = useState([]);
  const [savingProvider, setSavingProvider] = useState(null);

  const [keyFilter, setKeyFilter] = useState({ mode: 'managed' });
  const [quotaFilter, setQuotaFilter] = useState({});
  const [requestFilter, setRequestFilter] = useState({});

  const [assignModal, setAssignModal] = useState({ open: false, replacingKey: null, prefillRequest: null });
  const [assignForm, setAssignForm] = useState({ company_id: '', agent_name: 'frontline_agent', provider: 'openai', api_key: '' });
  const [approveModal, setApproveModal] = useState({ open: false, request: null, key_cost: '', service_charge: '', admin_note: '' });
  const [rejectModal, setRejectModal] = useState({ open: false, request: null, note: '' });
  const [adjustModal, setAdjustModal] = useState({ open: false, quota: null, action: '', value: '' });
  const [confirmDialog, setConfirmDialog] = useState({ open: false, title: '', description: '', onConfirm: null });

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
    setAdjustModal({ open: true, quota, action, value: defaultVal });
  };

  const submitAdjust = async () => {
    const { quota, action, value } = adjustModal;
    setSubmitting(true);
    try {
      const noValueActions = ['reset', 'reset_managed'];
      const payload = noValueActions.includes(action) ? { action } : { action, value: Number(value) };
      await adminApiKeysService.adjustQuota(quota.id, payload);
      toast({ title: 'Quota updated' });
      setAdjustModal({ open: false, quota: null, action: '', value: '' });
      reloadQuotas(); loadAll();
    } catch (e) {
      toast({ title: 'Adjust failed', description: String(e.message || e), variant: 'destructive' });
    } finally { setSubmitting(false); }
  };

  const submitApprove = async () => {
    setSubmitting(true);
    try {
      await adminApiKeysService.approveRequest(approveModal.request.id, {
        key_cost: Number(approveModal.key_cost) || 0,
        service_charge: Number(approveModal.service_charge) || 0,
        admin_note: approveModal.admin_note,
      });
      toast({ title: 'Request approved', description: 'Company notified to complete payment.' });
      setApproveModal({ open: false, request: null, key_cost: '', service_charge: '', admin_note: '' });
      reloadRequests(); loadAll();
    } catch (e) {
      toast({ title: 'Approve failed', description: String(e.message || e), variant: 'destructive' });
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
            <TabsList className="bg-[#1a1333] border border-[#3a295a] rounded-xl p-1 flex w-full h-auto mb-6">
              {[
                { value: 'overview', icon: Gauge, label: 'Overview' },
                { value: 'platform', icon: Globe, label: 'Platform Keys' },
                { value: 'keys', icon: Key, label: 'Per-Company Keys' },
                { value: 'pricing', icon: DollarSign, label: 'Pricing' },
                { value: 'quotas', icon: Gauge, label: 'Quotas' },
                { value: 'requests', icon: Inbox, label: 'Requests', badge: stats.pending_requests },
              ].map(t => (
                <TabsTrigger
                  key={t.value}
                  value={t.value}
                  className="flex-1 flex items-center justify-center gap-1.5 data-[state=active]:bg-violet-600 data-[state=active]:text-white data-[state=active]:shadow-[0_0_12px_rgba(139,92,246,0.3)] text-white/60 hover:text-white rounded-lg py-2"
                >
                  <t.icon className="h-4 w-4 shrink-0" />
                  <span className="text-sm font-medium truncate">{t.label}</span>
                  {t.badge > 0 && (
                    <span className="flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full bg-red-500 text-white text-[10px] font-bold shrink-0">
                      {t.badge > 99 ? '99+' : t.badge}
                    </span>
                  )}
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
              <KeysTab
                keys={keys}
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
              <QuotasTab quotas={quotas} onAdjust={openAdjust} filter={quotaFilter} setFilter={setQuotaFilter} onRefresh={reloadQuotas} loading={loading} />
            </TabsContent>
            <TabsContent value="requests">
              <RequestsTab
                requests={requests}
                pricing={pricing}
                onApprove={(r) => {
                  const p = pricing.find(x => x.agent_name === r.agent_name);
                  setApproveModal({ open: true, request: r, key_cost: String(p?.monthly_flat_usd ?? ''), service_charge: String(p?.service_charge_usd ?? ''), admin_note: '' });
                }}
                onAssignKey={(r) => openAssign(null, r)}
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
                  lockedLabel={(assignModal.replacingKey?.company_name) || (assignModal.prefillRequest?.company_name)}
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
            <div className="bg-violet-500/5 border border-violet-500/20 rounded-lg p-3 flex items-start gap-2">
              <Info className="w-4 h-4 text-violet-300 mt-0.5 shrink-0" />
              <p className="text-xs text-white/60">
                Free tokens for this agent are automatically applied from the{' '}
                <span className="text-violet-300 font-semibold">Pricing</span> tab configuration.
                To change the token limit, update it in Pricing first.
                {(() => {
                  const p = pricing.find(x => x.agent_name === assignForm.agent_name);
                  return p ? (
                    <span className="block mt-1 text-white/80 font-semibold">
                      Will grant: {formatTokens(p.free_tokens_on_purchase)} tokens
                    </span>
                  ) : null;
                })()}
              </p>
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
            <DialogDescription className="text-white/60">
              {approveModal.request?.company_name} — {approveModal.request?.agent_label} ({approveModal.request?.provider?.toUpperCase()})
              <br />Pre-filled from global pricing. Edit here to set a custom price for this company only — global pricing stays unchanged.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            {(() => {
              const p = pricing.find(x => x.agent_name === approveModal.request?.agent_name);
              const notSet = !p || (Number(p.monthly_flat_usd) === 0 && Number(p.service_charge_usd) === 0);
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
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-white/70 text-sm">Key Cost (USD)</Label>
                <Input
                  type="number" min="0" step="0.01" placeholder="0.00"
                  className="bg-[#1a1333] border-[#3a295a] text-white mt-1"
                  value={approveModal.key_cost}
                  onChange={(e) => setApproveModal({ ...approveModal, key_cost: e.target.value })}
                />
              </div>
              <div>
                <Label className="text-white/70 text-sm">Service Charge (USD)</Label>
                <Input
                  type="number" min="0" step="0.01" placeholder="0.00"
                  className="bg-[#1a1333] border-[#3a295a] text-white mt-1"
                  value={approveModal.service_charge}
                  onChange={(e) => setApproveModal({ ...approveModal, service_charge: e.target.value })}
                />
              </div>
            </div>
            {(Number(approveModal.key_cost) + Number(approveModal.service_charge)) > 0 && (
              <p className="text-sm text-emerald-300 font-semibold">
                Total due: ${(Number(approveModal.key_cost || 0) + Number(approveModal.service_charge || 0)).toFixed(2)}
              </p>
            )}
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
            <Button variant="outline" className="border-white/15 text-white/80" onClick={() => setApproveModal({ open: false, request: null, key_cost: '', service_charge: '', admin_note: '' })}>Cancel</Button>
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
