import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Helmet } from 'react-helmet';
import { useNavigate } from 'react-router-dom';
import { AlertTriangle, ChevronLeft, DatabaseBackup, Download, Loader2, RefreshCw, Trash2 } from 'lucide-react';

import DashboardNavbar from '@/components/common/DashboardNavbar';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useToast } from '@/components/ui/use-toast';
import usePurchasedModules from '@/hooks/usePurchasedModules';
import { getCompanyUser, logoutCompany } from '@/services/companyAuthService';
import companyBackupsService from '@/services/companyBackupsService';
import { getAgentNavItems } from '@/utils/agentNavItems';

const formatSize = (bytes) => {
  if (!bytes) return '—';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  return `${(bytes / 1024 ** i).toFixed(i ? 1 : 0)} ${units[i]}`;
};

const formatDate = (iso) => (iso ? new Date(iso).toLocaleString() : '—');

const STATUS_BADGE = {
  running: { label: 'Running', className: 'border-amber-500/30 bg-amber-500/15 text-amber-700 dark:text-amber-300' },
  done: { label: 'Ready', className: 'border-emerald-500/30 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300' },
  failed: { label: 'Failed', className: 'border-rose-500/30 bg-rose-500/15 text-rose-700 dark:text-rose-300' },
};

/**
 * /company/settings/backups — the company's own backups (backend: api/views/company_backups.py), as Admin → Backups
 * is for the whole platform. An owner or admin can make one, download it and delete it; one is also made every
 * night, encrypted and sent off-site, and the newest seven of those are kept on the server. Passwords, API keys and sign-in tokens are not in them.
 */
