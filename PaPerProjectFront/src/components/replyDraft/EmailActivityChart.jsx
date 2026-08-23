import React, { useState, useEffect } from 'react';
import { BarChart3, Loader2 } from 'lucide-react';
import { getReplyAnalytics } from '@/services/replyDraftService';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Filler,
  Legend,
} from 'chart.js';
import { Line } from 'react-chartjs-2';

// Safe to call more than once — Chart.js dedupes registrations, so the fact
// that CampaignDetail also registers these won't cause problems.
ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Filler, Legend);

// Window is not user-switchable: the chart can only ever plot what the
// account actually synced, so it follows the account's configured window
// (passed in as `days`) instead of offering ranges that would render flat.
const DEFAULT_WINDOW_DAYS = 90;

// Received-vs-sent volume chart for the attached Reply Draft account.
// `active` gates the fetch so a hidden instance doesn't call the API.
// `days`  is the account's configured sync window — changing it refetches.
// `refreshKey` lets the parent force a refetch when the underlying mail
//   changed but `days` didn't: editing the per-30-day email cap prunes
//   stored rows, so the same window can hold a different number of emails
//   and a stale chart would keep drawing the old counts.
export const EmailActivityChart = ({ active = true, variant = 'modal', days, refreshKey }) => {
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(false);
  const windowDays = Number(days) || DEFAULT_WINDOW_DAYS;

  useEffect(() => {
    if (!active) return;
    setLoading(true);
    let cancelled = false;
    getReplyAnalytics({ days: windowDays })
      .then((res) => { if (!cancelled) setAnalytics(res?.status === 'success' ? res.data : null); })
      .catch(() => { if (!cancelled) setAnalytics(null); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [active, windowDays, refreshKey]);

  const buckets = analytics?.buckets || [];
  const granularity = analytics?.granularity || 'day';  // 'day' | 'week'
  const isDash = variant === 'dashboard';

  // Two-line chart: incoming (cyan) vs sent (emerald). Daily buckets for
  // 30d, weekly buckets above that. Each bucket carries `received` and
  // `sent` keys from the analytics endpoint; older payloads with only
  // `count` fall back to the combined value on the received line.
  const chartData = {
    labels: buckets.map((b) => b.date),
    datasets: [
      {
        label: 'Received',
        data: buckets.map((b) => (b.received != null ? b.received : (b.count || 0))),
        borderColor: '#22d3ee',
        backgroundColor: 'rgba(34, 211, 238, 0.15)',
        fill: true,
        tension: 0.35,
        pointRadius: granularity === 'week' ? 3 : 2.5,
        pointHoverRadius: 5,
        borderWidth: 2,
      },
      {
        label: 'Sent',
        data: buckets.map((b) => b.sent || 0),
        borderColor: '#34d399',
        backgroundColor: 'rgba(52, 211, 153, 0.12)',
        fill: true,
        tension: 0.35,
        pointRadius: granularity === 'week' ? 3 : 2.5,
        pointHoverRadius: 5,
        borderWidth: 2,
      },
    ],
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { intersect: false, mode: 'index' },
    plugins: {
      legend: {
        display: true,
        position: 'top',
        align: 'end',
        labels: {
          color: 'rgba(200,200,200,0.85)',
          font: { size: 11 },
          boxWidth: 10,
          boxHeight: 10,
          usePointStyle: true,
          pointStyle: 'circle',
        },
      },
      tooltip: {
        callbacks: {
          title: (items) => {
            const raw = items[0]?.label || '';
            return granularity === 'week' ? `Week of ${raw}` : raw;
          },
          label: (ctx) => ` ${ctx.dataset.label}: ${ctx.parsed.y} email${ctx.parsed.y === 1 ? '' : 's'}`,
        },
      },
    },
    scales: {
      x: {
        grid: { display: false },
        ticks: {
          autoSkip: true,
          maxTicksLimit: granularity === 'week' ? Math.min(buckets.length, 10) : 8,
          color: 'rgba(120,120,120,0.8)',
          font: { size: 10 },
          callback: function (value) {
            const label = this.getLabelForValue(value);
            return typeof label === 'string' ? label.slice(5) : label;
          },
        },
      },
      y: {
        beginAtZero: true,
        ticks: {
          precision: 0,
          color: 'rgba(120,120,120,0.8)',
          font: { size: 10 },
        },
        grid: { color: 'rgba(120,120,120,0.12)' },
      },
    },
  };

  // The dashboard sits on the dark agent shell, so it gets the glass-card
  // treatment. The modal keeps the theme-token border it always had.
  const wrapCls = isDash
    ? 'rounded-2xl bg-black/40 border border-white/10 backdrop-blur-sm p-4 space-y-3'
    : 'rounded-lg border p-4 space-y-3';
  const titleCls = isDash ? 'text-sm font-semibold text-white' : 'text-sm font-semibold';
  const iconCls = isDash ? 'h-4 w-4 text-cyan-300' : 'h-4 w-4 text-primary';
  const mutedCls = isDash ? 'text-xs text-gray-400' : 'text-xs text-muted-foreground';

  return (
    <section className={wrapCls}>
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className={`flex items-center gap-2 ${titleCls}`}>
          <BarChart3 className={iconCls} />
          Email activity
        </div>
        <span className={`text-xs ${isDash ? 'text-gray-400' : 'text-muted-foreground'}`}>
          Last {windowDays} days
        </span>
      </div>

      {loading ? (
        <div className="flex justify-center py-8">
          <Loader2 className={`h-5 w-5 animate-spin ${isDash ? 'text-gray-400' : 'text-muted-foreground'}`} />
        </div>
      ) : buckets.length === 0 ? (
        <div className={`${mutedCls} py-6 text-center`}>No data.</div>
      ) : (
        <>
          <div className={mutedCls}>
            <span className="font-semibold text-cyan-300">{analytics?.received_total ?? 0}</span>
            {' '}received ·{' '}
            <span className="font-semibold text-emerald-300">{analytics?.sent_total ?? 0}</span>
            {' '}sent in the last {windowDays} days
            {granularity === 'week' && (
              <span className="ml-1 opacity-75">· grouped by week</span>
            )}
          </div>
          <div className={isDash ? 'h-56' : 'h-48'}>
            <Line data={chartData} options={chartOptions} />
          </div>
        </>
      )}
    </section>
  );
};

export default EmailActivityChart;
