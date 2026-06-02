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
  Send, Trash2, ChevronLeft, ChevronRight, ChevronDown, RefreshCw, DollarSign, Gauge,
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
  { value: 'recruitment_agent',     label: 'Recruitment Agent'     },
  { value: 'marketing_agent',       label: 'Marketing Agent'       },
  { value: 'project_manager_agent', label: 'Project Manager Agent' },
  { value: 'frontline_agent',       label: 'Frontline Agent'       },
  { value: 'operations_agent',      label: 'Operations Agent'      },
  { value: 'reply_draft_agent',     label: 'Reply Draft Agent'     },
  { value: 'hr_agent',              label: 'HR Support Agent'      },
  { value: 'ai_sdr_agent',          label: 'AI SDR Agent'          },
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
// Expected key prefixes per provider for frontend validation
const PROVIDER_KEY_PREFIXES = {
  openai:  { prefixes: ['sk-'], hint: 'OpenAI keys start with sk-' },
  groq:    { prefixes: ['gsk_'], hint: 'Groq keys start with gsk_' },
  claude:  { prefixes: ['sk-ant-'], hint: 'Anthropic keys start with sk-ant-' },
  gemini:  { prefixes: ['AIza'], hint: 'Gemini keys start with AIza' },
  grok:    { prefixes: ['xai-'], hint: 'xAI Grok keys start with xai-' },
};

