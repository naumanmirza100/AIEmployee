import React, { useState, useEffect } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
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
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { useToast } from '@/components/ui/use-toast';
import { Loader2, FileText, Calendar, ChevronLeft, ChevronRight } from 'lucide-react';
import { getCVRecords, getJobDescriptions, bulkUpdateCVRecords } from '@/services/recruitmentAgentService';
import QualificationReasoning from './QualificationReasoning';

const PAGE_SIZES = [10, 25, 50];

const CVRecords = () => {
  const { toast } = useToast();
  const [records, setRecords] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [jobFilter, setJobFilter] = useState('');
  const [decisionFilter, setDecisionFilter] = useState('');
  const [jobs, setJobs] = useState([]);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [selectedRecord, setSelectedRecord] = useState(null);
  const [modalOpen, setModalOpen] = useState(false);
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
      if (response.status === 'success') {
        setJobs(response.data || []);
      }
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
      toast({
        title: 'Error',
        description: 'Failed to load CV records',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  const getDecisionBadge = (decision) => {
    switch (decision) {
      case 'INTERVIEW':
        return <Badge className="bg-green-500">INTERVIEW</Badge>;
      case 'HOLD':
        return <Badge className="bg-yellow-500">HOLD</Badge>;
      case 'REJECT':
        return <Badge className="bg-red-500">REJECT</Badge>;
      default:
        return <Badge variant="outline">{decision || 'N/A'}</Badge>;
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
    setSelectedRecord(record);
    setModalOpen(true);
  };

  const handleCloseModal = () => {
    setModalOpen(false);
    setSelectedRecord(null);
  };

  const handleBulkChangeDecision = async (decision) => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;
    try {
      setBulkUpdating(true);
      const response = await bulkUpdateCVRecords(ids, decision);
      if (response.status === 'success') {
        toast({
          title: 'Updated',
          description: response.message || `Updated ${response.updated_count} candidate(s) to ${decision}`,
        });
        setSelectedIds(new Set());
        fetchRecords();
      } else {
        throw new Error(response.message || 'Bulk update failed');
      }
    } catch (error) {
      toast({
        title: 'Error',
        description: error?.message || 'Failed to update selected candidates',
        variant: 'destructive',
      });
    } finally {
      setBulkUpdating(false);
    }
  };

  const clearSelection = () => setSelectedIds(new Set());

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h2 className="text-2xl py-5 font-bold">Candidates</h2>
          <p className="text-sm text-muted-foreground">
            View and manage processed candidate CVs. Select a job to filter, click a row for full details.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Select
            value={jobFilter || 'all'}
            onValueChange={(value) => setJobFilter(value === 'all' ? '' : value)}
          >
            <SelectTrigger className="w-[220px]">
              <SelectValue placeholder="Select job" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Jobs</SelectItem>
              {jobs.map((job) => (
                <SelectItem key={job.id} value={job.id.toString()}>
                  {job.title}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select
            value={decisionFilter || 'all'}
            onValueChange={(value) => setDecisionFilter(value === 'all' ? '' : value)}
          >
            <SelectTrigger className="w-[160px]">
              <SelectValue placeholder="Decision" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Decisions</SelectItem>
              <SelectItem value="INTERVIEW">Interview</SelectItem>
              <SelectItem value="HOLD">Hold</SelectItem>
              <SelectItem value="REJECT">Reject</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {selectedIds.size > 0 && (
        <Card className="border-primary/50 bg-primary/5">
          <CardContent className="py-3 flex flex-wrap items-center justify-between gap-3">
            <span className="text-sm font-medium">
              {selectedIds.size} selected — Change decision (e.g. move rejected to Interview):
            </span>
            <div className="flex flex-wrap items-center gap-2">
              <Button
                size="sm"
                variant="default"
                className="bg-green-600 hover:bg-green-700"
                disabled={bulkUpdating}
                onClick={() => handleBulkChangeDecision('INTERVIEW')}
              >
                {bulkUpdating ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : null}
                Mark as Interview
              </Button>
              <Button
                size="sm"
                variant="secondary"
                disabled={bulkUpdating}
                onClick={() => handleBulkChangeDecision('HOLD')}
              >
                Mark as Hold
              </Button>
              <Button
                size="sm"
                variant="secondary"
                className="text-red-600 hover:text-red-700"
                disabled={bulkUpdating}
                onClick={() => handleBulkChangeDecision('REJECT')}
              >
                Mark as Reject
              </Button>
              <Button size="sm" variant="ghost" onClick={clearSelection}>
                Clear selection
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {total === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <FileText className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
            <p className="text-lg font-medium mb-2">No candidates yet</p>
            <p className="text-sm text-muted-foreground">
              {jobFilter || decisionFilter
                ? 'No records match the selected filters. Try changing job or decision.'
                : 'Process CVs to see candidate records here'}
            </p>
          </CardContent>
        </Card>
      ) : (
        <>
          <Card>
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-12 pr-0">
                      <Checkbox
                        checked={allOnPageSelected ? true : someOnPageSelected ? 'indeterminate' : false}
                        onCheckedChange={handleSelectAll}
                        aria-label="Select all on page"
                        className="translate-y-0.5"
                      />
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
                    const isSelected = selectedIds.has(record.id);
                    return (
                      <TableRow
                        key={record.id}
                        className="cursor-pointer hover:bg-muted/70 data-[state=selected]:bg-muted/70"
                        data-state={isSelected ? 'selected' : undefined}
                        onClick={() => handleRowClick(record)}
                      >
                        <TableCell className="w-12 pr-0" onClick={(e) => e.stopPropagation()}>
                          <Checkbox
                            checked={isSelected}
                            onCheckedChange={(checked) => handleSelectRow(record.id, !!checked)}
                            aria-label={`Select ${parsed.name || record.file_name}`}
                            className="translate-y-0.5"
                          />
                        </TableCell>
                        <TableCell className="font-medium">
                          {record.rank != null ? record.rank : '—'}
                        </TableCell>
                        <TableCell>{parsed.name || record.file_name || '—'}</TableCell>
                        <TableCell className="text-muted-foreground">
                          {parsed.email || '—'}
                        </TableCell>
                        <TableCell className="max-w-[180px] truncate" title={record.job_description_title}>
                          {record.job_description_title || '—'}
                        </TableCell>
                        <TableCell>{getDecisionBadge(record.qualification_decision)}</TableCell>
                        <TableCell className="text-right">
                          {record.qualification_confidence != null
                            ? `${record.qualification_confidence}%`
                            : '—'}
                        </TableCell>
                        <TableCell className="text-muted-foreground text-xs">
                          {record.created_at
                            ? new Date(record.created_at).toLocaleDateString()
                            : '—'}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>

            <div className="flex flex-col sm:flex-row items-center justify-between gap-4 px-4 py-3 border-t">
              <div className="flex items-center gap-4">
                <span className="text-sm text-muted-foreground">
                  Showing {rangeStart}–{rangeEnd} of {total}
                </span>
                <Select
                  value={String(pageSize)}
                  onValueChange={(v) => {
                    setPageSize(Number(v));
                    setPage(1);
                  }}
                >
                  <SelectTrigger className="w-[100px] h-9">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {PAGE_SIZES.map((size) => (
                      <SelectItem key={size} value={String(size)}>
                        {size} per page
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={!canPrev}
                >
                  <ChevronLeft className="h-4 w-4 mr-1" />
                  Previous
                </Button>
                <span className="text-sm text-muted-foreground px-2">
                  Page {page} of {totalPages}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={!canNext}
                >
                  Next
                  <ChevronRight className="h-4 w-4 ml-1" />
                </Button>
              </div>
            </div>
          </Card>
        </>
      )}

      {/* Candidate detail modal */}
      <Dialog open={modalOpen} onOpenChange={(open) => !open && handleCloseModal()}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Candidate details</DialogTitle>
            <DialogDescription>
              Full profile and qualification for this candidate
            </DialogDescription>
          </DialogHeader>
          {selectedRecord && (
            <CandidateDetailContent
              record={selectedRecord}
              getDecisionBadge={getDecisionBadge}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};

function CandidateDetailContent({ record, getDecisionBadge }) {
  const parsed = record.parsed || {};
  const qualified = record.qualified || {};
  const summary = record.insights?.summary || record.summary?.summary;
  const skills = parsed.skills || [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-4 pb-4 border-b">
        <div>
          <div className="flex items-center gap-2 mb-1">
            {record.rank != null && (
              <Badge variant="outline" className="font-bold">
                Rank #{record.rank}
              </Badge>
            )}
            {getDecisionBadge(record.qualification_decision)}
            {record.qualification_priority && (
              <Badge variant="secondary">{record.qualification_priority}</Badge>
            )}
          </div>
          <h3 className="text-lg font-semibold">{parsed.name || record.file_name || 'Unknown'}</h3>
          <p className="text-sm text-muted-foreground">
            {parsed.email && <span>{parsed.email}</span>}
            {parsed.phone && (
              <span className="ml-2">{parsed.phone}</span>
            )}
          </p>
          {record.job_description_title && (
            <p className="text-sm text-muted-foreground mt-1">
              Job: {record.job_description_title}
            </p>
          )}
        </div>
        <div className="text-right">
          {record.role_fit_score != null && (
            <div className="text-2xl font-bold text-primary">{record.role_fit_score}%</div>
          )}
          <div className="text-xs text-muted-foreground">Fit Score</div>
          {record.qualification_confidence != null && (
            <div className="text-sm mt-1">Confidence: {record.qualification_confidence}%</div>
          )}
        </div>
      </div>

      {summary && (
        <div>
          <h4 className="font-semibold text-sm mb-1">Summary</h4>
          <p className="text-sm text-muted-foreground">{summary}</p>
        </div>
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

      {skills.length > 0 && (
        <div>
          <h4 className="font-semibold text-sm mb-1">Skills</h4>
          <div className="flex flex-wrap gap-1">
            {skills.map((skill, idx) => (
              <Badge key={idx} variant="outline" className="text-xs">
                {skill}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {record.created_at && (
        <div className="text-xs text-muted-foreground flex items-center gap-1 pt-2 border-t">
          <Calendar className="h-3 w-3" />
          Processed: {new Date(record.created_at).toLocaleString()}
        </div>
      )}
    </div>
  );
}

export default CVRecords;
