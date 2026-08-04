import React, { useState, useEffect } from 'react';
import { Settings as SettingsIcon, BarChart3, Edit3, Trash2, Loader2 } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { useToast } from '@/components/ui/use-toast';
import { getReplyAnalytics, deleteReplyAccount } from '@/services/replyDraftService';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Filler,
} from 'chart.js';
import { Line } from 'react-chartjs-2';

// Safe to call more than once — Chart.js dedupes registrations, so the fact
// that CampaignDetail also registers these won't cause problems.
ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Filler);

// Settings dialog surfaced from the header gear button once an account is
// attached. Shows account info with edit/disconnect actions and a single
// window-selectable bar chart of inbox volume (30/60/90/120 days).
const ANALYTICS_WINDOWS = [30, 60, 90];

export const SettingsModal = ({ open, account, onClose, onEdit, onDeleted }) => {
  const { toast } = useToast();
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(false);
  const [windowDays, setWindowDays] = useState(30);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setConfirmDelete(false);
    setWindowDays(30);
  }, [open]);

  // Refetch whenever the modal opens OR the user switches the window.
  useEffect(() => {
    if (!open) return;
    setLoading(true);
    getReplyAnalytics({ days: windowDays })
      .then((res) => setAnalytics(res?.status === 'success' ? res.data : null))
      .catch(() => setAnalytics(null))
      .finally(() => setLoading(false));
  }, [open, windowDays]);

  const handleDelete = async () => {
    setDeleting(true);
    try {
      const res = await deleteReplyAccount();
      if (res?.status === 'success') {
        toast({ title: 'Account disconnected', description: res?.data?.message || 'Inbox cleared.' });
        onDeleted();
      } else {
        toast({ title: 'Delete failed', description: res?.message || 'Could not disconnect the account.', variant: 'destructive' });
      }
    } catch (e) {
      toast({ title: 'Delete failed', description: e?.message || 'Could not disconnect the account.', variant: 'destructive' });
    } finally {
      setDeleting(false);
    }
  };

  const buckets = analytics?.buckets || [];
  const granularity = analytics?.granularity || 'day';  // 'day' | 'week'

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

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <SettingsIcon className="h-5 w-5 text-primary" />
            Inbox settings &amp; analytics
          </DialogTitle>
          <DialogDescription>
            Stats are scoped to the attached Reply Draft Agent account only.
          </DialogDescription>
        </DialogHeader>

        <div className="py-4 space-y-5">
          {/* Account info + actions */}
          <section className="rounded-lg border p-4 space-y-3">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div className="min-w-0">
                <div className="text-xs text-muted-foreground">Connected account</div>
                <div className="text-sm font-semibold truncate">{account?.email || '—'}</div>
                <div className="text-xs text-muted-foreground mt-0.5">
                  {account?.account_type || 'smtp'} · IMAP: {account?.imap_host || '—'}
                </div>
              </div>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={onEdit} disabled={deleting}>
                  <Edit3 className="h-3.5 w-3.5 mr-2" />
                  Edit
                </Button>
                {!confirmDelete ? (
                  <Button variant="destructive" size="sm" onClick={() => setConfirmDelete(true)} disabled={deleting}>
                    <Trash2 className="h-3.5 w-3.5 mr-2" />
                    Disconnect
                  </Button>
                ) : (
                  <Button variant="destructive" size="sm" onClick={handleDelete} disabled={deleting}>
                    {deleting ? <Loader2 className="h-3.5 w-3.5 mr-2 animate-spin" /> : <Trash2 className="h-3.5 w-3.5 mr-2" />}
                    Really disconnect?
                  </Button>
                )}
              </div>
            </div>
            {confirmDelete && (
              <div className="rounded-md border border-rose-200 bg-rose-500/5 p-3 text-xs text-rose-700 dark:text-rose-400 dark:border-rose-800">
                Disconnecting deletes this account <strong>and all its synced inbox mail + drafts</strong>. This cannot be undone.{' '}
                <button type="button" onClick={() => setConfirmDelete(false)} className="underline">
                  Cancel
                </button>
              </div>
            )}
          </section>

          {/* Inbox volume chart */}
          <section className="rounded-lg border p-4 space-y-3">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div className="flex items-center gap-2 text-sm font-semibold">
                <BarChart3 className="h-4 w-4 text-primary" />
                Email activity
              </div>
              <div className="flex gap-1 p-0.5 rounded-md bg-muted text-xs">
                {ANALYTICS_WINDOWS.map((w) => (
                  <button
                    key={w}
                    type="button"
                    onClick={() => setWindowDays(w)}
                    className={`px-2.5 py-1 rounded transition-colors ${windowDays === w ? 'bg-background shadow-sm font-medium' : 'text-muted-foreground'
                      }`}
                  >
                    {w}d
                  </button>
                ))}
              </div>
            </div>

            {loading ? (
              <div className="flex justify-center py-8">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            ) : buckets.length === 0 ? (
              <div className="text-xs text-muted-foreground py-6 text-center">No data.</div>
            ) : (
              <>
                <div className="text-xs text-muted-foreground">
                  <span className="font-semibold text-cyan-300">{analytics?.received_total ?? 0}</span>
                  {' '}received ·{' '}
                  <span className="font-semibold text-emerald-300">{analytics?.sent_total ?? 0}</span>
                  {' '}sent in the last {windowDays} days
                  {granularity === 'week' && (
                    <span className="ml-1 opacity-75">· grouped by week</span>
                  )}
                </div>
                <div className="h-48">
                  <Line data={chartData} options={chartOptions} />
                </div>
              </>
            )}
          </section>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
