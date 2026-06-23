import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import SearchableSelect from '@/components/ui/searchable-select';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { useToast } from '@/components/ui/use-toast';
import {
  Loader2, FileText, Calendar, ChevronLeft, ChevronRight,
  Mail, Briefcase, Percent, Printer, MapPin, DollarSign,
  GraduationCap, Building2, Link2, Phone, ExternalLink,
  User, Star, CheckCircle2, Clock,
} from 'lucide-react';
import { getCVRecords, getJobDescriptions, bulkUpdateCVRecords } from '@/services/recruitmentAgentService';
import QualificationReasoning from './QualificationReasoning';

const PAGE_SIZES = [10, 25, 50];

export const getDecisionBadge = (decision) => {
  switch (decision) {
    case 'INTERVIEW': return <Badge className="bg-green-500">INTERVIEW</Badge>;
    case 'HOLD': return <Badge className="bg-yellow-500">HOLD</Badge>;
    case 'REJECT': return <Badge className="bg-red-500">REJECT</Badge>;
    default: return <Badge variant="outline">{decision || 'N/A'}</Badge>;
  }
};

const CVRecords = () => {
  const { toast } = useToast();
  const navigate = useNavigate();
  const [records, setRecords] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [jobFilter, setJobFilter] = useState('');
  const [decisionFilter, setDecisionFilter] = useState('');
  const [jobs, setJobs] = useState([]);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [bulkUpdating, setBulkUpdating] = useState(false);

  useEffect(() => {
    fetchJobs();
  }, []);

  useEffect(() => {
    fetchRecords();
  }, [jobFilter, decisionFilter, page, pageSize]);

  useEffect(() => {
    setPage(1);
  }, [jobFilter, decisionFilter, pageSize]);

  const fetchJobs = async () => {
    try {
      const response = await getJobDescriptions();
      if (response.status === 'success') setJobs(response.data || []);
    } catch (error) {
      console.error('Error fetching jobs:', error);
    }
  };

  const fetchRecords = async () => {
    try {
      setLoading(true);
      const filters = { page, page_size: pageSize };
      if (jobFilter) filters.job_id = jobFilter;
      if (decisionFilter) filters.decision = decisionFilter;
      const response = await getCVRecords(filters);
      if (response.status === 'success') {
        setRecords(response.data || []);
        setTotal(response.total ?? 0);
      }
    } catch (error) {
      console.error('Error fetching CV records:', error);
      toast({ title: 'Error', description: 'Failed to load CV records', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };


  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const canPrev = page > 1;
  const canNext = page < totalPages;
  const rangeStart = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const rangeEnd = Math.min(page * pageSize, total);

  const allOnPageSelected = records.length > 0 && records.every((r) => selectedIds.has(r.id));
  const someOnPageSelected = records.some((r) => selectedIds.has(r.id));

  const handleSelectAll = (checked) => {
    if (checked) {
      setSelectedIds((prev) => new Set([...prev, ...records.map((r) => r.id)]));
    } else {
      const pageIds = new Set(records.map((r) => r.id));
      setSelectedIds((prev) => new Set([...prev].filter((id) => !pageIds.has(id))));
    }
  };

  const handleSelectRow = (recordId, checked) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (checked) next.add(recordId);
      else next.delete(recordId);
      return next;
    });
  };

  const handleRowClick = (record) => {
    navigate(`/recruitment/candidates/${record.id}`);
  };

  const handleBulkChangeDecision = async (decision) => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;
    try {
      setBulkUpdating(true);
      const response = await bulkUpdateCVRecords(ids, decision);
      if (response.status === 'success') {
        toast({ title: 'Updated', description: response.message || `Updated ${response.updated_count} candidate(s) to ${decision}` });
        setSelectedIds(new Set());
        fetchRecords();
      } else {
        throw new Error(response.message || 'Bulk update failed');
      }
    } catch (error) {
      toast({ title: 'Error', description: error?.message || 'Failed to update selected candidates', variant: 'destructive' });
    } finally {
      setBulkUpdating(false);
    }
  };

  const handlePrint = () => {
    const selectedJob = jobs.find(j => j.id.toString() === jobFilter);
    const decisionLabel = { INTERVIEW: 'Interview', HOLD: 'Hold', REJECT: 'Reject' }[decisionFilter] || 'All';
    const rows = records.map((record) => {
      const p = record.parsed || {};
      const decision = record.qualification_decision || '—';
      const score = (record.qualification_confidence ?? record.role_fit_score) != null ? `${Math.round(record.qualification_confidence ?? record.role_fit_score)}%` : '—';
      const displayN = record.application_name || p.name || record.file_name || '—';
      const displayE = record.application_email || p.email || '—';
      const displayPh = record.application_phone || p.phone || '—';
      return `<tr><td>${displayN}</td><td>${displayE}</td><td>${displayPh}</td><td>${record.job_description_title || '—'}</td><td>${score}</td><td>${decision}</td><td>${record.created_at ? new Date(record.created_at).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'}</td></tr>`;
    }).join('');
    const html = `<!DOCTYPE html><html><head><meta charset="utf-8"/><title>Candidates Report</title><style>body{font-family:Arial,sans-serif;font-size:12px;color:#111;margin:24px}h1{font-size:20px;margin-bottom:4px}.meta{color:#555;font-size:11px;margin-bottom:16px}table{width:100%;border-collapse:collapse}th{background:#1a0a2e;color:#fff;padding:8px 10px;text-align:left;font-size:11px}td{padding:7px 10px;border-bottom:1px solid #e5e7eb;vertical-align:top}tr:nth-child(even) td{background:#f9f7ff}</style></head><body><h1>Candidates Report</h1><div class="meta">Job: ${selectedJob?.title || 'All Jobs'} | Decision: ${decisionLabel} | Total: ${total} | Printed: ${new Date().toLocaleString()}</div><table><thead><tr><th>Name</th><th>Email</th><th>Phone</th><th>Job</th><th>Score</th><th>Decision</th><th>Date</th></tr></thead><tbody>${rows}</tbody></table></body></html>`;
    const win = window.open('', '_blank');
    win.document.write(html);
    win.document.close();
    win.focus();
    win.print();
  };

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-4 w-full">
      {/* Header and Filters */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h2 className="text-xl sm:text-2xl py-3 sm:py-5 font-bold text-white">Candidates</h2>
          <p className="text-xs sm:text-sm text-white/60">
            View and manage processed candidate CVs. Select a job to filter, click a row for full details.
          </p>
        </div>
        <div className="flex flex-wrap gap-2 justify-end">
          <SearchableSelect
            value={jobFilter || 'all'}
            onValueChange={(value) => setJobFilter(value === 'all' ? '' : value)}
            options={[{ value: 'all', label: 'All Jobs' }, ...jobs.map(j => ({ value: j.id.toString(), label: j.title }))]}
            placeholder="All Jobs"
            triggerClassName="w-[180px]"
          />
          <SearchableSelect
            value={decisionFilter || 'all'}
            onValueChange={(value) => setDecisionFilter(value === 'all' ? '' : value)}
            options={[
              { value: 'all', label: 'All Decisions' },
              { value: 'INTERVIEW', label: 'Interview' },
              { value: 'HOLD', label: 'Hold' },
              { value: 'REJECT', label: 'Reject' },
            ]}
            placeholder="All Decisions"
            triggerClassName="w-[140px]"
          />
          <Button
            variant="outline"
            size="sm"
            onClick={handlePrint}
            className="h-10 border-white/20 text-white/80 hover:bg-white/10 gap-2"
          >
            <Printer className="h-4 w-4" />
            Print
          </Button>
        </div>
      </div>

      {/* Bulk Actions Bar */}
      {selectedIds.size > 0 && (
        <Card className="border-primary/50 bg-primary/5">
          <CardContent className="py-3 px-3 sm:px-6">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <span className="text-xs sm:text-sm font-medium">{selectedIds.size} selected</span>
              <div className="grid grid-cols-2 sm:flex sm:flex-wrap items-center gap-2">
                <Button size="sm" variant="default" className="bg-green-600 hover:bg-green-700 text-xs sm:text-sm" disabled={bulkUpdating} onClick={() => handleBulkChangeDecision('INTERVIEW')}>
                  {bulkUpdating ? <Loader2 className="h-3 w-3 sm:h-4 sm:w-4 animate-spin mr-1" /> : null}
                  Interview
                </Button>
                <Button size="sm" variant="secondary" className="text-xs sm:text-sm" disabled={bulkUpdating} onClick={() => handleBulkChangeDecision('HOLD')}>Hold</Button>
                <Button size="sm" variant="secondary" className="text-red-600 hover:text-red-700 text-xs sm:text-sm" disabled={bulkUpdating} onClick={() => handleBulkChangeDecision('REJECT')}>Reject</Button>
                <Button size="sm" variant="ghost" className="text-xs sm:text-sm" onClick={() => setSelectedIds(new Set())}>Clear</Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {total === 0 ? (
        <Card className="border-white/10 bg-black/20 backdrop-blur-sm">
          <CardContent className="py-8 sm:py-12 text-center">
            <FileText className="h-10 w-10 sm:h-12 sm:w-12 mx-auto text-white/40 mb-4" />
            <p className="text-base sm:text-lg font-medium mb-2 text-white">No candidates yet</p>
            <p className="text-xs sm:text-sm text-white/60 px-4">
              {jobFilter || decisionFilter ? 'No records match the selected filters.' : 'Process CVs to see candidate records here'}
            </p>
          </CardContent>
        </Card>
      ) : (
        <>
          {/* Mobile Card View */}
          <div className="block md:hidden space-y-3">
            <div className="flex items-center gap-2 px-1">
              <Checkbox checked={allOnPageSelected ? true : someOnPageSelected ? 'indeterminate' : false} onCheckedChange={handleSelectAll} aria-label="Select all on page" />
              <span className="text-sm text-muted-foreground">Select all</span>
            </div>
            {records.map((record) => {
              const parsed = record.parsed || {};
              const displayName = record.application_name || parsed.name || record.file_name || '—';
              const displayEmail = record.application_email || parsed.email || '';
              const isSelected = selectedIds.has(record.id);
              return (
                <Card key={record.id} className={`cursor-pointer transition-colors border-white/10 backdrop-blur-sm ${isSelected ? 'border-primary bg-primary/10' : 'bg-black/20 hover:bg-black/30'}`} onClick={() => handleRowClick(record)}>
                  <CardContent className="p-3 sm:p-4">
                    <div className="flex items-start gap-3">
                      <div onClick={(e) => e.stopPropagation()} className="pt-1">
                        <Checkbox checked={isSelected} onCheckedChange={(checked) => handleSelectRow(record.id, !!checked)} aria-label={`Select ${displayName}`} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-start justify-between gap-2 mb-2">
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2 flex-wrap">
                              {record.rank != null && <Badge variant="outline" className="text-xs shrink-0">#{record.rank}</Badge>}
                              <h3 className="font-semibold text-sm truncate">{displayName}</h3>
                            </div>
                          </div>
                          <div className="shrink-0">{getDecisionBadge(record.qualification_decision)}</div>
                        </div>
                        <div className="space-y-1.5 text-xs text-muted-foreground">
                          {displayEmail && <div className="flex items-center gap-1.5"><Mail className="h-3 w-3 shrink-0" /><span className="truncate">{displayEmail}</span></div>}
                          {record.job_description_title && <div className="flex items-center gap-1.5"><Briefcase className="h-3 w-3 shrink-0" /><span className="truncate">{record.job_description_title}</span></div>}
                          <div className="flex items-center justify-between pt-1">
                            <div className="flex items-center gap-1.5"><Calendar className="h-3 w-3 shrink-0" /><span>{record.created_at ? new Date(record.created_at).toLocaleDateString() : '—'}</span></div>
                            {record.qualification_confidence != null && <div className="flex items-center gap-1"><Percent className="h-3 w-3" /><span className="font-medium">{record.qualification_confidence}%</span></div>}
                          </div>
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>

          {/* Desktop Table View */}
          <Card className="hidden md:block border-white/10 bg-black/20 backdrop-blur-sm">
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-12 pr-0">
                      <Checkbox checked={allOnPageSelected ? true : someOnPageSelected ? 'indeterminate' : false} onCheckedChange={handleSelectAll} aria-label="Select all on page" className="translate-y-0.5" />
                    </TableHead>
                    <TableHead className="w-14">#</TableHead>
                    <TableHead>Name</TableHead>
                    <TableHead>Email</TableHead>
                    <TableHead>Job</TableHead>
                    <TableHead className="w-28">Decision</TableHead>
                    <TableHead className="text-right w-24">Conf. %</TableHead>
                    <TableHead className="w-28">Date</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {records.map((record) => {
                    const parsed = record.parsed || {};
                    const displayName = record.application_name || parsed.name || record.file_name || '—';
                    const displayEmail = record.application_email || parsed.email || '—';
                    const isSelected = selectedIds.has(record.id);
                    return (
                      <TableRow key={record.id} className="cursor-pointer hover:bg-muted/70 data-[state=selected]:bg-muted/70" data-state={isSelected ? 'selected' : undefined} onClick={() => handleRowClick(record)}>
                        <TableCell className="w-12 pr-0" onClick={(e) => e.stopPropagation()}>
                          <Checkbox checked={isSelected} onCheckedChange={(checked) => handleSelectRow(record.id, !!checked)} aria-label={`Select ${displayName}`} className="translate-y-0.5" />
                        </TableCell>
                        <TableCell className="font-medium">{record.rank != null ? record.rank : '—'}</TableCell>
                        <TableCell>{displayName}</TableCell>
                        <TableCell className="text-muted-foreground">{displayEmail}</TableCell>
                        <TableCell className="max-w-[180px] truncate" title={record.job_description_title}>{record.job_description_title || '—'}</TableCell>
                        <TableCell>{getDecisionBadge(record.qualification_decision)}</TableCell>
                        <TableCell className="text-right">{record.qualification_confidence != null ? `${record.qualification_confidence}%` : '—'}</TableCell>
                        <TableCell className="text-muted-foreground text-xs">{record.created_at ? new Date(record.created_at).toLocaleDateString() : '—'}</TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          </Card>

          {/* Pagination */}
          <Card className="md:border-t-0 md:rounded-t-none border-white/10 bg-black/20 backdrop-blur-sm">
            <CardContent className="py-3 px-3 sm:px-4">
              <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
                <div className="flex items-center gap-2 sm:gap-4 w-full sm:w-auto justify-between sm:justify-start">
                  <span className="text-xs sm:text-sm text-muted-foreground whitespace-nowrap">{rangeStart}–{rangeEnd} of {total}</span>
                  <Select value={String(pageSize)} onValueChange={(v) => { setPageSize(Number(v)); setPage(1); }}>
                    <SelectTrigger className="w-[90px] sm:w-[100px] h-8 sm:h-9 text-xs sm:text-sm border-white/20"><SelectValue /></SelectTrigger>
                    <SelectContent>{PAGE_SIZES.map((size) => <SelectItem key={size} value={String(size)}>{size} / page</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                <div className="flex items-center gap-1 sm:gap-2 w-full sm:w-auto justify-center">
                  <Button variant="outline" size="sm" className="h-8 sm:h-9 px-2 sm:px-3" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={!canPrev}>
                    <ChevronLeft className="h-4 w-4" /><span className="hidden sm:inline ml-1">Previous</span>
                  </Button>
                  <span className="text-xs sm:text-sm text-muted-foreground px-2 whitespace-nowrap">{page} / {totalPages}</span>
                  <Button variant="outline" size="sm" className="h-8 sm:h-9 px-2 sm:px-3" onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={!canNext}>
                    <span className="hidden sm:inline mr-1">Next</span><ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </>
      )}

    </div>
  );
};

/* ───────────────────────────── Full Profile ───────────────────────────── */

export function CandidateProfile({ detail, getDecisionBadge }) {
  const [activeTab, setActiveTab] = useState('overview');
  const parsed = detail.parsed || {};
  const qualified = detail.qualified || {};
  const insights = detail.insights || {};
  const application = detail.application || null;
  const interviews = detail.interviews || [];
  const summary = insights.summary || insights.summary_text || null;
  const skills = parsed.skills || [];
  const experience = parsed.experience || parsed.work_experience || [];
  const education = parsed.education || [];

  // Prefer real application data over AI-parsed text
  const displayName = application
    ? `${application.first_name} ${application.last_name}`.trim()
    : (parsed.name || detail.file_name || 'Unknown Candidate');
  const displayEmail = application?.email || parsed.email || '';
  const displayPhone = application?.phone || parsed.phone || '';

  const tabs = [
    { id: 'overview', label: 'Overview' },
    { id: 'application', label: application ? 'Application ✓' : 'Application' },
    { id: 'cv', label: 'CV Details' },
    { id: 'interviews', label: `Interviews (${interviews.length})` },
  ];

  return (
    <div className="space-y-0">
      {/* Profile Header */}
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 pb-4 border-b border-white/10">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap mb-1.5">
            {detail.rank != null && <Badge variant="outline" className="font-bold text-xs">Rank #{detail.rank}</Badge>}
            {getDecisionBadge(detail.qualification_decision)}
            {detail.qualification_priority && <Badge variant="secondary" className="text-xs">{detail.qualification_priority}</Badge>}
          </div>
          <h2 className="text-lg sm:text-xl font-bold text-white">{displayName}</h2>
          <div className="mt-1 space-y-0.5 text-sm text-white/60">
            {displayEmail && <div className="flex items-center gap-1.5"><Mail className="h-3.5 w-3.5 shrink-0" />{displayEmail}</div>}
            {displayPhone && <div className="flex items-center gap-1.5"><Phone className="h-3.5 w-3.5 shrink-0" />{displayPhone}</div>}
            {detail.job_description_title && <div className="flex items-center gap-1.5 text-violet-300"><Briefcase className="h-3.5 w-3.5 shrink-0" />{detail.job_description_title}</div>}
          </div>
        </div>
        <div className="flex items-center gap-5 sm:flex-col sm:items-end sm:gap-0.5 shrink-0">
          {detail.role_fit_score != null && (
            <div className="text-3xl font-bold text-violet-400">{detail.role_fit_score}<span className="text-base text-violet-300/70">%</span></div>
          )}
          {detail.qualification_confidence != null && (
            <div className="text-xs text-white/40">Confidence: {detail.qualification_confidence}%</div>
          )}
          {detail.created_at && (
            <div className="text-xs text-white/30 flex items-center gap-1 mt-1">
              <Clock className="h-3 w-3" />{new Date(detail.created_at).toLocaleDateString()}
            </div>
          )}
        </div>
      </div>

      {/* Tab Bar */}
      <div className="flex gap-1 pt-3 pb-1 overflow-x-auto border-b border-white/10">
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-3 py-1.5 text-xs sm:text-sm rounded-md font-medium whitespace-nowrap transition-colors ${
              activeTab === tab.id
                ? 'bg-violet-600/30 text-violet-300 border border-violet-500/40'
                : 'text-white/50 hover:text-white/80 hover:bg-white/5'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="pt-4 space-y-4">
        {activeTab === 'overview' && <OverviewTab summary={summary} skills={skills} qualified={qualified} />}
        {activeTab === 'application' && <ApplicationTab application={application} />}
        {activeTab === 'cv' && <CVDetailsTab parsed={parsed} experience={experience} education={education} />}
        {activeTab === 'interviews' && <InterviewsHistoryTab interviews={interviews} />}
      </div>
    </div>
  );
}

/* ── Overview Tab ── */
function OverviewTab({ summary, skills, qualified }) {
  return (
    <div className="space-y-4">
      {summary && (
        <Section title="Summary">
          <p className="text-sm text-white/70 leading-relaxed">{summary}</p>
        </Section>
      )}
      {skills.length > 0 && (
        <Section title="Skills">
          <div className="flex flex-wrap gap-1.5">
            {skills.map((skill, i) => (
              <Badge key={i} variant="outline" className="text-xs text-white/70 border-white/20">{skill}</Badge>
            ))}
          </div>
        </Section>
      )}
      {qualified.reasoning && (
        <QualificationReasoning
          reasoning={qualified.reasoning}
          exactMatchedSkills={qualified.exact_matched_skills || []}
          relatedMatchedSkills={qualified.related_matched_skills || []}
          missingSkills={qualified.missing_skills || []}
          inferredSkills={[]}
        />
      )}
      {!summary && skills.length === 0 && !qualified.reasoning && (
        <p className="text-sm text-white/40 py-4 text-center">No overview data available.</p>
      )}
    </div>
  );
}

/* ── Application Tab ── */
function ApplicationTab({ application }) {
  if (!application) {
    return (
      <div className="py-8 text-center">
        <FileText className="h-10 w-10 mx-auto text-white/20 mb-3" />
        <p className="text-sm text-white/40">No application form submission found for this candidate.</p>
        <p className="text-xs text-white/30 mt-1">Candidate was processed via CV upload, not the public form.</p>
      </div>
    );
  }
  return (
    <div className="space-y-4">
      <Section title="Personal Information">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">
          <InfoRow icon={<User className="h-3.5 w-3.5" />} label="Name" value={`${application.first_name} ${application.last_name}`} />
          <InfoRow icon={<Mail className="h-3.5 w-3.5" />} label="Email" value={application.email} />
          <InfoRow icon={<Phone className="h-3.5 w-3.5" />} label="Phone" value={application.phone} />
          {application.current_location && <InfoRow icon={<MapPin className="h-3.5 w-3.5" />} label="Location" value={application.current_location} />}
          {application.salary_expectation && <InfoRow icon={<DollarSign className="h-3.5 w-3.5" />} label="Expected Salary" value={application.salary_expectation} />}
        </div>
      </Section>

      {application.education && (
        <Section title="Education">
          <p className="text-sm text-white/70 whitespace-pre-wrap">{application.education}</p>
        </Section>
      )}

      {(application.previous_company || application.previous_salary) && (
        <Section title="Previous Experience">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">
            {application.previous_company && <InfoRow icon={<Building2 className="h-3.5 w-3.5" />} label="Company" value={application.previous_company} />}
            {application.previous_salary && <InfoRow icon={<DollarSign className="h-3.5 w-3.5" />} label="Previous Salary" value={application.previous_salary} />}
          </div>
        </Section>
      )}

      {(application.linkedin_url || application.github_url || application.other_links) && (
        <Section title="Links">
          <div className="space-y-1.5">
            {application.linkedin_url && (
              <a href={application.linkedin_url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 text-sm text-violet-400 hover:text-violet-300 transition-colors">
                <Link2 className="h-3.5 w-3.5 shrink-0" />LinkedIn<ExternalLink className="h-3 w-3" />
              </a>
            )}
            {application.github_url && (
              <a href={application.github_url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 text-sm text-violet-400 hover:text-violet-300 transition-colors">
                <Link2 className="h-3.5 w-3.5 shrink-0" />GitHub<ExternalLink className="h-3 w-3" />
              </a>
            )}
            {application.other_links && <p className="text-sm text-white/60 whitespace-pre-wrap">{application.other_links}</p>}
          </div>
        </Section>
      )}

      {application.cover_letter && (
        <Section title="Cover Letter">
          <p className="text-sm text-white/70 whitespace-pre-wrap leading-relaxed">{application.cover_letter}</p>
        </Section>
      )}

      <div className="flex items-center justify-between text-xs text-white/30 pt-1 border-t border-white/10">
        <span>Applied: {application.applied_at ? new Date(application.applied_at).toLocaleString() : '—'}</span>
        <Badge variant="outline" className="text-xs capitalize">{application.status}</Badge>
      </div>
    </div>
  );
}

/* ── CV Details Tab ── */
function CVDetailsTab({ parsed, experience, education }) {
  const links = {
    linkedin: parsed.linkedin || parsed.linkedin_url,
    github: parsed.github || parsed.github_url,
    portfolio: parsed.portfolio || parsed.portfolio_url || parsed.website,
  };
  const hasLinks = Object.values(links).some(Boolean);

  return (
    <div className="space-y-4">
      {experience.length > 0 && (
        <Section title="Work Experience">
          <div className="space-y-3">
            {experience.map((exp, i) => (
              <div key={i} className="border border-white/10 rounded-lg p-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-white truncate">{exp.title || exp.position || exp.role || '—'}</p>
                    <p className="text-xs text-violet-300/80">{exp.company || exp.organization || '—'}</p>
                  </div>
                  {(exp.start_date || exp.end_date || exp.duration || exp.period) && (
                    <span className="text-xs text-white/40 shrink-0">{exp.start_date || ''}{exp.start_date && exp.end_date ? ' – ' : ''}{exp.end_date || exp.period || exp.duration || ''}</span>
                  )}
                </div>
                {(exp.description || exp.responsibilities) && (
                  <p className="mt-1.5 text-xs text-white/60 leading-relaxed line-clamp-3">
                    {Array.isArray(exp.responsibilities) ? exp.responsibilities.join(' • ') : (exp.description || exp.responsibilities)}
                  </p>
                )}
              </div>
            ))}
          </div>
        </Section>
      )}

      {education.length > 0 && (
        <Section title="Education">
          <div className="space-y-2">
            {education.map((edu, i) => (
              <div key={i} className="border border-white/10 rounded-lg p-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-white truncate">{edu.degree || edu.qualification || edu.field || '—'}</p>
                    <p className="text-xs text-violet-300/80">{edu.institution || edu.university || edu.school || '—'}</p>
                  </div>
                  {(edu.year || edu.graduation_year || edu.end_year) && (
                    <span className="text-xs text-white/40 shrink-0">{edu.year || edu.graduation_year || edu.end_year}</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </Section>
      )}

      {hasLinks && (
        <Section title="Links">
          <div className="space-y-1.5">
            {links.linkedin && <a href={links.linkedin} target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 text-sm text-violet-400 hover:text-violet-300"><Link2 className="h-3.5 w-3.5" />LinkedIn<ExternalLink className="h-3 w-3" /></a>}
            {links.github && <a href={links.github} target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 text-sm text-violet-400 hover:text-violet-300"><Link2 className="h-3.5 w-3.5" />GitHub<ExternalLink className="h-3 w-3" /></a>}
            {links.portfolio && <a href={links.portfolio} target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 text-sm text-violet-400 hover:text-violet-300"><Link2 className="h-3.5 w-3.5" />Portfolio<ExternalLink className="h-3 w-3" /></a>}
          </div>
        </Section>
      )}

      {experience.length === 0 && education.length === 0 && !hasLinks && (
        <p className="text-sm text-white/40 py-4 text-center">No structured CV details extracted.</p>
      )}
    </div>
  );
}

/* ── Interviews History Tab ── */
function InterviewsHistoryTab({ interviews }) {
  if (interviews.length === 0) {
    return (
      <div className="py-8 text-center">
        <Calendar className="h-10 w-10 mx-auto text-white/20 mb-3" />
        <p className="text-sm text-white/40">No interviews scheduled for this candidate yet.</p>
      </div>
    );
  }

  const statusColors = { PENDING: 'bg-yellow-500', SCHEDULED: 'bg-green-500', COMPLETED: 'bg-blue-500', CANCELLED: 'bg-red-500', RESCHEDULED: 'bg-purple-500' };
  const outcomeColors = { HIRED: 'bg-emerald-600', PASSED: 'bg-teal-500', REJECTED: 'bg-red-600', ONSITE_INTERVIEW: 'bg-indigo-500' };
  const outcomeLabels = { HIRED: 'Hired', PASSED: 'Passed', REJECTED: 'Rejected', ONSITE_INTERVIEW: 'Onsite Interview' };

  return (
    <div className="space-y-3">
      {interviews.map((iv) => (
        <div key={iv.id} className="border border-white/10 rounded-lg p-3 space-y-2">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <div className="flex items-center gap-2 flex-wrap">
              <Badge className={`${statusColors[iv.status] || 'bg-gray-500'} text-xs`}>{iv.status}</Badge>
              {iv.outcome && <Badge className={`${outcomeColors[iv.outcome] || 'bg-gray-500'} text-xs`}>{outcomeLabels[iv.outcome] || iv.outcome}</Badge>}
              <Badge variant="outline" className="text-xs">{iv.interview_type}</Badge>
            </div>
            <span className="text-xs text-white/30">{iv.created_at ? new Date(iv.created_at).toLocaleDateString() : ''}</span>
          </div>
          {iv.scheduled_datetime && (
            <div className="flex items-center gap-1.5 text-xs text-white/60">
              <Clock className="h-3 w-3" />
              {new Date(iv.scheduled_datetime).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}
            </div>
          )}
          {iv.feedback_rating && (
            <div className="flex items-center gap-2 pt-1 border-t border-white/10">
              <div className="flex gap-0.5">
                {[1,2,3,4,5].map(s => (
                  <Star key={s} className={`h-3 w-3 ${s <= iv.feedback_rating ? 'text-amber-400 fill-amber-400' : 'text-white/20'}`} />
                ))}
              </div>
              {iv.feedback_strengths && <p className="text-xs text-white/50 line-clamp-1"><span className="text-green-400">+</span> {iv.feedback_strengths}</p>}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

/* ── Shared helpers ── */
function Section({ title, children }) {
  return (
    <div>
      <h4 className="text-xs font-semibold text-violet-400 uppercase tracking-wider mb-2">{title}</h4>
      {children}
    </div>
  );
}

function InfoRow({ icon, label, value }) {
  if (!value) return null;
  return (
    <div className="flex items-start gap-1.5 text-sm">
      <span className="text-white/30 mt-0.5 shrink-0">{icon}</span>
      <span className="text-white/40 shrink-0">{label}:</span>
      <span className="text-white/80 break-all">{value}</span>
    </div>
  );
}

/* ── Legacy fallback (data already in hand, no fetch needed) ── */
function LegacyCandidateDetail({ record, getDecisionBadge }) {
  const parsed = record.parsed || {};
  const qualified = record.qualified || {};
  const app = record.application || null;
  const summary = record.insights?.summary || record.summary?.summary;
  const skills = parsed.skills || [];
  const displayName = app
    ? `${app.first_name} ${app.last_name}`.trim()
    : (parsed.name || record.file_name || 'Unknown');
  const displayEmail = record.application_email || app?.email || parsed.email || '';
  const displayPhone = record.application_phone || app?.phone || parsed.phone || '';
  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 sm:gap-4 pb-4 border-b">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            {record.rank != null && <Badge variant="outline" className="font-bold text-xs">Rank #{record.rank}</Badge>}
            {getDecisionBadge(record.qualification_decision)}
            {record.qualification_priority && <Badge variant="secondary" className="text-xs">{record.qualification_priority}</Badge>}
          </div>
          <h3 className="text-base sm:text-lg font-semibold break-words">{displayName}</h3>
          <div className="text-xs sm:text-sm text-muted-foreground mt-1 space-y-0.5">
            {displayEmail && <p className="break-all">{displayEmail}</p>}
            {displayPhone && <p>{displayPhone}</p>}
            {record.job_description_title && <p className="mt-1">Job: {record.job_description_title}</p>}
          </div>
        </div>
        <div className="flex sm:flex-col items-center sm:items-end gap-2 sm:gap-0 sm:text-right shrink-0">
          {record.role_fit_score != null && <div className="text-xl sm:text-2xl font-bold text-primary">{record.role_fit_score}%</div>}
          <div className="text-xs text-muted-foreground">Fit Score</div>
          {record.qualification_confidence != null && <div className="text-xs sm:text-sm mt-1">Confidence: {record.qualification_confidence}%</div>}
        </div>
      </div>
      {summary && <div><h4 className="font-semibold text-xs sm:text-sm mb-1">Summary</h4><p className="text-xs sm:text-sm text-muted-foreground">{summary}</p></div>}
      {qualified.reasoning && <QualificationReasoning reasoning={qualified.reasoning} exactMatchedSkills={qualified.exact_matched_skills || []} relatedMatchedSkills={qualified.related_matched_skills || []} missingSkills={qualified.missing_skills || []} inferredSkills={[]} />}
      {skills.length > 0 && (
        <div><h4 className="font-semibold text-xs sm:text-sm mb-1">Skills</h4>
          <div className="flex flex-wrap gap-1">{skills.map((skill, idx) => <Badge key={idx} variant="outline" className="text-[10px] sm:text-xs">{skill}</Badge>)}</div>
        </div>
      )}
    </div>
  );
}

export default CVRecords;
