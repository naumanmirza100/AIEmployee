import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Loader2, ArrowLeft, FileText, RefreshCw } from 'lucide-react';
import { getEmailStatusFull } from '@/services/marketingAgentService';

const STATUS_LABELS = {
  pending: 'Pending',
  sent: 'Sent',
  delivered: 'Delivered',
  opened: 'Opened',
  clicked: 'Clicked',
  // bounced: 'Bounced',
  failed: 'Failed',
  unsubscribed: 'Unsubscribed',
};

const formatDateTime = (iso) => {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch {
    return iso;
  }
};

const formatTimeRemaining = (iso) => {
  if (!iso) return '';
  try {
    const sendTime = new Date(iso);
    const now = new Date();
    const diffMs = sendTime - now;
    if (diffMs <= 0) return 'Ready to send';
    const diffM = Math.floor(diffMs / 60000);
    const diffH = Math.floor(diffM / 60);
    const diffD = Math.floor(diffH / 24);
    if (diffD > 0) return `${diffD}d ${diffH % 24}h from now`;
    if (diffH > 0) return `${diffH}h ${diffM % 60}m from now`;
    return `${diffM} min from now`;
  } catch {
    return '';
  }
};

const formatDelay = (d, h, m) => {
  const parts = [];
  if (d > 0) parts.push(`${d}d`);
  if (h > 0) parts.push(`${h}h`);
  if (m > 0) parts.push(`${m}m`);
  return parts.length ? parts.join(' ') : 'Immediate';
};

/** Strip HTML tags so reply content doesn't show raw <a href="..."> or long tracking URLs in tags. */
const stripHtmlForDisplay = (html) => {
  if (!html || typeof html !== 'string') return '';
  return html
    .replace(/<[^>]+>/g, ' ')
    .replace(/  +/g, ' ')
    .trim();
};

const INTEREST_LABELS = {
  positive: 'Interested',
  negative: 'Not Interested',
  neutral: 'Neutral',
  requested_info: 'Requested Info',
  objection: 'Objection',
  unsubscribe: 'Unsubscribe',
  not_analyzed: 'Not Analyzed',
};

