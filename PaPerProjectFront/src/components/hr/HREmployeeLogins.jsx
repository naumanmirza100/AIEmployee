import React, { useState } from 'react';
import { KeyRound, Loader2 } from 'lucide-react';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import hrAgentService from '@/services/hrAgentService';

const NONE = 'none';

/**
 * The logins that belong to one person, on their HR record.
 *
 * A person can have an employee login (My Space) and a dashboard login. The
 * calendar, My work and HR self-service treat the dashboard login as this
 * person only when it is linked here; before this, nothing set that link, so
 * leave approved for someone who works from a dashboard login blocked nothing.
 * An HR admin picks the login; everyone else sees which one it is.
 */
export default function HREmployeeLogins({ employee, logins, onChanged }) {
  const { toast } = useToast();
  const [options, setOptions] = useState(null);
  const [saving, setSaving] = useState(false);

  if (!employee || !logins) return null;
  const linked = logins.dashboard_login;
  const employeeLogin = logins.employee_login;

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

  return (
    <div className="mt-3 pt-3 border-t border-white/[0.06]" data-testid="hr-employee-logins">
      <div className="text-[10px] uppercase tracking-wider text-white/50 mb-1.5 flex items-center gap-1.5">
        <KeyRound className="h-3 w-3" /> Logins
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2 text-sm">
        <div>
          <div className="text-xs text-white/50">Employee login</div>
          <div className="text-white/85" data-testid="hr-employee-login">
            {employeeLogin ? `@${employeeLogin.username}${employeeLogin.is_active ? '' : ' (switched off)'}` : 'None yet'}
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
    </div>
  );
}
