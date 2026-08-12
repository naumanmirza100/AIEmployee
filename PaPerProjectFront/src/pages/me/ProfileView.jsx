import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { useToast } from '@/components/ui/use-toast';
import { User, Mail, Shield, RefreshCw, LogOut, ExternalLink, Loader2 } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import authService from '@/services/authService';

/**
 * ProfileView — /me/profile
 *
 * Read-only account rows, one interactive action (refresh from server),
 * an HR-content pointer, and logout. Editable fields (avatar, phone,
 * timezone, notification preferences, password) will land when the
 * corresponding backend endpoints are exposed (see
 * USER_DASHBOARD_REDESIGN.md, Chunk E follow-up).
 */
export default function ProfileView() {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { user, logout, updateUser } = useAuth();

  const [refreshing, setRefreshing] = useState(false);

  const refresh = async () => {
    setRefreshing(true);
    try {
      const fresh = await authService.getCurrentUser();
      if (fresh) {
        updateUser(fresh);
        toast({ title: 'Profile refreshed' });
      } else {
        toast({ title: 'Session expired', description: 'Please log in again.', variant: 'destructive' });
        navigate('/login');
      }
    } catch (err) {
      toast({ title: 'Could not refresh', description: err.message, variant: 'destructive' });
    } finally {
      setRefreshing(false);
    }
  };

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  const rows = [
    { label: 'Name', icon: User, value: user?.fullName || user?.username || '—' },
    { label: 'Email', icon: Mail, value: user?.email || '—' },
    { label: 'Role', icon: Shield, value: prettyRole(user?.role || user?.userType) },
  ];

  return (
    <div className="max-w-4xl mx-auto space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 text-white">
          <User className="h-6 w-6 text-violet-300" />
          <h2 className="text-2xl font-bold">My Profile</h2>
        </div>
        <Button variant="outline" size="sm" onClick={refresh} disabled={refreshing}
          className="border-white/15 text-white/70 hover:bg-white/[0.06] hover:text-white">
          {refreshing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
          <span className="ml-1.5">Refresh</span>
        </Button>
      </div>

      <Card className="bg-white/[0.03] border-white/[0.08]">
        <CardHeader>
          <CardTitle className="text-white text-base">Account</CardTitle>
          <CardDescription className="text-white/50">
            Basic account info. Editing (avatar, phone, timezone,
            notification preferences, password) is coming — the backend
            endpoints are next.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <dl className="divide-y divide-white/5">
            {rows.map((r) => (
              <div key={r.label} className="flex items-center justify-between py-3">
                <dt className="text-xs text-white/50 flex items-center gap-2">
                  <r.icon className="h-3.5 w-3.5" /> {r.label}
                </dt>
                <dd className="text-sm text-white">{r.value}</dd>
              </div>
            ))}
          </dl>
        </CardContent>
      </Card>

      <Card className="bg-white/[0.03] border-white/[0.08]">
        <CardHeader>
          <CardTitle className="text-white text-base">HR self-service</CardTitle>
          <CardDescription className="text-white/50">
            If your company has the HR module, you can view leave balances,
            documents, goals, and reviews here.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Link to="/hr/me">
            <Button variant="outline" size="sm" className="border-white/15 text-white/70 hover:bg-white/[0.06] hover:text-white">
              Open HR self-service <ExternalLink className="h-3.5 w-3.5 ml-1.5" />
            </Button>
          </Link>
          <p className="text-[10px] text-white/40 mt-2">
            Requires a company_user account. Backend gating is being unified — see
            USER_DASHBOARD_REDESIGN.md, Chunk F.
          </p>
        </CardContent>
      </Card>

      <Card className="bg-white/[0.03] border-white/[0.08]">
        <CardHeader>
          <CardTitle className="text-white text-base">Session</CardTitle>
        </CardHeader>
        <CardContent>
          <Button variant="outline" size="sm" onClick={handleLogout}
            className="border-red-500/40 text-red-300 hover:bg-red-500/10 hover:text-red-200">
            <LogOut className="h-3.5 w-3.5 mr-1.5" /> Log out
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

function prettyRole(role) {
  if (!role) return 'Employee';
  return role
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(' ');
}
