import React from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Loader2, RefreshCw, Search } from 'lucide-react';
import { CARD_CLASS, ROW_CLASS, formatTokens } from './apiKeysShared';

export const QuotasTab = ({ quotas, onAdjust, filter, setFilter, onRefresh, loading, agentOptions = [] }) => (
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
          {agentOptions.map(a => <SelectItem key={a.value} value={a.value}>{a.label}</SelectItem>)}
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

export default QuotasTab;
