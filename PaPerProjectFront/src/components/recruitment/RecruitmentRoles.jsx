import React, { useEffect, useState } from 'react';
import { Loader2, ShieldCheck } from 'lucide-react';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { useToast } from '@/components/ui/use-toast';
import { getRecruitmentRoles, setRecruitmentRole } from '@/services/recruitmentAgentService';

/** What each role means, as the settings page and the banner say it. */
export const ROLE_TEXT = {
  recruiter: 'Recruiter: everything in Recruitment.',
  hiring_manager: 'Hiring manager: the jobs they posted or are named on, with their candidates and interviews; they decide on them.',
  interviewer: 'Interviewer: the interviews they sit in or run, and those candidates; they give feedback.',
};

const LABELS = { recruiter: 'Recruiter', hiring_manager: 'Hiring manager', interviewer: 'Interviewer' };

/**
 * Who does what in Recruitment (24 Nov 2026). Owners and admins set the roles; they are always recruiters themselves.
 * A login with no role set is a recruiter, as everyone was before.
 */
export default function RecruitmentRoles() {
  const { toast } = useToast();
  const [data, setData] = useState(null);
  const [saving, setSaving] = useState(null);

  const load = () => getRecruitmentRoles().then(setData).catch((e) => toast({ title: 'Could not load roles', description: e.message, variant: 'destructive' }));
  useEffect(() => { load(); }, []);

  const change = async (login, role) => {
    setSaving(login.id);
    try {
      setData(await setRecruitmentRole(login.id, role));
      toast({ title: 'Role saved', description: `${login.name} is now a ${LABELS[role].toLowerCase()} in Recruitment.` });
    } catch (e) {
      toast({ title: 'Not saved', description: e.message, variant: 'destructive' });
    } finally {
      setSaving(null);
    }
  };

  return (
    <Card className="border-white/10 bg-card/90 dark:bg-pure-black/20 backdrop-blur-sm" data-testid="REC-settings-roles-card">
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><ShieldCheck className="h-5 w-5 text-violet-400" /> Roles</CardTitle>
        <CardDescription>
          Who does what in Recruitment. A hiring manager is named on a job from the job's card.
          {data && !data.may_set && ' Only an owner or admin changes roles.'}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <ul className="space-y-1 text-xs text-muted-foreground">
          {Object.values(ROLE_TEXT).map((t) => <li key={t}>{t}</li>)}
        </ul>
        {!data ? (
          <div className="flex justify-center py-6"><Loader2 className="h-5 w-5 animate-spin text-white/40" /></div>
        ) : (
          <div className="divide-y divide-white/5 rounded-lg border border-white/10">
            {data.logins.map((login) => (
              <div key={login.id} className="flex items-center justify-between gap-3 px-3 py-2">
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium text-white/90">{login.name}</div>
                  <div className="truncate text-[11px] text-white/45">{login.email}</div>
                </div>
                {login.fixed || !data.may_set ? (
                  <span className="text-xs text-white/60">{LABELS[login.role]}{login.fixed ? ` (${login.company_role})` : ''}</span>
                ) : (
                  <select className="h-8 rounded-md border border-input bg-background px-2 text-xs text-foreground"
                    value={login.role} disabled={saving === login.id}
                    onChange={(e) => change(login, e.target.value)} aria-label={`${login.name}'s role`}>
                    {Object.entries(LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                  </select>
                )}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/** A line for a login who is not a recruiter: what they can do here. */
export function RecruitmentRoleBanner() {
  const [role, setRole] = useState(null);
  useEffect(() => { getRecruitmentRoles().then((d) => setRole(d.my_role)).catch(() => {}); }, []);
  if (!role || role === 'recruiter') return null;
  return (
    <div className="mb-3 rounded-lg border border-violet-400/30 bg-violet-500/10 px-3 py-2 text-xs text-violet-200" data-testid="REC-role-banner">
      You are a {LABELS[role].toLowerCase()} in Recruitment. {ROLE_TEXT[role].split(': ')[1]}
    </div>
  );
}
