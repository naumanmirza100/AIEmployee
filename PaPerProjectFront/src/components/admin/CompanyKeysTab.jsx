import React from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Loader2, Key, Trash2, RefreshCw, Plus, Search } from 'lucide-react';
import { CARD_CLASS, ROW_CLASS, formatTokens } from './apiKeysShared';

export const KeysTab = ({ keys, onAssign, onRevoke, onAdjustQuota, filter, setFilter, onRefresh, loading, agentOptions = [] }) => (
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
          {agentOptions.map(a => <SelectItem key={a.value} value={a.value}>{a.label}</SelectItem>)}
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
// Starting values for an agent that has never been priced. They are only used
// to seed the form for an all-zero (unconfigured) row so the admin edits real
// numbers instead of a wall of 0.00 — every field stays editable, and 0 is a
// legal value to save here (unlike the key-assign form, where 0 tokens would
// hand out an unusable key).

export default KeysTab;
