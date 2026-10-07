import React, { useState } from 'react';
import { KeyRound, Loader2, UserPlus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import hrAgentService from '@/services/hrAgentService';
import { createUser } from '@/services/companyUserManagementService';

const NONE = 'none';
const ROLES = [
  ['team_member', 'Team Member'], ['project_manager', 'Project Manager'], ['developer', 'Developer'],
  ['designer', 'Designer'], ['internee', 'Internee'], ['viewer', 'Viewer'],
];

/**
 * The logins that belong to one person, on their HR record.
 *
 * A person can have an employee login (My Space) and a dashboard login.
 *
 *  - The calendar, My work and HR self-service treat the dashboard login as
 *    this person only when it is linked here. Nothing used to set that link,
 *    so leave approved for someone who works from a dashboard login blocked
 *    nothing. An HR admin picks the login; everyone else sees which it is.
 *  - "Create login" makes the employee login for this record. Made from the
 *    Users tab at a different address from the record's, it became a second
 *    HR record for the same person and started their onboarding again.
 */
export default function HREmployeeLogins({ employee, logins, onChanged, onLoginCreated }) {
  const { toast } = useToast();
  const [options, setOptions] = useState(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState(null);     // the "Create login" form, when open

  if (!employee || !logins) return null;
  const linked = logins.dashboard_login;
  const employeeLogin = logins.employee_login;
  const canCreate = logins.can_manage && !employeeLogin && employee.employment_status !== 'offboarded';

  // The list is only needed once the picker is opened.
  const loadOptions = async (open) => {
    if (!open || options) return;
    try {
      const res = await hrAgentService.listHRDashboardLogins();
      setOptions(res?.data || []);
    } catch (error) {
      setOptions([]);
      toast({ title: 'Could not load the logins', description: error?.data?.message || error?.message, variant: 'destructive' });
    }
  };

  const choose = async (value) => {
    setSaving(true);
    try {
      const res = await hrAgentService.setHREmployeeDashboardLogin(employee.id, value === NONE ? null : Number(value));
      onChanged?.(res?.data);
      setOptions(null);     // who is linked to what has changed
      if (res?.warning) {
        toast({ title: 'Linked, with one thing to know', description: res.warning });
      } else {
        toast({ title: value === NONE ? 'Dashboard login unlinked' : 'Dashboard login linked' });
      }
    } catch (error) {
      toast({ title: 'Not changed', description: error?.data?.message || error?.message, variant: 'destructive' });
    } finally {
      setSaving(false);
    }
  };

  const createLogin = async () => {
    setForm((f) => ({ ...f, saving: true }));
    try {
      await createUser({
        employee_id: employee.id, email: form.email.trim(), password: form.password, role: form.role,
      });
      toast({
        title: 'Login created',
        description: `${employee.full_name} signs in with ${form.email.trim()}. Pass the password on to them.`,
      });
      setForm(null);
      onLoginCreated?.();
    } catch (error) {
      toast({ title: 'Login not created', description: error?.data?.message || error?.message, variant: 'destructive' });
      setForm((f) => (f ? { ...f, saving: false } : f));
    }
  };

  return (
    <div className="mt-3 pt-3 border-t border-white/[0.06]" data-testid="hr-employee-logins">
      <div className="text-[10px] uppercase tracking-wider text-white/50 mb-1.5 flex items-center gap-1.5">
        <KeyRound className="h-3 w-3" /> Logins
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2 text-sm">
        <div>
          <div className="text-xs text-white/50">Employee login</div>
          <div className="flex items-center gap-2">
            <span className="text-white/85" data-testid="hr-employee-login">
              {employeeLogin ? `@${employeeLogin.username}${employeeLogin.is_active ? '' : ' (switched off)'}` : 'None yet'}
            </span>
            {canCreate && (
              <Button size="sm" variant="outline" className="h-7 px-2 text-xs"
                onClick={() => setForm({ email: employee.work_email || '', password: '', role: 'team_member', saving: false })}>
                <UserPlus className="h-3 w-3 mr-1" /> Create login
              </Button>
            )}
          </div>
        </div>
        <div>
          <div className="text-xs text-white/50">Dashboard login</div>
          {logins.can_manage ? (
            <div className="flex items-center gap-2">
              <Select
                value={linked ? String(linked.id) : NONE}
                onValueChange={choose}
                onOpenChange={loadOptions}
                disabled={saving}
              >
                <SelectTrigger className="h-8 text-sm" aria-label="Dashboard login of this employee">
                  <SelectValue>
                    {linked ? `${linked.full_name} (${linked.email})` : 'Not linked'}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE}>Not linked</SelectItem>
                  {linked && !(options || []).some((o) => o.id === linked.id) && (
                    <SelectItem value={String(linked.id)}>{linked.full_name} ({linked.email})</SelectItem>
                  )}
                  {(options || []).map((o) => {
                    // A login belongs to one record: one linked elsewhere cannot be chosen here.
                    const elsewhere = o.linked_to && o.id !== linked?.id;
                    return (
                      <SelectItem key={o.id} value={String(o.id)} disabled={!!elsewhere}>
                        {o.full_name} ({o.email}){elsewhere ? `, linked to ${o.linked_to}` : ''}
                      </SelectItem>
                    );
                  })}
                </SelectContent>
              </Select>
              {saving && <Loader2 className="h-4 w-4 animate-spin text-white/40 shrink-0" />}
            </div>
          ) : (
            <div className="text-white/85" data-testid="hr-dashboard-login">
              {linked ? `${linked.full_name} (${linked.email})` : 'Not linked'}
            </div>
          )}
        </div>
      </div>
      {linked && !logins.on_calendar && (
        <p className="mt-2 text-xs text-amber-300/90" data-testid="hr-logins-note">
          No employee login yet, so the calendar cannot place this person: their leave will not block bookings
          until they have one.
        </p>
      )}

      <Dialog open={!!form} onOpenChange={(open) => { if (!open) setForm(null); }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Create a login for {employee.full_name}</DialogTitle>
            <DialogDescription>
              They sign in on the employee sign-in page. This record keeps everything it holds and takes the
              login&apos;s address as its work email.
            </DialogDescription>
          </DialogHeader>
          {form && (
            <div className="space-y-3">
              <div>
                <Label htmlFor="new-login-email">Work email</Label>
                <Input id="new-login-email" type="email" value={form.email}
                  onChange={(ev) => setForm((f) => ({ ...f, email: ev.target.value }))} />
                <p className="mt-1 text-xs text-muted-foreground">
                  Use their company address. The address they applied from stays on the record as their personal email.
                </p>
              </div>
              <div>
                <Label htmlFor="new-login-password">Password</Label>
                <Input id="new-login-password" type="password" autoComplete="new-password" value={form.password}
                  onChange={(ev) => setForm((f) => ({ ...f, password: ev.target.value }))} />
                <p className="mt-1 text-xs text-muted-foreground">
                  At least 8 characters, with an upper-case letter, a lower-case letter, a digit and a symbol.
                </p>
              </div>
              <div>
                <Label>Role</Label>
                <Select value={form.role} onValueChange={(role) => setForm((f) => ({ ...f, role }))}>
                  <SelectTrigger aria-label="Role of the new login"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {ROLES.map(([value, label]) => <SelectItem key={value} value={value}>{label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setForm(null)} disabled={form?.saving}>Cancel</Button>
            <Button onClick={createLogin} disabled={!form?.email?.trim() || !form?.password || form?.saving}>
              {form?.saving && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
              Create login
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