const EmailSendingStatusPage = ({ embedded = false }) => {
  const { id } = useParams();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const fetchData = async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const res = await getEmailStatusFull(id);
      if (res?.status === 'success' && res?.data) {
        setData(res.data);
      } else {
        setError(res?.message || 'Failed to load email status');
      }
    } catch (e) {
      setError(e?.message || 'Failed to load email status');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  // Initial load
  useEffect(() => {
    fetchData(false);
  }, [id]);

  // Auto-refresh so changes (new emails, pending, replies) show without reloading the page
  const POLL_INTERVAL_MS = 30 * 1000; // 30 seconds
  useEffect(() => {
    if (!id || loading) return;
    const interval = setInterval(() => {
      fetchData(true); // background refresh (uses refreshing state, not full loading)
    }, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [id, loading]);

  if (loading && !refreshing) {
    return (
      <div className="flex items-center justify-center min-h-[320px]">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="space-y-4">
        {!embedded && (
          <Button variant="ghost" asChild>
            <Link to={`/marketing/dashboard/campaign/${id}`}>
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back to campaign
            </Link>
          </Button>
        )}
        <Card>
          <CardContent className="pt-6">
            <p className="text-destructive">{error}</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  const { campaign, stats, currently_sending, emails_by_sequence, total_emails_shown, pending_emails = [], upcoming_emails = [], replies = [], replies_by_sequence = {} } = data || {};
  const upcomingMain = (upcoming_emails || []).filter((u) => !u.is_sub_sequence);
  const upcomingSub = (upcoming_emails || []).filter((u) => u.is_sub_sequence);

  return (
    <div className="space-y-6 rounded-lg p-4 md:p-6 border ">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          {!embedded && (
            <Button variant="ghost" asChild>
              <Link to={`/marketing/dashboard/campaign/${id}`}>
                <ArrowLeft className="mr-2 h-4 w-4" />
                Back to {campaign?.name || 'Campaign'}
              </Link>
            </Button>
          )}
          <h1 className={`flex items-center gap-2 ${embedded ? 'text-lg font-semibold' : 'text-2xl font-semibold mt-2'}`}>
            <FileText className="h-6 w-6" />
            Email sending status
          </h1>
          <p className="text-muted-foreground text-sm mt-1">
            Track emails sent, opens, clicks, and replies.
          </p>
        </div>
        <div className="flex items-center gap-2">
        <Button variant="outline" size="sm" onClick={() => fetchData(true)} disabled={refreshing}>
          <RefreshCw className={`mr-2 h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
        <span className="text-xs text-muted-foreground ml-2">Auto-refreshes every 30s</span>
        </div>
      </div>

      {/* Stats cards - muted professional colors */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-7 gap-3">
        <Card className={currently_sending ? 'border-emerald-400/70 dark:border-emerald-600/60 bg-emerald-100/50 dark:bg-emerald-950/35' : 'border-slate-200/80 dark:border-slate-800/80'}>
          <CardContent className="pt-4 pb-4">
            <div className={`text-sm ${currently_sending ? 'text-emerald-900 dark:text-emerald-300' : 'text-muted-foreground'}`}>Total sent</div>
            <div className={`text-2xl font-semibold ${currently_sending ? 'text-emerald-900 dark:text-emerald-200' : 'text-foreground'}`}>{stats?.total_sent ?? 0}</div>
            <div className={`text-xs mt-1 ${currently_sending ? 'text-emerald-900 dark:text-emerald-400/90' : 'text-muted-foreground'}`}>
              {currently_sending ? 'Currently sending' : 'Not sending'}
            </div>
          </CardContent>
        </Card>
        <Card className="border-slate-200/80 dark:border-slate-800/80">
          <CardContent className="pt-4 pb-4">
            <div className="text-sm text-muted-foreground">Opened</div>
            <div className="text-2xl font-semibold text-amber-700/90 dark:text-amber-400/90">{stats?.total_opened ?? 0}</div>
            <div className="text-xs text-muted-foreground mt-1">{stats?.open_rate ?? 0}% open rate</div>
          </CardContent>
        </Card>
        <Card className="border-slate-200/80 dark:border-slate-800/80">
          <CardContent className="pt-4 pb-4">
            <div className="text-sm text-muted-foreground">Clicked</div>
            <div className="text-2xl font-semibold text-violet-700/90 dark:text-violet-400/90">{stats?.total_clicked ?? 0}</div>
            <div className="text-xs text-muted-foreground mt-1">{stats?.click_rate ?? 0}% click rate</div>
          </CardContent>
        </Card>
        <Card className="border-slate-200/80 dark:border-slate-800/80">
          <CardContent className="pt-4 pb-4">
            <div className="text-sm text-muted-foreground">Replied</div>
            <div className="text-2xl font-semibold text-emerald-700/90 dark:text-emerald-400/90">{stats?.total_replied ?? 0}</div>
          </CardContent>
        </Card>
        <Card className="border-slate-200/80 dark:border-slate-800/80">
          <CardContent className="pt-4 pb-4">
            <div className="text-sm text-muted-foreground">Failed</div>
            <div className="text-2xl font-semibold text-red-700/90 dark:text-red-400/90">{stats?.total_failed ?? 0}</div>
          </CardContent>
        </Card>
        <Card className={(stats?.pending_count ?? 0) > 0 ? 'border-amber-400/70 dark:border-amber-600/50 bg-amber-100/20 dark:bg-amber-950/30' : 'border-slate-200/80 dark:border-slate-800/80'}>
          <CardContent className="pt-4 pb-4">
            <div className={`text-sm ${(stats?.pending_count ?? 0) > 0 ? 'text-amber-700 dark:text-amber-300/90' : 'text-muted-foreground'}`}>Pending</div>
            <div className={`text-2xl font-semibold ${(stats?.pending_count ?? 0) > 0 ? 'text-amber-800 dark:text-amber-200/90' : 'text-foreground'}`}>{stats?.pending_count ?? 0}</div>
            <div className={`text-xs mt-1 ${(stats?.pending_count ?? 0) > 0 ? 'text-amber-600 dark:text-amber-400/80' : 'text-muted-foreground'}`}>Ready to send</div>
          </CardContent>
        </Card>
        <Card className="border-slate-200/80 dark:border-slate-800/80 bg-sky-50/20 dark:bg-sky-950/25">
          <CardContent className="pt-4 pb-4">
            <div className="text-sm text-sky-500/90 dark:text-sky-300/90">Upcoming</div>
            <div className="text-2xl font-semibold text-sky-500/90 dark:text-sky-300/90">{stats?.upcoming_count ?? 0}</div>
            <div className="text-xs text-muted-foreground mt-1">Scheduled (next 24h)</div>
          </CardContent>
        </Card>
      </div>

      {/* Email history by sequence - matches template: Type (Initial/Seq/Sub-Seq), Replied + interest */}
      {emails_by_sequence && Object.keys(emails_by_sequence).length > 0 ? (
        <div className="space-y-4">
          <h2 className="text-lg font-semibold">Full email history (last {total_emails_shown ?? 100}) – by sequence</h2>
          {Object.entries(emails_by_sequence).map(([seqName, emails]) => (
            <Card key={seqName} className="border-slate-700/80">
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <span className="rounded bg-sky-600/90  text-sky-50 px-2 py-0.5 text-sm font-semibold">
                    Sequence: {seqName}
                  </span>
                </CardTitle>
                <CardDescription>{emails.length} email(s)</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="rounded-md  overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-slate-200  bg-slate-600/80 ">
                        <th className="text-left p-2 font-medium">Recipient</th>
                        <th className="text-left p-2 font-medium">Subject</th>
                        <th className="text-center p-2 font-medium">Type</th>
                        <th className="text-center p-2 font-medium">Status</th>
                        <th className="text-center p-2 font-medium">Replied</th>
                        <th className="text-left p-2 font-medium">Sent at</th>
                      </tr>
                    </thead>
                    <tbody>
                      {emails.map((e) => (
                        <tr key={e.id} className="border-b last:border-0">
                          <td className="p-2 text-foreground">{e.recipient_email}</td>
                          <td className="p-2 max-w-[200px] truncate text-foreground" title={e.subject}>{e.subject}</td>
                          <td className="p-2 text-center">
                            {e.type === 'sub_sequence' ? (
                              <span className="inline-block rounded bg-violet-100/90 dark:bg-violet-900/35 text-violet-800 dark:text-violet-300 px-2 py-0.5 text-xs font-semibold border border-violet-200/50 dark:border-violet-700/40">
                                Sub-Sequence
                              </span>
                            ) : e.type === 'sequence' ? (
                              <span className="inline-block rounded bg-rose-100/90 dark:bg-rose-900/35 text-rose-800 dark:text-rose-300 px-2 py-0.5 text-xs font-semibold border border-rose-200/50 dark:border-rose-700/40">
                                Sequence
                              </span>
                            ) : (
                              <span className="inline-block rounded bg-sky-100/90 dark:bg-sky-900/35 text-sky-800 dark:text-sky-300 px-2 py-0.5 text-xs font-semibold border border-sky-200/50 dark:border-sky-700/40">
                                Initial
                              </span>
                            )}
                          </td>
                          <td className="p-2 text-center">
                            <Badge variant="secondary" className="text-xs bg-slate-100 dark:bg-slate-800/60 text-slate-700 dark:text-slate-300">
                              {STATUS_LABELS[e.status] || e.status}
                            </Badge>
                          </td>
                          <td className="p-2 text-center">
                            {e.is_replied ? (
                              <div className="flex flex-col items-center gap-0.5">
                                <span className="rounded bg-emerald-100/90 dark:bg-emerald-900/35 text-emerald-800 dark:text-emerald-300 px-2 py-0.5 text-xs font-semibold border border-emerald-200/50 dark:border-emerald-700/40">
                                  Replied
                                </span>
                                {e.reply_interest_level && e.reply_interest_level !== 'not_analyzed' ? (
                                  e.reply_interest_level === 'requested_info' ? (
                                    <span className="mt-1 rounded bg-blue-100 dark:bg-blue-900/40 text-blue-800 dark:text-blue-300 px-2 py-0.5 text-xs font-semibold border border-blue-200/50 dark:border-blue-700/40">
                                      Requested Info
                                    </span>
                                  ) : (
                                    <span className={`text-xs font-medium ${e.reply_interest_level === 'positive' ? 'text-green-600 dark:text-green-400' :
                                        e.reply_interest_level === 'negative' ? 'text-red-600 dark:text-red-400' :
                                          e.reply_interest_level === 'neutral' ? 'text-muted-foreground' :
                                            e.reply_interest_level === 'objection' ? 'text-amber-600 dark:text-amber-400' :
                                              e.reply_interest_level === 'unsubscribe' ? 'text-red-600 dark:text-red-400' : 'text-muted-foreground'
                                      }`}>
                                      {INTEREST_LABELS[e.reply_interest_level] || e.reply_interest_level}
                                    </span>
                                  )
                                ) : null}
                              </div>
                            ) : (
                              <span className="text-muted-foreground text-xs">—</span>
                            )}
                          </td>
                          <td className="p-2 text-muted-foreground">{formatDateTime(e.sent_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <Card className="border-slate-200/80 dark:border-slate-800/80">
          <CardContent className="pt-6">
            <p className="text-center text-muted-foreground py-8">No email activity yet.</p>
          </CardContent>
        </Card>
      )}
      {/* Upcoming main sequence (next 24 hours) */}
      {upcomingMain.length > 0 && (
        <Card className="border-slate-700/80">
          <CardHeader>
            <CardTitle className="text-base text-sky-600 ">Upcoming sequence sends (next 24 hours)</CardTitle>
            <CardDescription>{upcomingMain.length} main sequence email(s) scheduled</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-3">
              {upcomingMain.map((u, idx) => (
                <li key={`main-${idx}`} className="rounded-lg border-l-4 border-sky-500/70 bg-[rgba(76,75,74,0.2)] p-3">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="font-medium text-foreground">{u.lead_email}</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        Next: Step {u.step_order} – {(u.template_name || '').replace(/neutal/i, 'neutral')}
                      </p>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        Delay: {formatDelay(u.delay_days, u.delay_hours, u.delay_minutes)}
                      </p>
                    </div>
                    <div className="text-right shrink-0">
                      <p className="font-semibold text-sky-800 dark:text-sky-200">{formatDateTime(u.next_send_time)}</p>
                      <p className="text-xs text-muted-foreground">{formatTimeRemaining(u.next_send_time)}</p>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {/* Upcoming sub-sequence sends (from replies) */}
      {upcomingSub.length > 0 && (
        <Card className="border-slate-700/80">
          <CardHeader>
            <CardTitle className="text-base text-violet-600 ">Upcoming sub-sequence sends (next 24 hours)</CardTitle>
            <CardDescription>{upcomingSub.length} sub-sequence email(s) – triggered by replies</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="space-y-3">
              {upcomingSub.map((u, idx) => (
                <li key={`sub-${idx}`} className="rounded-lg border-l-4 border-violet-500/70 bg-[rgba(76,75,74,0.2)] p-3">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="font-medium text-foreground">{u.lead_email}</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        <span className="inline-block rounded bg-violet-100/90 dark:bg-violet-900/35 text-violet-800 dark:text-violet-300 text-xs px-1.5 py-0.5 mr-1.5 border border-violet-200/50 dark:border-violet-700/40">
                          Sub: {u.sub_sequence_name || u.sequence_name}
                        </span>
                        <span>Next: Step {u.step_order} – {(u.template_name || '').replace(/neutal/i, 'neutral')}</span>
                      </p>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        Delay: {formatDelay(u.delay_days, u.delay_hours, u.delay_minutes)}
                      </p>
                    </div>
                    <div className="text-right shrink-0">
                      <p className="font-semibold text-violet-800 dark:text-violet-200">{formatDateTime(u.next_send_time)}</p>
                      <p className="text-xs text-muted-foreground">{formatTimeRemaining(u.next_send_time)}</p>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {/* Replied contacts */}
      {(replies.length > 0 || Object.keys(replies_by_sequence).length > 0) && (
        <Card className="border-slate-700/80">
          <CardHeader>
            <CardTitle className="text-base text-emerald-600 ">Replied contacts</CardTitle>
            <CardDescription>Reply, email they replied to, and AI interest</CardDescription>
          </CardHeader>
          <CardContent>
            {Object.keys(replies_by_sequence).length > 0 ? (
              <div className="space-y-4">
                {Object.entries(replies_by_sequence).map(([seqKey, { sequence_name, replies: seqReplies }]) => (
                  <div key={seqKey} className=" p-3">
                    <h4 className="text-sm font-semibold text-foreground mb-2 flex items-center gap-2">
                      <span className="rounded bg-sky-100  text-sky-800  px-2 py-0.5 text-xs font-medium border border-sky-200/50 ">
                        {sequence_name}
                      </span>
                    </h4>
                    <ul className="space-y-3">
                      {seqReplies.map((r) => (
                        <li key={r.id} className="rounded-lg border-l-4 border-b-[0.5px] border-emerald-500/70  p-3 space-y-2">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <p className="font-medium text-foreground">{r.lead_email}</p>
                            <div className="flex items-center gap-2 shrink-0">
                              {r.interest_level && r.interest_level !== 'not_analyzed' ? (
                                r.interest_level === 'requested_info' ? (
                                  <span className="rounded bg-blue-100 dark:bg-blue-900/40 text-blue-800 dark:text-blue-300 px-2 py-0.5 text-xs font-semibold border border-blue-200/50 dark:border-blue-700/40">
                                    Requested Info
                                  </span>
                                ) : (
                                  <Badge
                                    variant={
                                      r.interest_level === 'positive'
                                        ? 'default'
                                        : r.interest_level === 'negative'
                                          ? 'destructive'
                                          : 'secondary'
                                    }
                                    className="text-xs"
                                  >
                                    {INTEREST_LABELS[r.interest_level] || r.interest_level}
                                  </Badge>
                                )
                              ) : null}
                              <span className="text-xs text-muted-foreground">{formatDateTime(r.replied_at)}</span>
                            </div>
                          </div>
                          {r.in_reply_to_subject && (
                            <p className="text-xs text-muted-foreground">
                              In reply to: <span className="font-medium text-foreground">{r.in_reply_to_subject}</span>
                            </p>
                          )}
                          {r.reply_subject && (
                            <p className="text-xs">
                              Reply subject: <span className="font-medium text-foreground">{r.reply_subject}</span>
                            </p>
                          )}
                          {r.reply_content && (
                            <div className="rounded bg-muted/50 dark:bg-muted/40 p-2 text-sm text-foreground whitespace-pre-wrap break-words">
                              {stripHtmlForDisplay(r.reply_content)}
                            </div>
                          )}
                          {r.sub_sequence_name && (
                            <span className="inline-block rounded bg-violet-100/90 dark:bg-violet-900/35 text-violet-800 dark:text-violet-300 text-xs px-1.5 py-0.5 border border-violet-200/50 dark:border-violet-700/40">
                              Sub-seq: {r.sub_sequence_name}
                            </span>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            ) : (
              <ul className="space-y-3">
                {replies.map((r) => (
                  <li key={r.id} className="rounded-lg border-l-4 border-emerald-500/70  p-3 space-y-2">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="font-medium text-foreground">{r.lead_email}</p>
                      <div className="flex items-center gap-2 shrink-0">
{r.interest_level && r.interest_level !== 'not_analyzed' ? (
                        r.interest_level === 'requested_info' ? (
                          <span className="rounded bg-blue-100 dark:bg-blue-900/40 text-blue-800 dark:text-blue-300 px-2 py-0.5 text-xs font-semibold border border-blue-200/50 dark:border-blue-700/40">
                            Requested Info
                          </span>
                        ) : (
                          <Badge
                            variant={
                              r.interest_level === 'positive'
                                ? 'default'
                                : r.interest_level === 'negative'
                                  ? 'destructive'
                                  : 'secondary'
                            }
                            className="text-xs"
                          >
                            {INTEREST_LABELS[r.interest_level] || r.interest_level}
                          </Badge>
                        )
                        ) : null}
                        <span className="text-xs text-muted-foreground">{formatDateTime(r.replied_at)}</span>
                      </div>
                    </div>
                    {r.in_reply_to_subject && (
                      <p className="text-xs text-muted-foreground">
                        In reply to: <span className="font-medium text-foreground">{r.in_reply_to_subject}</span>
                      </p>
                    )}
                    {r.reply_subject && (
                      <p className="text-xs">
                        Reply subject: <span className="font-medium text-foreground">{r.reply_subject}</span>
                      </p>
                    )}
                    {r.reply_content && (
                      <div className="rounded bg-muted/50 dark:bg-muted/40 p-2 text-sm text-foreground whitespace-pre-wrap break-words">
                        {stripHtmlForDisplay(r.reply_content)}
                      </div>
                    )}
                    {r.sub_sequence_name && (
                      <span className="inline-block rounded bg-violet-100/90 dark:bg-violet-900/35 text-violet-800 dark:text-violet-300 text-xs px-1.5 py-0.5 border border-violet-200/50 dark:border-violet-700/40">
                        Sub-seq: {r.sub_sequence_name}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      )}

      {/* Pending emails (ready to send) */}
      {pending_emails.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base text-amber-800 dark:text-amber-200">Pending emails (ready to send)</CardTitle>
            <CardDescription>{pending_emails.length} email(s) waiting to be sent</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="rounded-md border border-slate-200/60 dark:border-slate-700/50 overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="text-left p-2 font-medium">Recipient</th>
                    <th className="text-left p-2 font-medium">Subject</th>
                    <th className="text-left p-2 font-medium">Sequence / Step</th>
                    <th className="text-center p-2 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {pending_emails.map((p, idx) => (
                    <tr key={idx} className="border-b last:border-0">
                      <td className="p-2">{p.recipient_email}</td>
                      <td className="p-2 max-w-[200px] truncate" title={p.subject}>{p.subject}</td>
                      <td className="p-2">
                        {p.is_sub_sequence && p.sub_sequence_name ? (
                          <span>{p.sub_sequence_name} </span>
                        ) : (
                          <span>{p.sequence_name} – Step {p.step_order} </span>
                        )}
                      </td>
                      <td className="p-2 text-center ">
                        <Badge variant={p.is_retry ? 'destructive' : 'secondary'} className="text-xs">
                          {p.is_retry ? 'Retry' : 'Pending'}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}


    </div>
  );
};

export default EmailSendingStatusPage;
