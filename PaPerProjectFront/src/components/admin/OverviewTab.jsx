import React from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Key, ShieldCheck, AlertTriangle, Gauge, Inbox, Building2, Globe } from 'lucide-react';
import { CARD_CLASS, ProviderLogo, formatTokens, StatCard } from './apiKeysShared';

export const OverviewTab = ({ stats }) => (
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

export default OverviewTab;
