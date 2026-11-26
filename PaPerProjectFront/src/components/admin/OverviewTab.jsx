import React from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Key, ShieldCheck, AlertTriangle, Gauge, Inbox, Building2, Globe, ChevronRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import { CARD_CLASS, ProviderLogo, formatTokens, StatCard } from './apiKeysShared';
import AISpendCard from './AISpendCard';

// What waits on the super admin, most urgent first (UI refresh, 26 Nov 2026), from the overview's own counts.
const NeedsYouNow = ({ stats }) => {
  const hour = new Date().getHours();
  const greeting = hour < 12 ? 'Good morning.' : hour < 18 ? 'Good afternoon.' : 'Good evening.';
  const exhausted = (stats.exhausted_quotas || 0) + (stats.exhausted_managed_quotas || 0);
  const rows = [
    { key: 'requests', n: stats.pending_requests || 0, title: 'Agent and token requests', sub: 'Companies waiting for your decision',
      act: 'Decide', to: '/admin/api-keys?tab=requests', dot: 'bg-red-500' },
    { key: 'quotas', n: exhausted, title: 'Used-up quotas',
      sub: `${stats.exhausted_quotas ?? 0} free · ${stats.exhausted_managed_quotas ?? 0} managed`, act: 'Top up', to: '/admin/api-keys?tab=quotas', dot: 'bg-orange-400' },
    { key: 'platform', n: stats.platform_keys_configured ?? 0, title: 'Platform keys set',
      sub: stats.platform_keys_configured > 0 ? 'The agents can run on the platform\'s keys' : 'No platform key: free tokens can\'t be used',
      act: stats.platform_keys_configured > 0 ? 'All good' : 'Add a key', to: '/admin/api-keys?tab=platform',
      dot: stats.platform_keys_configured > 0 ? 'bg-emerald-500' : 'bg-red-500', ok: stats.platform_keys_configured > 0 },
  ];
  const waiting = rows.filter((r) => !r.ok && r.n > 0);
  return (
    <Card className="h-full flex flex-col">
      <CardContent className="p-6 sm:p-8 flex-1 flex flex-col">
        <p className="inline-flex items-center gap-2 text-sm text-muted-foreground">
          <span className="h-2 w-2 rounded-full bg-emerald-500 shadow-[0_0_0_3px_rgba(16,185,129,0.18)]" />
          {new Date().toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })}
        </p>
        <h2 className="font-heading font-semibold tracking-tight text-5xl leading-none mt-5 text-foreground">{greeting}</h2>
        <p className="mt-4 text-base text-foreground/80">
          {waiting.length
            ? <>Waiting for you: <b className="text-foreground">{waiting.map((r) => `${r.n} ${r.title.toLowerCase()}`).join(' and ')}</b>.</>
            : 'Nothing is waiting for you.'}
        </p>
        <div className="h-px bg-border my-5" />
        <div className="divide-y divide-border">
          {rows.map((r) => (
            <div key={r.key} className="py-1">
            <Link to={r.to} className="flex items-center gap-4 py-2.5 px-2 -mx-2 rounded-xl hover:bg-muted/40 transition-colors">
              <span className={`h-2 w-2 rounded-full shrink-0 ${r.n > 0 || !r.ok ? r.dot : 'bg-muted-foreground/40'}`} />
              <span className="flex-1 min-w-0">
                <span className="block text-[15px] font-semibold text-foreground">{r.title}</span>
                <span className="block text-xs text-muted-foreground mt-0.5 truncate">{r.sub}</span>
              </span>
              <span className="text-right">
                <span className="block font-heading font-semibold text-2xl leading-none text-foreground tabular-nums">{r.n}</span>
                <span className={`block text-[11px] font-semibold mt-1 ${r.n > 0 && !r.ok ? 'text-red-600 dark:text-red-400' : 'text-muted-foreground'}`}>{r.act}</span>
              </span>
              <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />
            </Link>
            </div>
          ))}
        </div>
        <div className="flex-1 min-h-6" />
        <p className="text-[11px] uppercase tracking-wider text-muted-foreground mb-2.5">Shortcuts</p>
        <div className="flex flex-wrap gap-2">
          {[['Pricing', '/admin/api-keys?tab=pricing'], ['Per-company keys', '/admin/api-keys?tab=keys'],
            ['Reset logs', '/admin/api-keys?tab=reset-logs'], ['Backups', '/admin/backups']].map(([label, to]) => (
            <Link key={to} to={to} className="rounded-full border border-border/70 bg-card/70 px-3.5 py-1.5 text-xs font-medium text-foreground hover:border-primary/40 hover:text-primary transition-colors">
              {label}
            </Link>
          ))}
        </div>
      </CardContent>
    </Card>
  );
};

export const OverviewTab = ({ stats }) => (
  <div className="space-y-6">
    {/* What waits on you, beside the platform's AI bill in dollars: the credit running out stops every agent. */}
    <div className="grid grid-cols-1 xl:grid-cols-5 gap-6 items-stretch">
      <div className="xl:col-span-2"><NeedsYouNow stats={stats} /></div>
      <div className="xl:col-span-3"><AISpendCard /></div>
    </div>
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
            <div className="p-4 bg-[var(--panel-1)] border border-[var(--line-3)] rounded-lg">
              <p className="text-xs text-white/40 uppercase mb-1">Included</p>
              <p className="text-xl font-bold text-white">{formatTokens(stats.total_included_tokens)}</p>
            </div>
            <div className="p-4 bg-[var(--panel-1)] border border-[var(--line-3)] rounded-lg">
              <p className="text-xs text-white/40 uppercase mb-1">Used</p>
              <p className="text-xl font-bold text-violet-300">{formatTokens(stats.total_used_tokens)}</p>
            </div>
          </div>
        </div>
        {/* Managed key tokens */}
        <div>
          <p className="text-xs text-white/40 uppercase tracking-wider mb-2">Managed Key Tokens</p>
          <div className="grid grid-cols-2 gap-3">
            <div className="p-4 bg-[var(--panel-1)] border border-[var(--line-3)] rounded-lg">
              <p className="text-xs text-white/40 uppercase mb-1">Included</p>
              <p className="text-xl font-bold text-white">{formatTokens(stats.total_managed_included_tokens)}</p>
            </div>
            <div className="p-4 bg-[var(--panel-1)] border border-[var(--line-3)] rounded-lg">
              <p className="text-xs text-white/40 uppercase mb-1">Used</p>
              <p className="text-xl font-bold text-emerald-300">{formatTokens(stats.total_managed_used_tokens)}</p>
            </div>
          </div>
        </div>
        {/* BYOK info */}
        <div className="p-4 bg-[var(--panel-1)] border border-[var(--line-3)] rounded-lg">
          <p className="text-xs text-white/40 uppercase mb-1">BYOK (tracked, info only)</p>
          <p className="text-xl font-bold text-blue-300">{formatTokens(stats.total_byok_info_tokens)}</p>
        </div>
        {/* Per-provider breakdown */}
        {stats.provider_totals && Object.keys(stats.provider_totals).length > 0 && (
          <div>
            <p className="text-xs text-white/40 uppercase mb-2">By Provider</p>
            <div className="flex flex-wrap gap-2">
              {Object.entries(stats.provider_totals).map(([provider, tokens]) => (
                <div key={provider} className="p-3 bg-[var(--panel-1)] border border-[var(--line-3)] rounded-lg text-center hover:border-violet-500/30 transition-colors min-w-[110px]">
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

export default OverviewTab;