const PlatformKeyRow = ({ row, onSave, onRevoke, saving, revoking }) => {
  const [apiKey, setApiKey] = useState('');

  const prefixInfo = PROVIDER_KEY_PREFIXES[row.provider];
  const validPrefix = !apiKey || !prefixInfo ||
    prefixInfo.prefixes.some(p => apiKey.startsWith(p));
  const prefixError = apiKey.length > 3 && !validPrefix
    ? `Wrong key format. ${prefixInfo.hint}.`
    : null;

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
        <div className="flex items-center gap-2">
          <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium border ${
            row.configured && row.status === 'active'
              ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
              : 'bg-gray-500/15 text-gray-400 border-gray-500/30'
          }`}>
            {row.configured && row.status === 'active' ? 'Active' : 'Not set'}
          </span>
          {row.configured && row.status === 'active' && (
            <button
              onClick={() => onRevoke(row.provider)}
              disabled={revoking}
              title="Remove this key"
              className="text-[10px] px-2 py-0.5 rounded-full border border-red-500/30 text-red-400/70 hover:bg-red-500/10 hover:text-red-300 transition-all disabled:opacity-50"
            >
              {revoking ? <Loader2 className="w-3 h-3 animate-spin inline" /> : <Trash2 className="w-3 h-3 inline" />}
            </button>
          )}
        </div>
      </div>
      <div className="flex items-end gap-2">
        <div className="flex-1">
          <div className='flex justify-start items-center gap-2'>
          <Label className="text-white/60 text-xs">
            {row.configured ? 'Replace key' : 'Paste new key'}
          </Label>
           {prefixError && (
            <p className="text-[10px] text-red-400 mt-1 flex items-center gap-1">
              <AlertTriangle className="w-3 h-3 inline" /> {prefixError}
            </p>
          )}
          </div>
          <Input
            type="password" autoComplete="off"
            placeholder={prefixInfo ? prefixInfo.prefixes[0] + '...' : 'sk-...'}
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            className={`bg-[#1a1333] border-[#3a295a] text-white mt-1 font-mono ${prefixError ? 'border-red-500/60' : ''}`}
          />
        </div>
        <Button
          className="bg-violet-600 hover:bg-violet-700 text-white"
          disabled={saving || apiKey.length < 10 || !!prefixError}
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

// Which provider each agent uses by default (mirrors AGENT_DEFAULT_PROVIDER in backend)
const AGENT_DEFAULT_PROVIDERS = [
  { agent: 'Recruitment Agent',      key: 'recruitment_agent',       provider: 'groq',   providerLabel: 'Groq (Llama)'    },
  { agent: 'Marketing Agent',        key: 'marketing_agent',         provider: 'groq',   providerLabel: 'Groq (Llama)'    },
  { agent: 'Reply Draft Agent',      key: 'reply_draft_agent',       provider: 'groq',   providerLabel: 'Groq (Llama)'    },
  { agent: 'Project Manager Agent',  key: 'project_manager_agent',   provider: 'groq',   providerLabel: 'Groq (Llama)'    },
  { agent: 'Operations Agent',       key: 'operations_agent',        provider: 'groq',   providerLabel: 'Groq (Llama)'    },
  { agent: 'Frontline Agent',        key: 'frontline_agent',         provider: 'openai', providerLabel: 'OpenAI'          },
  { agent: 'HR Support Agent',       key: 'hr_agent',                provider: 'groq',   providerLabel: 'Groq (Llama)'    },
  { agent: 'AI SDR Agent',           key: 'ai_sdr_agent',            provider: 'groq',   providerLabel: 'Groq (Llama)'    },
];

const PROVIDER_ACCENT = {
  openai:  'text-green-300 bg-green-500/10 border-green-500/20',
  groq:    'text-violet-300 bg-violet-500/10 border-violet-500/20',
  claude:  'text-orange-300 bg-orange-500/10 border-orange-500/20',
  gemini:  'text-blue-300 bg-blue-500/10 border-blue-500/20',
  grok:    'text-red-300 bg-red-500/10 border-red-500/20',
};

const AgentProviderReferenceTable = () => (
  <div className="bg-[#0f0a20] border border-[#2d2342] rounded-lg overflow-hidden">
    <div className="px-4 py-2.5 border-b border-[#2d2342] flex items-center gap-2">
      <Key className="w-3.5 h-3.5 text-violet-300" />
      <span className="text-xs font-semibold text-white/70 uppercase tracking-wider">Agent → Provider Mapping (Default / Free Tokens)</span>
    </div>
    <div className="divide-y divide-[#2d2342]">
      {AGENT_DEFAULT_PROVIDERS.map(row => (
        <div key={row.key} className="flex items-center justify-between px-4 py-2 hover:bg-white/2 transition-colors">
          <div className="flex items-center gap-3">
            <div className="w-5 h-5 rounded flex items-center justify-center">
              <ProviderLogo provider={row.provider} size={16} />
            </div>
            <div>
              <p className="text-xs text-white font-medium">{row.agent}</p>
              <p className="text-[10px] text-white/30 font-mono">{row.key}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className={`text-[10px] px-2 py-0.5 rounded border font-medium ${PROVIDER_ACCENT[row.provider] || 'text-white/40 bg-white/5 border-white/10'}`}>
              {row.providerLabel}
            </span>
            <span className="text-[10px] text-white/30">default</span>
          </div>
        </div>
      ))}
    </div>
    <div className="px-4 py-2 bg-[#0c0820] border-t border-[#2d2342]">
      <p className="text-[10px] text-white/30 leading-relaxed">
        <span className="text-white/50">Note:</span> Companies can override the default provider by adding a BYOK key with a different provider,
        or an admin can assign a managed key with any supported provider. The table above shows which platform key is consumed on the free-tokens path.
      </p>
    </div>
  </div>
);

const PlatformTab = ({ platformKeys, onSave, onRevoke, savingProvider, revokingProvider }) => (
  <div className="space-y-3">
    <div className="bg-gradient-to-r from-emerald-500/10 to-teal-500/10 border border-emerald-500/20 rounded-lg p-4 flex items-start gap-3">
      <Globe className="w-5 h-5 text-emerald-300 shrink-0 mt-0.5" />
      <div className="text-sm text-white/70">
        <p className="text-white font-semibold mb-1">Platform keys = the "free tokens" path</p>
        <p className="text-white/60 leading-relaxed">
          Set <span className="text-white font-semibold">one key per provider</span>. Every company uses these keys automatically
          until their per-agent quota (1M default) is exhausted. Keys are encrypted at rest — only the masked preview is shown.
          <span className="text-white/80 font-medium"> When a managed or BYOK key quota is exhausted, calls are hard-blocked — there is no automatic fallback to another pool.</span>
        </p>
      </div>
    </div>
    <AgentProviderReferenceTable />
    {platformKeys.map(row => (
      <PlatformKeyRow
        key={row.provider}
        row={row}
        onSave={onSave}
        onRevoke={onRevoke}
        saving={savingProvider === row.provider}
        revoking={revokingProvider === row.provider}
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
                  {k.status !== 'revoked' && (
                    <Button size="sm" variant="ghost" className="text-red-300 hover:text-red-200 hover:bg-red-500/10" onClick={() => onRevoke(k)}>
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  )}
                  {q && k.status !== 'revoked' && (
                    <Button size="sm" variant="outline" className="border-white/15 text-white/70 hover:bg-white/5 hover:text-white text-xs" onClick={() => onAdjustQuota(q, k)}>
                       Edit tokens
                    </Button>
                  )}
                  {k.status === 'revoked' ? (
                    <Button size="sm" className="bg-violet-600 hover:bg-violet-700 text-white" onClick={() => onAssign(k)}>
                      Re-assign
                    </Button>
                  ) : (
                    k.mode === 'managed' && (
                      <Button size="sm" className="pr-4 pl-4 bg-violet-600 hover:bg-violet-700 text-white" onClick={() => onAssign(k)}>
                        Replace
                      </Button>
                    )
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
    yearly_discount_pct: row.yearly_discount_pct ?? '0',
  });
  const dirty = useMemo(() =>
    String(draft.monthly_flat_usd) !== String(row.monthly_flat_usd) ||
    String(draft.service_charge_usd) !== String(row.service_charge_usd) ||
    Number(draft.free_tokens_on_purchase) !== Number(row.free_tokens_on_purchase) ||
    Number(draft.managed_key_tokens) !== Number(row.managed_key_tokens ?? 0) ||
    String(draft.yearly_discount_pct) !== String(row.yearly_discount_pct ?? '0'),
    [draft, row]
  );

  // Live price calculations
  const monthly = parseFloat(draft.monthly_flat_usd) || 0;
  const svc = parseFloat(draft.service_charge_usd) || 0;
  const discountPct = Math.min(100, Math.max(0, parseFloat(draft.yearly_discount_pct) || 0));
  const monthlyTotal = monthly + svc;
  const yearlyFull = monthlyTotal * 12;
  const yearlyTotal = yearlyFull * (1 - discountPct / 100);
  const yearlySaving = yearlyFull - yearlyTotal;

  return (
    <div className={`${ROW_CLASS} rounded-lg p-4`}>
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-white font-semibold">{row.agent_label}</h4>
        <span className="text-[10px] text-white/40 font-mono">{row.agent_name}</span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
        <div>
          <Label className="text-white/60 text-xs">
            Key Cost <span className="text-violet-300 font-semibold">/ month</span>
            <span className="text-white/30 ml-1">— pre-filled in Approve modal</span>
          </Label>
          <div className="relative mt-1">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-white/40 text-sm">$</span>
            <Input
              type="number" step="0.01"
              className="bg-[#1a1333] border-[#3a295a] text-white pl-6"
              value={draft.monthly_flat_usd}
              onChange={(e) => setDraft({ ...draft, monthly_flat_usd: e.target.value })}
            />
          </div>
        </div>
        <div>
          <Label className="text-white/60 text-xs">
            Service Charge <span className="text-violet-300 font-semibold">/ month</span>
            <span className="text-white/30 ml-1">— platform fee</span>
          </Label>
          <div className="relative mt-1">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-white/40 text-sm">$</span>
            <Input
              type="number" step="0.01"
              className="bg-[#1a1333] border-[#3a295a] text-white pl-6"
              value={draft.service_charge_usd}
              onChange={(e) => setDraft({ ...draft, service_charge_usd: e.target.value })}
            />
          </div>
        </div>
        <div>
          <Label className="text-white/60 text-xs">
            Yearly Discount <span className="text-white/30">— % off when company pays yearly (0 = no discount)</span>
          </Label>
          <div className="relative mt-1">
            <Input
              type="number" min="0" max="100" step="1"
              className="bg-[#1a1333] border-[#3a295a] text-white pr-7"
              value={draft.yearly_discount_pct}
              onChange={(e) => {
                const v = Math.min(100, Math.max(0, Number(e.target.value) || 0));
                setDraft({ ...draft, yearly_discount_pct: String(v) });
              }}
            />
            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-white/40 text-sm">%</span>
          </div>
          <p className="text-[10px] text-white/40 mt-1">
            0% = no discount · 20% = 20% off · 100% = free
          </p>
        </div>
        <div>
          <Label className="text-white/60 text-xs">
            Managed Key Tokens <span className="text-white/30">— per weekly reset</span>
          </Label>
          <Input
            type="number"
            className="bg-[#1a1333] border-[#3a295a] text-white mt-1"
            value={draft.managed_key_tokens}
            onChange={(e) => setDraft({ ...draft, managed_key_tokens: e.target.value })}
          />
          <p className="text-[10px] text-white/40 mt-1">{formatTokens(Number(draft.managed_key_tokens))} tokens / week</p>
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
      </div>

      {/* Live price calculator */}
      {monthlyTotal > 0 && (
        <div className="grid grid-cols-2 gap-2 mb-3 p-3 bg-violet-500/5 border border-violet-500/20 rounded-lg">
          <div>
            <p className="text-[10px] text-white/40 uppercase tracking-wider mb-1">Monthly plan</p>
            <p className="text-white font-bold">${monthlyTotal.toFixed(2)}<span className="text-white/40 font-normal text-[10px]"> /mo</span></p>
            <p className="text-[10px] text-white/40">(${monthly.toFixed(2)} key + ${svc.toFixed(2)} svc)</p>
          </div>
          <div>
            <p className="text-[10px] text-white/40 uppercase tracking-wider mb-1">
              Yearly plan {discountPct > 0 && <span className="text-emerald-400">({discountPct}% off)</span>}
            </p>
            <p className="text-white font-bold">${yearlyTotal.toFixed(2)}<span className="text-white/40 font-normal text-[10px]"> /yr</span></p>
            {yearlySaving > 0 && (
              <p className="text-[10px] text-emerald-400">saves ${yearlySaving.toFixed(2)} vs monthly</p>
            )}
            {discountPct === 0 && (
              <p className="text-[10px] text-white/30">same as monthly × 12</p>
            )}
          </div>
        </div>
      )}

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
                {q.managed_key_status !== 'revoked' && (
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-white/25 ml-2">Managed:</span>
                    <Button size="sm" variant="outline" className="border-violet-500/30 text-violet-300 hover:bg-violet-500/10 text-xs" onClick={() => onAdjust(q, 'set_managed')}>
                      Set tokens
                    </Button>
                    <Button size="sm" variant="outline" className="border-violet-500/30 text-violet-300 hover:bg-violet-500/10 text-xs" onClick={() => onAdjust(q, 'reset_managed')}>
                      Reset used
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

// Single timeline entry for one KeyRequest record (or a synthetic revocation node)
const TimelineEntry = ({ r, isLast, onApprove, onAssignKey, onReject, pricing }) => {
  const meta = REQUEST_STATUS_META[r.status] || REQUEST_STATUS_META.pending;
  const { Icon } = meta;
  const total = (r.key_cost_snapshot ?? 0) + (r.service_charge_snapshot ?? 0);
  const agentPricing = pricing?.find(p => p.agent_name === r.agent_name);
  const isActive = ['key_assigned', 'approved'].includes(r.status) && !r._synthetic;
  const isNegative = ['rejected', 'revoked'].includes(r.status);
  const isPending = ['pending', 'payment_pending', 'payment_received'].includes(r.status);
  // _ts is set on synthetic revocation nodes; otherwise use resolved_at or created_at
  const displayTime = r._ts || r.resolved_at || r.created_at;

  const dotColor = isActive
    ? 'bg-emerald-500 border-emerald-400 shadow-emerald-500/40'
    : isNegative
    ? 'bg-orange-500 border-orange-400 shadow-orange-500/40'
    : isPending
    ? 'bg-amber-500 border-amber-400 shadow-amber-500/40 animate-pulse'
    : 'bg-white/20 border-white/20';

  return (
    <div className="flex gap-3">
      {/* Dot + line */}
      <div className="flex flex-col items-center shrink-0">
        <div className={`w-3 h-3 rounded-full border-2 shadow-sm mt-1 ${dotColor}`} />
        {!isLast && <div className="w-px flex-1 bg-[#2d2342] mt-1 mb-0" />}
      </div>

      {/* Content */}
      <div className={`flex-1 pb-4 min-w-0 ${isLast ? '' : ''}`}>
        <div className="flex items-start justify-between gap-2 flex-wrap">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className={`flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full border font-medium ${meta.cls}`}>
                <Icon className="w-3 h-3" />{meta.label}
              </span>
              <span className="text-[10px] text-white/30 uppercase">{r.provider}</span>
              {isActive && <span className="text-[9px] text-emerald-400/70 font-medium">● ACTIVE</span>}
            </div>

            {r.note && <p className="text-xs text-white/50 mt-1 italic">User note: "{r.note}"</p>}
            {r.admin_note && <p className="text-xs text-violet-300 mt-1">Admin: "{r.admin_note}"</p>}

            {r.status === 'payment_pending' && total > 0 && (
              <p className="text-xs text-yellow-300 mt-1">
                Amount due: <span className="font-semibold">${total.toFixed(2)}</span>
                <span className="text-white/40 ml-1">(key ${(r.key_cost_snapshot ?? 0).toFixed(2)} + svc ${(r.service_charge_snapshot ?? 0).toFixed(2)})</span>
              </p>
            )}
            {r.status === 'payment_received' && r.amount_paid != null && (
              <p className="text-xs text-blue-300 mt-1">
                Paid: <span className="font-semibold">${r.amount_paid.toFixed(2)}</span>
                {r.paid_at && <span className="text-white/40 ml-1">• {new Date(r.paid_at).toLocaleString()}</span>}
              </p>
            )}

            <p className="text-[10px] text-white/25 mt-1">
              {r._synthetic
                ? <span className="italic text-orange-300/50">Key revoked</span>
                : r.requested_by
                  ? <><span className="text-white/40">{r.requested_by}</span> requested</>
                  : <span className="italic">Direct admin assignment</span>
              }
              {!r._synthetic && r.resolved_by && <> · resolved by <span className="text-white/40">{r.resolved_by}</span></>}
              {' · '}{new Date(displayTime).toLocaleString()}
            </p>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {!r._synthetic && r.status === 'pending' && (
              <>
                <Button size="sm" className="h-7 bg-emerald-600 hover:bg-emerald-700 text-white text-xs px-2" onClick={() => onApprove(r)}>
                  <CheckCircle2 className="w-3 h-3 mr-1" />Approve
                </Button>
                <Button size="sm" variant="outline" className="h-7 border-red-500/40 text-red-300 hover:bg-red-500/10 text-xs px-2" onClick={() => onReject(r)}>
                  <XCircle className="w-3 h-3 mr-1" />Reject
                </Button>
              </>
            )}
            {!r._synthetic && r.status === 'payment_pending' && (
              <span className="text-[10px] text-yellow-300/70 italic">Awaiting payment</span>
            )}
            {!r._synthetic && r.status === 'payment_received' && (
              <Button size="sm" className="h-7 bg-violet-600 hover:bg-violet-700 text-white text-xs px-2" onClick={() => onAssignKey(r)}>
                <Key className="w-3 h-3 mr-1" />Assign Key
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

// Expand a request list into timeline entries, splitting assigned-then-revoked
// records into two nodes: one "Key Assigned" (green) and one "Revoked" (orange).
function expandEntries(requests) {
  const entries = [];
  for (const r of requests) {
    if (r.was_assigned) {
      // First node: the original assignment (green)
      entries.push({ ...r, status: 'key_assigned', _ts: r.resolved_at });
      // Second node: the revocation (orange, synthetic — no action buttons)
      entries.push({
        ...r,
        _syntheticId: `${r.id}_revoked`,
        status: 'revoked',
        _ts: r.revoked_at,
        _synthetic: true,
      });
    } else {
      entries.push(r);
    }
  }
  return entries;
}

// Grouped card: one card per (company, agent) showing full timeline
const RequestGroupCard = ({ group, onApprove, onAssignKey, onReject, pricing }) => {
  const [expanded, setExpanded] = useState(group.hasAction);

  // Expand revoked-assignment records into two timeline nodes each
  const entries = React.useMemo(() => expandEntries(group.requests), [group.requests]);

  const latest = entries[entries.length - 1];
  const latestMeta = REQUEST_STATUS_META[latest.status] || REQUEST_STATUS_META.pending;
  const { Icon: LatestIcon } = latestMeta;
  const isCurrentlyActive = ['key_assigned', 'approved'].includes(latest.status) && !latest._synthetic;

  return (
    <div className={`${ROW_CLASS} rounded-xl overflow-hidden`}>
      {/* Header */}
      <button
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-white/[0.02] transition-colors"
        onClick={() => setExpanded(e => !e)}
      >
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-white font-semibold text-sm">{group.company_name}</span>
            <span className="text-xs text-white/40">{group.agent_label}</span>
            <span className={`flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full border font-medium ${latestMeta.cls}`}>
              <LatestIcon className="w-3 h-3" />{latestMeta.label}
            </span>
            {isCurrentlyActive && (
              <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 font-medium">Active key</span>
            )}
          </div>
          <p className="text-[10px] text-white/30 mt-0.5">
            {entries.length} event{entries.length > 1 ? 's' : ''} · Latest {new Date(latest._ts || latest.resolved_at || latest.created_at).toLocaleDateString()}
          </p>
        </div>
        <div className="shrink-0 text-white/30">
          {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        </div>
      </button>

      {/* Timeline */}
      {expanded && (
        <div className="px-4 pb-2 pt-1 border-t border-[#2d2342]">
          {entries.map((r, i) => (
            <TimelineEntry
              key={r._syntheticId || r.id}
              r={r}
              isLast={i === entries.length - 1}
              onApprove={onApprove}
              onAssignKey={onAssignKey}
              onReject={onReject}
              pricing={pricing}
            />
          ))}
        </div>
      )}
    </div>
  );
};

const RequestsTab = ({ requests, onApprove, onAssignKey, onReject, filter, setFilter, onRefresh, loading, pricing }) => {
  // Group by (company_id + agent_name), sorted oldest→newest within each group
  const groups = React.useMemo(() => {
    const map = {};
    requests.forEach(r => {
      const key = `${r.company_id}__${r.agent_name}`;
      if (!map[key]) map[key] = {
        key,
        company_id: r.company_id,
        company_name: r.company_name,
        agent_name: r.agent_name,
        agent_label: r.agent_label,
        requests: [],
        hasAction: false,
      };
      map[key].requests.push(r);
      if (['pending', 'payment_received'].includes(r.status)) map[key].hasAction = true;
    });
    // Sort each group oldest→newest so timeline reads top-to-bottom
    Object.values(map).forEach(g => g.requests.sort((a, b) => new Date(a.created_at) - new Date(b.created_at)));
    // Sort groups: action-needed first, then by latest event desc
    return Object.values(map).sort((a, b) => {
      if (a.hasAction !== b.hasAction) return a.hasAction ? -1 : 1;
      const aLatest = new Date(a.requests[a.requests.length - 1].created_at);
      const bLatest = new Date(b.requests[b.requests.length - 1].created_at);
      return bLatest - aLatest;
    });
  }, [requests]);

  return (
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
        {groups.length > 0 && (
          <span className="text-xs text-white/30 ml-1">{groups.length} company{groups.length > 1 ? '/agent pairs' : '/agent pair'} · {requests.length} total events</span>
        )}
      </div>
      {groups.length === 0 ? (
        <Card className={CARD_CLASS}>
          <CardContent className="p-12 text-center text-white/50">
            <Inbox className="w-10 h-10 text-white/20 mx-auto mb-2" /> No requests.
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {groups.map(g => (
            <RequestGroupCard
              key={g.key}
              group={g}
              onApprove={onApprove}
              onAssignKey={onAssignKey}
              onReject={onReject}
              pricing={pricing}
            />
          ))}
        </div>
      )}
    </div>
  );
};

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
  const [revokingProvider, setRevokingProvider] = useState(null);

  const [keyFilter, setKeyFilter] = useState({ mode: 'managed' });
  const [quotaFilter, setQuotaFilter] = useState({});
  const [requestFilter, setRequestFilter] = useState({});

  const [assignModal, setAssignModal] = useState({ open: false, replacingKey: null, prefillRequest: null });
  const [assignForm, setAssignForm] = useState({ company_id: '', agent_name: 'frontline_agent', provider: 'openai', api_key: '', reset_tokens: true, managed_tokens: '', renewal_period: 'none', duration_months: '' });
  const [approveModal, setApproveModal] = useState({ open: false, request: null, key_cost: '', service_charge: '', admin_note: '' });
  const [rejectModal, setRejectModal] = useState({ open: false, request: null, note: '' });
  const [adjustModal, setAdjustModal] = useState({ open: false, quota: null, action: '', value: '' });
  const [confirmDialog, setConfirmDialog] = useState({ open: false, title: '', description: '', onConfirm: null });

  const [submitting, setSubmitting] = useState(false);
  const [savingAgent, setSavingAgent] = useState(null);

  const loadAll = async ({ silent = false } = {}) => {
    if (!silent) setLoading(true);
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
      const r = await adminApiKeysService.listRequests(requestFilter);
      setRequests(r.requests || []);
    } catch (e) { toast({ title: 'Failed', description: String(e.message || e), variant: 'destructive' }); }
  };

  useEffect(() => { const t = setTimeout(reloadKeys, 300); return () => clearTimeout(t); /* eslint-disable-next-line */ }, [keyFilter]);
  useEffect(() => { const t = setTimeout(reloadQuotas, 300); return () => clearTimeout(t); /* eslint-disable-next-line */ }, [quotaFilter]);
  useEffect(() => { const t = setTimeout(reloadRequests, 300); return () => clearTimeout(t); /* eslint-disable-next-line */ }, [requestFilter]);

  const openAssign = (existingOrRequest, prefill = null) => {
    if (prefill) {
      const duration = prefill.preferred_duration || 'monthly';
      const p = pricing.find(x => x.agent_name === prefill.agent_name);
      const defaultTokens = p?.managed_key_tokens ? String(p.managed_key_tokens) : '';
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
          : '',
        renewal_period: existingOrRequest.renewal_period || 'none',
        duration_months: '',
      });
      setAssignModal({ open: true, replacingKey: existingOrRequest, prefillRequest: null });
    } else {
      setAssignForm({ company_id: '', agent_name: 'frontline_agent', provider: 'openai', api_key: '', reset_tokens: true, managed_tokens: '', renewal_period: 'none', duration_months: '' });
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
        reset_tokens: assignForm.reset_tokens,
        renewal_period: assignForm.renewal_period,
      };
      if (assignForm.managed_tokens.trim() !== '') payload.managed_tokens = assignForm.managed_tokens;
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
                : <PlatformTab platformKeys={platformKeys} onSave={savePlatformKey} onRevoke={handleRevokePlatformKey} savingProvider={savingProvider} revokingProvider={revokingProvider} />}
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
                  const duration = r.preferred_duration || 'monthly';
                  const discountPct = parseFloat(p?.yearly_discount_pct || 0);
                  const monthlyKey = parseFloat(p?.monthly_flat_usd || 0);
                  const monthlySvc = parseFloat(p?.service_charge_usd || 0);
                  const keyCost = duration === 'yearly'
                    ? (monthlyKey * 12 * (1 - discountPct / 100)).toFixed(2)
                    : String(p?.monthly_flat_usd ?? '');
                  const svcCharge = duration === 'yearly'
                    ? (monthlySvc * 12 * (1 - discountPct / 100)).toFixed(2)
                    : String(p?.service_charge_usd ?? '');
                  setApproveModal({ open: true, request: r, key_cost: keyCost, service_charge: svcCharge, admin_note: '' });
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
        <DialogContent className="bg-[#120d22] border border-[#2d2342] text-white sm:max-w-3xl w-full">
          <DialogHeader className="pb-2 border-b border-white/8">
            <DialogTitle className="flex items-center gap-2">
              <Key className="w-5 h-5 text-violet-400" />
              {assignModal.replacingKey ? 'Replace Managed Key' : assignModal.prefillRequest ? 'Approve & Assign Key' : 'Assign Managed Key'}
            </DialogTitle>
            <DialogDescription className="text-white/50 text-xs">
              Encrypted on save — only a masked preview is visible afterward.
            </DialogDescription>
          </DialogHeader>

          <div className="py-3 space-y-4">

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
                      {AGENT_OPTIONS.map(a => <SelectItem key={a.value} value={a.value}>{a.label}</SelectItem>)}
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
                        ? <span className="text-emerald-400">Every 7 days</span>
                        : <span className="text-white/40">No reset</span>
                      }
                    </p>
                    <p className="text-[10px] text-white/40 mt-0.5">
                      {rk.tokens_per_period > 0 ? `${formatTokens(rk.tokens_per_period)} / week` : '—'}
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
            {/* {assignModal.prefillRequest ? (
              <div className="grid grid-cols-3 gap-4 p-4 bg-[#1a1333] border border-violet-500/30 rounded-xl">
                <div className="col-span-3 flex items-center gap-2 mb-1">
                  <div className="w-1.5 h-1.5 rounded-full bg-violet-400" />
                  <p className="text-[11px] text-violet-300 uppercase tracking-widest font-semibold">Requested by company</p>
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
                    {assignForm.renewal_period === 'none' ? 'No reset' : 'Every 7 days'}
                  </p>
                  <p className="text-[10px] text-white/40 mt-0.5">
                    {assignForm.renewal_period === 'none' ? 'One-time tokens only' : 'Automatic weekly reset'}
                  </p>
                </div>
                <div className="bg-[#120d22] rounded-lg p-3 border border-[#2d2342]">
                  <p className="text-[10px] text-white/40 uppercase tracking-wider mb-1">Key Valid For</p>
                  <p className="text-sm text-violet-300 font-semibold">
                    {assignForm.duration_months ? `${assignForm.duration_months} month${parseInt(assignForm.duration_months) !== 1 ? 's' : ''}` : 'Auto'}
                  </p>
                  <p className="text-[10px] text-white/40 mt-0.5">Set by company request</p>
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-x-6">
                <div>
                  <Label className="text-white/60 text-xs uppercase tracking-wider">Billing Plan — Key Expiry</Label>
                  <Select value={assignForm.renewal_period} onValueChange={(v) => setAssignForm({ ...assignForm, renewal_period: v })}>
                    <SelectTrigger className="bg-[#1a1333] border-[#3a295a] text-white mt-1"><SelectValue /></SelectTrigger>
                    <SelectContent className="bg-[#1a1333] border-[#3a295a] text-white">
                      <SelectItem value="none">One-time — key never expires</SelectItem>
                      <SelectItem value="monthly">Monthly — key expires after 1 month</SelectItem>
                      <SelectItem value="yearly">Yearly — key expires after 1 year</SelectItem>
                    </SelectContent>
                  </Select>
                  <p className="text-[10px] text-emerald-400/70 mt-1">
                    {assignForm.renewal_period === 'none' ? 'Tokens are one-time — no weekly reset.' : '✓ Tokens reset automatically every 7 days.'}
                  </p>
                </div>
                <div>
                  <Label className="text-white/60 text-xs uppercase tracking-wider">Key Valid For (months)</Label>
                  <Input
                    type="number" min="1"
                    placeholder={assignForm.renewal_period === 'yearly' ? '12' : assignForm.renewal_period === 'monthly' ? '1' : '—'}
                    className="bg-[#1a1333] border-[#3a295a] text-white mt-1"
                    value={assignForm.duration_months}
                    onChange={(e) => setAssignForm((f) => ({ ...f, duration_months: e.target.value }))}
                  />
                  <p className="text-[10px] text-white/40 mt-1">Leave blank to auto-set from billing plan</p>
                  {assignForm.duration_months && !isNaN(parseInt(assignForm.duration_months)) && (
                    <p className="text-[10px] text-amber-400/80 mt-1">
                      ⚠ Key expires after {assignForm.duration_months} month{parseInt(assignForm.duration_months) !== 1 ? 's' : ''} — company must renew
                    </p>
                  )}
                </div>
              </div>
            )} */}
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
            {/* Duration badge — what company requested */}
            {approveModal.request?.preferred_duration && (
              <div className="flex items-center gap-2 p-2.5 bg-violet-500/10 border border-violet-500/20 rounded-lg">
                <Clock className="w-4 h-4 text-violet-300 shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-white/70">
                    Company requested a <span className="text-violet-300 font-semibold capitalize">{approveModal.request.preferred_duration}</span> key.
                    Price has been auto-calculated from global pricing below.
                  </p>
                </div>
              </div>
            )}
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
                <Label className="text-white/70 text-sm">
                  Key Cost (USD)
                  <span className="text-white/30 font-normal ml-1 text-[10px]">
                    {approveModal.request?.preferred_duration === 'yearly' ? '— yearly total' : '— monthly'}
                  </span>
                </Label>
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
                <Label className="text-white/70 text-sm">
                  Service Charge (USD)
                  <span className="text-white/30 font-normal ml-1 text-[10px]">
                    {approveModal.request?.preferred_duration === 'yearly' ? '— yearly total' : '— monthly'}
                  </span>
                </Label>
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
            </div>
            {(Number(approveModal.key_cost) + Number(approveModal.service_charge)) > 0 && (
              <div className="flex items-center justify-between px-3 py-2 bg-emerald-500/8 border border-emerald-500/20 rounded-lg">
                <span className="text-sm text-white/70">Total due</span>
                <span className="text-emerald-300 font-bold text-base">
                  ${(Number(approveModal.key_cost || 0) + Number(approveModal.service_charge || 0)).toFixed(2)}
                  <span className="text-white/30 text-[10px] font-normal ml-1">
                    {approveModal.request?.preferred_duration === 'yearly' ? '/year' : '/month'}
                  </span>
                </span>
              </div>
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
