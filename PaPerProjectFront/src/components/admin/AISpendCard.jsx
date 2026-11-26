import React, { useEffect, useState } from 'react';
import { CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { DollarSign, Loader2 } from 'lucide-react';
import adminApiKeysService from '@/services/adminApiKeysService';

// The platform's AI bill in dollars (22 Nov 2026, core/ai_spend.py). On 19 Nov the OpenAI credit ran out with no
// warning; this shows the month against its budget, day by day, and who spent it. The site's team is also emailed
// at 50%, 80% and 100% of the budget, and on a day far above the usual.
const usd = (v) => (v == null ? '—' : `$${Number(v) < 0.01 && Number(v) > 0 ? '<0.01' : Number(v).toFixed(2)}`);

const Rows = ({ title, rows, label }) => (
  <div>
    <p className="text-[11px] uppercase tracking-wider text-pure-white/40 mb-2">{title}</p>
    {rows.length === 0 ? <p className="text-xs text-pure-white/40">Nothing yet this month.</p> : (
      <div className="space-y-2">
        {rows.map((r) => (
          <div key={r[label]} className="flex justify-between items-start gap-3 text-sm">
            <span className="text-pure-white/80 truncate" title={r[label]}>{r[label]}</span>
            <span className="shrink-0 text-right leading-tight">
              <span className="block text-pure-white tabular-nums">{usd(r.usd)}</span>
              <span className="block text-[11px] text-pure-white/45 tabular-nums">{r.calls.toLocaleString()} calls</span>
            </span>
          </div>
        ))}
      </div>
    )}
  </div>
);

export const AISpendCard = () => {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    adminApiKeysService.getAISpend()
      .then((res) => setData(res?.data || null))
      .catch((e) => setError(String(e.message || e)));
  }, []);

  const peak = data ? Math.max(0.0001, ...data.daily.map((d) => d.usd)) : 1;
  const pct = data?.budget_used_pct;
  const barColour = pct == null ? 'bg-violet-400' : pct >= 100 ? 'bg-red-400' : pct >= 80 ? 'bg-amber-400' : 'bg-emerald-400';

  return (
    <section className="ui-ink rounded-xl" data-testid="ai-spend-card">
      <CardHeader>
        <CardTitle className="text-pure-white flex items-center gap-2">
          <DollarSign className="w-5 h-5 text-[#b98aff]" /> AI spend on the platform's keys
        </CardTitle>
        <CardDescription className="text-pure-white/50">
          This month, worked out from every AI call's tokens at today's prices. Free tokens and managed keys are the
          platform's bill; companies' own keys are billed to them.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {error ? <p className="text-sm text-[#fca5a5]">{error}</p> : !data ? (
          <div className="flex justify-center py-6"><Loader2 className="w-6 h-6 animate-spin text-[#b98aff]" /></div>
        ) : (
          <div className="space-y-5">
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              <div className="col-span-2 md:col-span-3">
                <p className="text-[11px] uppercase tracking-wider text-pure-white/40">This month</p>
                <p className="font-heading font-semibold text-6xl leading-none mt-2 tabular-nums text-pure-white">{usd(data.month_usd)}</p>
                {data.budget_usd ? (
                  <p className="text-[11px] text-pure-white/50">{pct}% of the {usd(data.budget_usd)} budget</p>
                ) : <p className="text-[11px] text-pure-white/50">no budget set</p>}
              </div>
              <div>
                <p className="text-[11px] uppercase tracking-wider text-pure-white/40">Today</p>
                <p className="text-2xl font-bold text-pure-white">{usd(data.daily[data.daily.length - 1]?.usd)}</p>
              </div>
              <div>
                <p className="text-[11px] uppercase tracking-wider text-pure-white/40">Companies' own keys</p>
                <p className="text-2xl font-bold text-pure-white/70">{usd(data.own_keys_usd)}</p>
                <p className="text-[11px] text-pure-white/50">billed to them</p>
              </div>
              <div>
                <p className="text-[11px] uppercase tracking-wider text-pure-white/40">Not split</p>
                <p className="text-2xl font-bold text-pure-white/70">{usd(data.unsplit_usd)}</p>
                <p className="text-[11px] text-pure-white/50">calls before 22 Nov, counted as the platform's</p>
              </div>
            </div>
            {data.openai_bill ? (
              <p className="text-[11px] text-pure-white/60" data-testid="ai-spend-openai-bill">
                OpenAI's own bill this month: {usd(data.openai_bill.month_usd)} (today {usd(data.openai_bill.today_usd)}).
                It counts every use of the account, the site's and anything else on the same key; the warnings go by
                the higher figure.
              </p>
            ) : (
              <p className="text-[11px] text-[#fcd34d]" data-testid="ai-spend-no-bill">
                These figures are the site's own calls. Anything else using the same OpenAI key (a laptop's test runs)
                isn't counted. Add an OpenAI admin key (OPENAI_ADMIN_KEY on the server) to read OpenAI's own bill.
              </p>
            )}
            {data.groq_today && (data.groq_today.limit_calls > 0 || data.groq_today.limit_tokens > 0) && (
              <p className="text-[11px] text-pure-white/60" data-testid="ai-spend-groq">
                Groq today (AI SDR's free tier): {data.groq_today.calls.toLocaleString()} of{' '}
                {data.groq_today.limit_calls.toLocaleString()} requests, {data.groq_today.tokens.toLocaleString()} of{' '}
                {data.groq_today.limit_tokens.toLocaleString()} tokens. AI SDR waits when either runs out.
              </p>
            )}
            {data.budget_usd ? (
              <div className="h-2 rounded-full bg-pure-white/10 overflow-hidden">
                <div className={`h-full ${barColour}`} style={{ width: `${Math.min(100, pct || 0)}%` }} />
              </div>
            ) : null}
            <div>
              <p className="text-[11px] uppercase tracking-wider text-pure-white/40 mb-2">The last 14 days</p>
              <div className="flex items-end gap-1 h-24">
                {data.daily.map((d) => (
                  <div key={d.date} className="flex-1 flex flex-col items-center justify-end h-full"
                    title={`${d.date}: ${usd(d.usd)}`}>
                    <div className="w-full rounded-t ui-ink-chart" style={{ height: `${Math.max(2, (d.usd / peak) * 100)}%` }} />
                  </div>
                ))}
              </div>
              <div className="flex justify-between text-[10px] text-pure-white/40 mt-1">
                <span>{data.daily[0]?.date}</span><span>{data.daily[data.daily.length - 1]?.date}</span>
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
              <Rows title="By provider" rows={data.by_provider} label="provider" />
              <Rows title="Most by company" rows={data.by_company} label="company" />
              <Rows title="By agent" rows={data.by_agent} label="agent" />
            </div>
            {data.unpriced_models?.length > 0 && (
              <p className="text-[11px] text-[#fcd34d]">
                Not in the price table, counted at gpt-4.1's price: {data.unpriced_models.join(', ')}.
              </p>
            )}
          </div>
        )}
      </CardContent>
    </section>
  );
};

export default AISpendCard;
