import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import pmAgentService from '@/services/pmAgentService';
import { companyApi } from '@/services/companyAuthService';
import { Loader2, Bell, AlertTriangle, AlertCircle, Info, CheckCircle, RefreshCw, Eye } from 'lucide-react';

const severityConfig = {
  critical: { icon: AlertCircle, color: 'text-red-400', bg: 'bg-red-900/30 border-red-700', label: 'Critical' },
  warning: { icon: AlertTriangle, color: 'text-yellow-400', bg: 'bg-yellow-900/30 border-yellow-700', label: 'Warning' },
  info: { icon: Info, color: 'text-blue-400', bg: 'bg-blue-900/30 border-blue-700', label: 'Info' },
};

export default function SmartNotifications() {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [projects, setProjects] = useState([]);
  const [selectedProject, setSelectedProject] = useState(null);

  useEffect(() => {
    fetchProjects();
    fetchNotifications();
  }, []);

  const fetchProjects = async () => {
    try {
      const res = await companyApi.get('/company/projects');
      const data = res?.data?.data || res?.data?.results || res?.data || [];
      setProjects(Array.isArray(data) ? data : []);
    } catch (e) { console.error(e); }
  };

  const fetchNotifications = async () => {
    setLoading(true);
    try {
      const res = await pmAgentService.listNotifications(false, 100);
      const data = res?.data?.data || {};
      setNotifications(data.notifications || []);
      setUnreadCount(data.unread_count || 0);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const scanForIssues = async () => {
    setScanning(true);
    try {
      const res = await pmAgentService.scanNotifications(selectedProject);
      const data = res?.data?.data || {};
      toast({
        title: 'Scan Complete',
        description: `Found ${data.total || 0} issue(s) across ${data.projects_scanned || 0} project(s).`,
      });
      fetchNotifications();
    } catch (e) {
      toast({ title: 'Error', description: e.message, variant: 'destructive' });
    } finally {
      setScanning(false);
    }
  };

  const markAllRead = async () => {
    try {
      await pmAgentService.markNotificationsRead([], true);
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
      setUnreadCount(0);
    } catch (e) { console.error(e); }
  };

  return (
    <div className="space-y-6">
      {/* Controls */}
      <Card className="bg-gray-900/50 border-gray-700">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-lg text-violet-300 flex items-center gap-2">
              <Bell className="w-5 h-5" /> Smart Notifications
              {unreadCount > 0 && (
                <span className="bg-red-500 text-white text-xs rounded-full px-2 py-0.5">{unreadCount}</span>
              )}
            </CardTitle>
            {unreadCount > 0 && (
              <Button onClick={markAllRead} variant="ghost" size="sm" className="text-xs text-gray-400 hover:text-white">
                <Eye className="w-3 h-3 mr-1" /> Mark all read
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
            <Select value={selectedProject || 'all'} onValueChange={(v) => setSelectedProject(v === 'all' ? null : v)}>
              <SelectTrigger className="flex-1 h-10 bg-gray-800 border-gray-600 text-white">
                <SelectValue placeholder="All Projects" />
              </SelectTrigger>
              <SelectContent className="bg-gray-800 border-gray-600 z-50">
                <SelectItem value="all">All Projects</SelectItem>
                {projects.map((p) => (
                  <SelectItem key={p.id} value={String(p.id)}>{p.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button onClick={scanForIssues} disabled={scanning} className="bg-violet-600 hover:bg-violet-700">
              {scanning ? <><Loader2 className="w-4 h-4 animate-spin mr-2" /> Scanning...</> : <><RefreshCw className="w-4 h-4 mr-2" /> Scan for Issues</>}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-violet-400" />
        </div>
      )}

      {/* Empty State */}
      {!loading && notifications.length === 0 && (
        <div className="flex flex-col items-center justify-center py-20 text-gray-500">
          <CheckCircle className="w-12 h-12 mb-3 text-green-600" />
          <p className="text-sm">No notifications. Click Scan to check for issues.</p>
        </div>
      )}

      {/* Notification Cards */}
      {!loading && notifications.length > 0 && (
        <div className="space-y-3">
          {notifications.map((notif) => {
            const config = severityConfig[notif.severity] || severityConfig.info;
            const Icon = config.icon;
            return (
              <div
                key={notif.id}
                className={`rounded-lg border p-4 ${config.bg} ${!notif.is_read ? 'ring-1 ring-violet-500/30' : 'opacity-75'}`}
              >
                <div className="flex items-start gap-3">
                  <Icon className={`w-5 h-5 mt-0.5 shrink-0 ${config.color}`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className={`text-xs font-medium ${config.color}`}>{config.label}</span>
                      {notif.project_name && (
                        <span className="text-xs text-gray-500">• {notif.project_name}</span>
                      )}
                      <span className="text-xs text-gray-600 ml-auto">
                        {new Date(notif.created_at).toLocaleDateString()}
                      </span>
                    </div>
                    <h4 className="text-sm font-medium text-white mt-1">{notif.title}</h4>
                    <p className="text-xs text-gray-400 mt-1">{notif.message}</p>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
