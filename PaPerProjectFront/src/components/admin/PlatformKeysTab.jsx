import React, { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Loader2, Key, AlertTriangle, Trash2, Save, Globe } from 'lucide-react';
import { ROW_CLASS, ProviderLogo, PROVIDER_KEY_PREFIXES, PROVIDER_LABELS, PROVIDER_ACCENT } from './apiKeysShared';

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

// Each agent's default provider now travels with the agent itself
// (Agent.default_provider), so this no longer needs to mirror the backend by hand.

const AgentProviderReferenceTable = ({ agents = [] }) => (
  <div className="bg-[#0f0a20] border border-[#2d2342] rounded-lg overflow-hidden">
    <div className="px-4 py-2.5 border-b border-[#2d2342] flex items-center gap-2">
      <Key className="w-3.5 h-3.5 text-violet-300" />
      <span className="text-xs font-semibold text-white/70 uppercase tracking-wider">Agent → Provider Mapping (Default / Free Tokens)</span>
    </div>
    <div className="divide-y divide-[#2d2342]">
      {agents.map(row => (
        <div key={row.slug} className="flex items-center justify-between px-4 py-2 hover:bg-white/2 transition-colors">
          <div className="flex items-center gap-3">
            <div className="w-5 h-5 rounded flex items-center justify-center">
              <ProviderLogo provider={row.default_provider} size={16} />
            </div>
            <div>
              <p className="text-xs text-white font-medium">{row.name}</p>
              <p className="text-[10px] text-white/30 font-mono">{row.slug}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className={`text-[10px] px-2 py-0.5 rounded border font-medium ${PROVIDER_ACCENT[row.default_provider] || 'text-white/40 bg-white/5 border-white/10'}`}>
              {PROVIDER_LABELS[row.default_provider] || row.default_provider}
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

export const PlatformTab = ({ platformKeys, onSave, onRevoke, savingProvider, revokingProvider, agentOptions = [] }) => (
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
    <AgentProviderReferenceTable agents={agentOptions} />
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

export default PlatformTab;
