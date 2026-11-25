import React, { useCallback, useEffect, useState } from 'react';
import { Helmet } from 'react-helmet';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog';
import { useToast } from '@/components/ui/use-toast';
import { Loader2, DatabaseBackup, Download, Trash2, RefreshCw, AlertTriangle } from 'lucide-react';
import DashboardNavbar from '@/components/common/DashboardNavbar';
import { getAdminNavItems } from '@/utils/adminNavItems';
import { useAuth } from '@/contexts/AuthContext';
import adminBackupsService from '@/services/adminBackupsService';

const GRADIENT_BG = 'var(--app-page-bg)';

const formatSize = (bytes) => {
  if (!bytes) return '—';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  return `${(bytes / 1024 ** i).toFixed(i ? 1 : 0)} ${units[i]}`;
};

const formatDate = (iso) => (iso ? new Date(iso).toLocaleString() : '—');

const STATUS_BADGE = {
  running: { label: 'Running', className: 'bg-amber-500/15 text-amber-400 border-amber-500/30' },
  done: { label: 'Ready', className: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30' },
  failed: { label: 'Failed', className: 'bg-rose-500/15 text-rose-400 border-rose-500/30' },
};

// Super admin only: back up everything (every company's data across all agents, the users, the platform's own
// data and the uploaded files) into one zip kept on the server, then download or delete it from here.
const AdminBackupsPage = () => {
  const navigate = useNavigate();
  const { logout, user } = useAuth();
  const { toast } = useToast();
  const [backups, setBackups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [busyId, setBusyId] = useState(null);
  const [toDelete, setToDelete] = useState(null);

  const handleLogout = async () => {
    try {
      await logout();
      navigate('/login');
    } catch (error) {
      console.error('Logout error:', error);
    }
  };

  const load = useCallback(async () => {
    try {
      const resp = await adminBackupsService.listBackups();
      setBackups(resp?.data || []);
    } catch (e) {
      toast({ title: 'Could not load the backups', description: String(e.message || e), variant: 'destructive' });
    } finally { setLoading(false); }
  }, [toast]);

  useEffect(() => { load(); }, [load]);

  // While one is being made, check on it every few seconds so it turns Ready on its own.
  const running = backups.some(b => b.status === 'running');
  useEffect(() => {
    if (!running) return undefined;
    const timer = setInterval(load, 4000);
    return () => clearInterval(timer);
  }, [running, load]);

  const handleStart = async () => {
    setStarting(true);
    try {
      await adminBackupsService.startBackup();
      toast({ title: 'Backup started', description: 'It is being made in the background. It shows Ready here when it is done.' });
      load();
    } catch (e) {
      toast({ title: 'Could not start the backup', description: String(e.message || e), variant: 'destructive' });
    } finally { setStarting(false); }
  };

  const handleDownload = async (backup) => {
    setBusyId(backup.id);
    try {
      await adminBackupsService.downloadBackup(backup.id);
    } catch (e) {
      toast({ title: 'Could not download the backup', description: String(e.message || e), variant: 'destructive' });
    } finally { setBusyId(null); }
  };

  const handleDelete = async () => {
    const backup = toDelete;
    setToDelete(null);
    setBusyId(backup.id);
    try {
      await adminBackupsService.deleteBackup(backup.id);
      toast({ title: 'Backup deleted' });
      load();
    } catch (e) {
      toast({ title: 'Could not delete the backup', description: String(e.message || e), variant: 'destructive' });
    } finally { setBusyId(null); }
  };

  return (
    <>
      <Helmet><title>Super Admin — Backups</title></Helmet>
      <div className="min-h-screen overflow-x-hidden" style={{ background: GRADIENT_BG }}>
        <DashboardNavbar
          icon={DatabaseBackup}
          title="Backups"
          subtitle="Back up every company's data, the users and the uploaded files"
          user={user}
          userRole="Admin"
          onLogout={handleLogout}
          showNavTabs
          activeSection="admin-backups"
          navItems={getAdminNavItems(navigate)}
        />

        <div className="container mx-auto px-4 py-8 max-w-5xl space-y-6">
          <Card className="border-violet-500/20 bg-white/[0.02]">
            <CardHeader className="flex flex-row items-start justify-between gap-4 space-y-0 flex-wrap">
              <div className="space-y-1.5 min-w-0">
                <CardTitle className="text-lg">Back up everything</CardTitle>
                <CardDescription className="max-w-2xl">
                  One zip with the whole database (all companies, users, and every agent's data) and the uploaded
                  files (CVs, HR and Frontline documents, attachments). Login sessions, logs and search indexes are
                  left out. It is made in the background and kept on the server until you delete it.
                  One is also made every night, encrypted and sent off-site; the server keeps the last seven of those.
                </CardDescription>
              </div>
              <Button onClick={handleStart} disabled={starting || running}
                className="bg-gradient-to-r from-violet-600 to-fuchsia-600 text-white">
                {starting || running ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <DatabaseBackup className="w-4 h-4 mr-2" />}
                {running ? 'Backing up…' : 'Create backup'}
              </Button>
            </CardHeader>
          </Card>

          <Card className="bg-white/[0.02]">
            <CardHeader className="flex flex-row items-center justify-between space-y-0">
              <CardTitle className="text-base">Backups on the server</CardTitle>
              <Button variant="ghost" size="sm" onClick={load} title="Refresh"><RefreshCw className="w-4 h-4" /></Button>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-violet-400" /></div>
              ) : backups.length === 0 ? (
                <p className="text-sm text-muted-foreground py-8 text-center">No backups yet. Create one above.</p>
              ) : (
                <div className="divide-y divide-white/5">
                  {backups.map(b => {
                    const badge = STATUS_BADGE[b.status] || STATUS_BADGE.failed;
                    return (
                      <div key={b.id} className="flex items-center justify-between gap-4 py-3 flex-wrap">
                        <div className="min-w-0 space-y-1">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-medium text-sm break-all">{b.file_name}</span>
                            <Badge variant="outline" className={badge.className}>{badge.label}</Badge>
                          </div>
                          <div className="text-xs text-muted-foreground">
                            {formatDate(b.created_at)}{b.nightly ? ' · nightly' : b.created_by ? ` · by ${b.created_by}` : ''}
                            {b.status === 'done' && (
                              <> · {formatSize(b.size_bytes)} · {(b.records ?? 0).toLocaleString()} records · {(b.files ?? 0).toLocaleString()} files</>
                            )}
                          </div>
                          {b.status === 'failed' && b.error && (
                            <div className="text-xs text-rose-400 flex items-center gap-1"><AlertTriangle className="w-3 h-3 shrink-0" /> {b.error}</div>
                          )}
                        </div>
                        <div className="flex items-center gap-2">
                          {b.status === 'done' && (
                            <Button size="sm" variant="outline" disabled={busyId === b.id} onClick={() => handleDownload(b)}>
                              {busyId === b.id ? <Loader2 className="w-4 h-4 mr-1 animate-spin" /> : <Download className="w-4 h-4 mr-1" />} Download
                            </Button>
                          )}
                          {b.status !== 'running' && (
                            <Button size="sm" variant="ghost" className="text-rose-400 hover:text-rose-300" disabled={busyId === b.id}
                              onClick={() => setToDelete(b)} title="Delete this backup">
                              <Trash2 className="w-4 h-4" />
                            </Button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
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
};

export default AdminBackupsPage;