export default function CompanyBackupsPage() {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { purchasedModules, modulesLoaded } = usePurchasedModules();
  const companyUser = useMemo(() => getCompanyUser(), []);
  const [backups, setBackups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [starting, setStarting] = useState(false);
  const [busyId, setBusyId] = useState(null);
  const [toDelete, setToDelete] = useState(null);

  const handleLogout = async () => {
    await logoutCompany();
    navigate('/company/login');
  };

  const load = useCallback(async () => {
    try {
      const res = await companyBackupsService.listBackups();
      setBackups(res?.data || []);
      setError('');
    } catch (e) {
      setError(e?.message || 'Could not load the backups.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // While one is being made, check on it every few seconds so it turns Ready on its own.
  const running = backups.some((b) => b.status === 'running');
  useEffect(() => {
    if (!running) return undefined;
    const timer = setInterval(load, 4000);
    return () => clearInterval(timer);
  }, [running, load]);

  const handleStart = async () => {
    setStarting(true);
    try {
      await companyBackupsService.startBackup();
      toast({ title: 'Backup started', description: 'It is being made in the background. It shows Ready here when it is done.' });
      load();
    } catch (e) {
      toast({ title: 'Could not start the backup', description: e?.message || 'Please try again.', variant: 'destructive' });
    } finally {
      setStarting(false);
    }
  };

  const handleDownload = async (backup) => {
    setBusyId(backup.id);
    try {
      await companyBackupsService.downloadBackup(backup.id);
    } catch (e) {
      toast({ title: 'Could not download the backup', description: e?.message || 'Please try again.', variant: 'destructive' });
    } finally {
      setBusyId(null);
    }
  };

  const handleDelete = async () => {
    const backup = toDelete;
    setToDelete(null);
    setBusyId(backup.id);
    try {
      await companyBackupsService.deleteBackup(backup.id);
      toast({ title: 'Backup deleted' });
      load();
    } catch (e) {
      toast({ title: 'Could not delete the backup', description: e?.message || 'Please try again.', variant: 'destructive' });
    } finally {
      setBusyId(null);
    }
  };

  return (
    <>
      <Helmet><title>Backups — AIEmployee</title></Helmet>
      <div className="min-h-screen overflow-x-hidden" style={{ background: 'var(--app-page-bg)' }}>
        <DashboardNavbar
          icon={DatabaseBackup}
          title="Backups"
          subtitle="Your company's data and uploaded files, in one zip"
          user={companyUser}
          userRole="Company User"
          onLogout={handleLogout}
          showNavTabs
          activeSection="dashboard"
          navItems={getAgentNavItems(purchasedModules, 'dashboard', navigate)}
          sidebarLoading={!modulesLoaded}
        />
        <div className="container mx-auto max-w-4xl px-4 py-8 space-y-5">
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            <ChevronLeft className="h-4 w-4" /> Back
          </button>

          {error ? (
            <p className="rounded-xl border border-border bg-[var(--panel-2)] p-4 text-sm text-muted-foreground">{error}</p>
          ) : (
            <>
              <div className="flex flex-wrap items-start justify-between gap-4 rounded-xl border border-border bg-[var(--panel-2)] p-4">
                <div className="min-w-0 max-w-2xl space-y-1.5">
                  <h2 className="text-sm font-semibold text-foreground">Back up your company</h2>
                  <p className="text-sm text-muted-foreground">
                    One zip with your company's data across every agent (leads, campaigns, tickets, employees,
                    recruitment, meetings and the rest), the files you uploaded, and your leads as spreadsheets.
                    Passwords, API keys and mailbox or CRM credentials are left out. It is made in the background and
                    kept until you delete it. One is also made every night at 2 AM (Pakistan time), encrypted and sent
                    off-site; the server keeps the newest seven of those.
                  </p>
                </div>
                <Button onClick={handleStart} disabled={starting || running || loading}
                  className="bg-gradient-to-r from-violet-600 to-fuchsia-600 text-white">
                  {starting || running ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <DatabaseBackup className="mr-2 h-4 w-4" />}
                  {running ? 'Backing up…' : 'Create backup'}
                </Button>
              </div>

              <div className="rounded-xl border border-border bg-[var(--panel-2)] p-4">
                <div className="mb-2 flex items-center justify-between">
                  <h2 className="text-sm font-semibold text-foreground">Your backups</h2>
                  <Button variant="ghost" size="sm" onClick={load} title="Refresh"><RefreshCw className="h-4 w-4" /></Button>
                </div>
                {loading ? (
                  <div className="flex justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-violet-500" /></div>
                ) : backups.length === 0 ? (
                  <p className="py-8 text-center text-sm text-muted-foreground">No backups yet. Create one above.</p>
                ) : (
                  <div className="divide-y divide-border">
                    {backups.map((b) => {
                      const badge = STATUS_BADGE[b.status] || STATUS_BADGE.failed;
                      return (
                        <div key={b.id} className="flex flex-wrap items-center justify-between gap-4 py-3">
                          <div className="min-w-0 space-y-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="break-all text-sm font-medium text-foreground">{b.file_name}</span>
                              <Badge variant="outline" className={badge.className}>{badge.label}</Badge>
                            </div>
                            <div className="text-xs text-muted-foreground">
                              {formatDate(b.created_at)}{b.nightly ? ' · nightly' : b.created_by ? ` · by ${b.created_by}` : ''}
                              {b.status === 'done' && (
                                <> · {formatSize(b.size_bytes)} · {(b.records ?? 0).toLocaleString()} records · {(b.files ?? 0).toLocaleString()} files</>
                              )}
                            </div>
                            {b.status === 'failed' && b.error && (
                              <div className="flex items-center gap-1 text-xs text-rose-600 dark:text-rose-400">
                                <AlertTriangle className="h-3 w-3 shrink-0" /> {b.error}
                              </div>
                            )}
                          </div>
                          <div className="flex items-center gap-2">
                            {b.status === 'done' && (
                              <Button size="sm" variant="outline" disabled={busyId === b.id} onClick={() => handleDownload(b)}>
                                {busyId === b.id ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Download className="mr-1 h-4 w-4" />} Download
                              </Button>
                            )}
                            {b.status !== 'running' && (
                              <Button size="sm" variant="ghost" className="text-rose-600 hover:text-rose-500 dark:text-rose-400"
                                disabled={busyId === b.id} onClick={() => setToDelete(b)} title="Delete this backup">
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      <Dialog open={!!toDelete} onOpenChange={(open) => { if (!open) setToDelete(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete this backup?</DialogTitle>
            <DialogDescription>
              {toDelete?.file_name} is removed from the server for good. Download it first if you want to keep a copy.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setToDelete(null)}>Cancel</Button>
            <Button variant="destructive" onClick={handleDelete}>Delete</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
