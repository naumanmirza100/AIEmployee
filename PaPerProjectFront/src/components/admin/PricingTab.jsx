import React, { useState, useMemo } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Loader2, Key, Save, Info } from 'lucide-react';
import { ROW_CLASS, formatTokens } from './apiKeysShared';

const PRICING_SEED = {
  monthly_flat_usd: '10.00',
  service_charge_usd: '4.00',
  managed_key_tokens: 50000,
};

const PricingRow = ({ row, onSave, saving }) => {
  // "Unconfigured" = never priced: cost, service charge and token grant all 0.
  const isUnconfigured =
    Number(row.monthly_flat_usd) === 0 &&
    Number(row.service_charge_usd) === 0 &&
    Number(row.managed_key_tokens ?? 0) === 0;
  const [draft, setDraft] = useState({
    monthly_flat_usd: isUnconfigured ? PRICING_SEED.monthly_flat_usd : row.monthly_flat_usd,
    service_charge_usd: isUnconfigured ? PRICING_SEED.service_charge_usd : row.service_charge_usd,
    free_tokens_on_purchase: row.free_tokens_on_purchase,
    managed_key_tokens: isUnconfigured ? PRICING_SEED.managed_key_tokens : (row.managed_key_tokens ?? 0),
    yearly_discount_pct: row.yearly_discount_pct ?? '0',
    monthly_discount_pct: row.monthly_discount_pct ?? '0',
  });
  const dirty = useMemo(() =>
    String(draft.monthly_flat_usd) !== String(row.monthly_flat_usd) ||
    String(draft.service_charge_usd) !== String(row.service_charge_usd) ||
    Number(draft.free_tokens_on_purchase) !== Number(row.free_tokens_on_purchase) ||
    Number(draft.managed_key_tokens) !== Number(row.managed_key_tokens ?? 0) ||
    String(draft.yearly_discount_pct) !== String(row.yearly_discount_pct ?? '0') ||
    String(draft.monthly_discount_pct) !== String(row.monthly_discount_pct ?? '0'),
    [draft, row]
  );

  // Live price calculations
  const monthly = parseFloat(draft.monthly_flat_usd) || 0;
  const svc = parseFloat(draft.service_charge_usd) || 0;
  const monthlyDiscountPct = Math.min(100, Math.max(0, parseFloat(draft.monthly_discount_pct) || 0));
  const monthlyTotal = monthly + svc;
  const monthlyDiscounted = monthlyTotal * (1 - monthlyDiscountPct / 100);
  const monthlySaving = monthlyTotal - monthlyDiscounted;

  return (
    <div className={`${ROW_CLASS} rounded-lg p-4`}>
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-white font-semibold">
          {row.agent_label}
          {isUnconfigured && (
            <span
              title="This agent has no pricing yet. Suggested starting values are filled in below — adjust them and click Save. Nothing is stored until you save."
              className="ml-2 align-middle text-[10px] font-medium uppercase tracking-wide px-1.5 py-0.5 rounded-full bg-amber-500/15 text-amber-300 border border-amber-500/30"
            >
              Not saved — suggested
            </span>
          )}
        </h4>
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
            Monthly Discount <span className="text-white/30">— % off the monthly price (0 = no discount)</span>
          </Label>
          <div className="relative mt-1">
            <Input
              type="number" min="0" max="100" step="1"
              className="bg-[#1a1333] border-[#3a295a] text-white pr-7"
              value={draft.monthly_discount_pct}
              onChange={(e) => {
                const v = Math.min(100, Math.max(0, Number(e.target.value) || 0));
                setDraft({ ...draft, monthly_discount_pct: String(v) });
              }}
            />
            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-white/40 text-sm">%</span>
          </div>
          <p className="text-[10px] text-white/40 mt-1">0% = no discount · 20% = 20% off monthly price</p>
        </div>
        {/* Yearly discount hidden — yearly plan not offered
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
        */}
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
      {/* Live price calculator */}
      {monthlyTotal > 0 && (
        <div className="grid grid-cols-2 gap-2 mb-3 p-3 bg-violet-500/5 border border-violet-500/20 rounded-lg">
          <div>
            <p className="text-[10px] text-white/40 uppercase tracking-wider mb-1">Full price</p>
            <p className="text-white/50 font-bold line-through text-sm">${monthlyTotal.toFixed(2)}<span className="text-white/30 font-normal text-[10px]"> /mo</span></p>
            <p className="text-[10px] text-white/30">(${monthly.toFixed(2)} key + ${svc.toFixed(2)} svc)</p>
          </div>
          <div>
            <p className="text-[10px] text-white/40 uppercase tracking-wider mb-1">
              After discount {monthlyDiscountPct > 0 && <span className="text-emerald-400">({monthlyDiscountPct}% off)</span>}
            </p>
            <p className="text-white font-bold">${monthlyDiscounted.toFixed(2)}<span className="text-white/40 font-normal text-[10px]"> /mo</span></p>
            {monthlySaving > 0 && <p className="text-[10px] text-emerald-400">saves ${monthlySaving.toFixed(2)}</p>}
            {monthlyDiscountPct === 0 && <p className="text-[10px] text-white/30">no discount set</p>}
          </div>
        </div>
      )}
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

export const PricingTab = ({ pricing, onSave, savingAgent }) => (
  <div className="space-y-3">
    <div className="bg-gradient-to-r from-violet-500/10 to-fuchsia-500/10 border border-violet-500/20 rounded-lg p-3 flex items-start gap-2">
      <Info className="w-4 h-4 text-violet-300 mt-0.5 shrink-0" />
      <p className="text-xs text-white/70 leading-relaxed">
        <span className="text-white font-semibold">Key Cost</span> and <span className="text-white font-semibold">Service Charge</span> are pre-filled in the Approve Request modal — admin can still override them per company.{' '}
        <span className="text-white font-semibold">Free Tokens</span> are automatically granted when a managed key is assigned.{' '}
        Editing a price inside Approve or Edit Request affects only that company, unless{' '}
        <span className="text-violet-300 font-semibold">“Also save as global pricing”</span> is ticked there — that writes back to this tab.
        Agents with no pricing yet show suggested starting values; 0 is allowed here.
      </p>
    </div>
    {pricing.map(row => <PricingRow key={row.agent_name} row={row} onSave={onSave} saving={savingAgent === row.agent_name} />)}
  </div>
);

// -------------------- Quotas Tab --------------------

export default PricingTab;
