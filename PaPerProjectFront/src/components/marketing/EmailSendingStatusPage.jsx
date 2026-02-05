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
  bounced: 'Bounced',
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

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      await fetchData(false);
    };
    run();
    return () => { cancelled = true; };
  }, [id]);

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

  const { campaign, stats, currently_sending, emails_by_sequence, total_emails_shown } = data || {};

  return (
    <div className="space-y-6">
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
        <Button variant="outline" size="sm" onClick={() => fetchData(true)} disabled={refreshing}>
          <RefreshCw className={`mr-2 h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <Card className={currently_sending ? 'border-green-500 bg-green-50 dark:bg-green-950/20' : ''}>
          <CardContent className="pt-4 pb-4">
            <div className="text-sm text-muted-foreground">Total sent</div>
            <div className="text-2xl font-semibold">{stats?.total_sent ?? 0}</div>
            <div className="text-xs text-muted-foreground mt-1">
              {currently_sending ? 'Currently sending' : 'Not sending'}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 pb-4">
            <div className="text-sm text-muted-foreground">Opened</div>
            <div className="text-2xl font-semibold text-amber-600">{stats?.total_opened ?? 0}</div>
            <div className="text-xs text-muted-foreground mt-1">{stats?.open_rate ?? 0}% open rate</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 pb-4">
            <div className="text-sm text-muted-foreground">Clicked</div>
            <div className="text-2xl font-semibold text-violet-600">{stats?.total_clicked ?? 0}</div>
            <div className="text-xs text-muted-foreground mt-1">{stats?.click_rate ?? 0}% click rate</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 pb-4">
            <div className="text-sm text-muted-foreground">Replied</div>
            <div className="text-2xl font-semibold text-green-600">{stats?.total_replied ?? 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 pb-4">
            <div className="text-sm text-muted-foreground">Failed</div>
            <div className="text-2xl font-semibold text-red-600">{stats?.total_failed ?? 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 pb-4">
            <div className="text-sm text-muted-foreground">Bounced</div>
            <div className="text-2xl font-semibold">{stats?.total_bounced ?? 0}</div>
          </CardContent>
        </Card>
      </div>

      {/* Email history by sequence */}
      {emails_by_sequence && Object.keys(emails_by_sequence).length > 0 ? (
        <div className="space-y-4">
          <h2 className="text-lg font-semibold">Email history (last {total_emails_shown ?? 100})</h2>
          {Object.entries(emails_by_sequence).map(([seqName, emails]) => (
            <Card key={seqName}>
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <span className="rounded bg-primary/10 px-2 py-0.5 text-sm font-medium text-primary">
                    {seqName}
                  </span>
                </CardTitle>
                <CardDescription>{emails.length} email(s)</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="rounded-md border overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b bg-muted/50">
                        <th className="text-left p-2 font-medium">Recipient</th>
                        <th className="text-left p-2 font-medium">Subject</th>
                        <th className="text-center p-2 font-medium">Status</th>
                        <th className="text-left p-2 font-medium">Sent at</th>
                      </tr>
                    </thead>
                    <tbody>
                      {emails.map((e) => (
                        <tr key={e.id} className="border-b last:border-0">
                          <td className="p-2">{e.recipient_email}</td>
                          <td className="p-2 max-w-[200px] truncate" title={e.subject}>{e.subject}</td>
                          <td className="p-2 text-center">
                            <Badge variant="secondary" className="text-xs">
                              {STATUS_LABELS[e.status] || e.status}
                            </Badge>
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
        <Card>
          <CardContent className="pt-6">
            <p className="text-center text-muted-foreground py-8">No email activity yet.</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default EmailSendingStatusPage;
