/**
 * HRDashboard — landing component for the HR Support Agent.
 *
 * Mirrors FrontlineDashboard's tab structure but tailored for HR:
 *   Overview · Knowledge Q&A · Employees · Documents · Workflows · Meetings
 *
 * Each tab calls into `hrAgentService` (which talks to /api/hr/...). The tab
 * bodies are intentionally compact — they exercise the wired endpoints and
 * provide a starting surface to extend, the same way Frontline's tabs grew.
 */
import React, { useState, useEffect } from 'react';
import {
  Card, CardContent, CardHeader, CardTitle, CardDescription,
} from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/components/ui/use-toast';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
  Loader2,
  LayoutDashboard,
  MessageSquare,
  Users,
  FileText,
  GitBranch,
  CalendarClock,
  Plus,
  Upload,
} from 'lucide-react';
import ErrorBoundary from '@/components/common/ErrorBoundary';
import hrAgentService from '@/services/hrAgentService';
import HRKnowledgeQAAgent from './HRKnowledgeQAAgent';
import HRMeetingScheduler from './HRMeetingScheduler';

const HRDashboard = () => {
  const { toast } = useToast();
  const [activeTab, setActiveTab] = useState('overview');

  // Overview
  const [stats, setStats] = useState(null);
  const [statsLoading, setStatsLoading] = useState(false);

  // Q&A is now handled by `HRKnowledgeQAAgent` (see qa tab)

  // Employees
  const [employees, setEmployees] = useState([]);
  const [empLoading, setEmpLoading] = useState(false);
  const [empSearch, setEmpSearch] = useState('');

  // Documents
  const [documents, setDocuments] = useState([]);
  const [docsLoading, setDocsLoading] = useState(false);
  // Upload dialog state
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadTitle, setUploadTitle] = useState('');
  const [uploadDescription, setUploadDescription] = useState('');
  const [uploadDocType, setUploadDocType] = useState('policy');
  const [uploadConfidentiality, setUploadConfidentiality] = useState('employee');
  const [uploading, setUploading] = useState(false);

  // Workflows
  const [workflows, setWorkflows] = useState([]);
  const [wfLoading, setWfLoading] = useState(false);

  // Meetings tab is now handled by `HRMeetingScheduler` component below.

  // ---------- Loaders ----------
  const loadStats = async () => {
    setStatsLoading(true);
    try {
      const res = await hrAgentService.getHRDashboard();
      setStats(res?.data || null);
    } catch (e) {
      toast({ title: 'Failed to load HR overview', description: e.message, variant: 'destructive' });
    } finally {
      setStatsLoading(false);
    }
  };

  const loadEmployees = async () => {
    setEmpLoading(true);
    try {
      const res = await hrAgentService.listHREmployees({ q: empSearch });
      setEmployees(res?.data || []);
    } catch (e) {
      toast({ title: 'Failed to load employees', description: e.message, variant: 'destructive' });
    } finally {
      setEmpLoading(false);
    }
  };

  const loadDocuments = async () => {
    setDocsLoading(true);
    try {
      const res = await hrAgentService.listHRDocuments();
      setDocuments(res?.data || []);
    } catch (e) {
      toast({ title: 'Failed to load documents', description: e.message, variant: 'destructive' });
    } finally {
      setDocsLoading(false);
    }
  };

  const loadWorkflows = async () => {
    setWfLoading(true);
    try {
      const res = await hrAgentService.listHRWorkflows();
      setWorkflows(res?.data || []);
    } catch (e) {
      toast({ title: 'Failed to load workflows', description: e.message, variant: 'destructive' });
    } finally {
      setWfLoading(false);
    }
  };

  useEffect(() => { loadStats(); }, []);
  useEffect(() => {
    if (activeTab === 'employees') loadEmployees();
    if (activeTab === 'documents') loadDocuments();
    if (activeTab === 'workflows') loadWorkflows();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab]);

  // ---------- Handlers ----------

  const handleUpload = async () => {
    if (!uploadFile) {
      toast({ title: 'Pick a file first', variant: 'destructive' });
      return;
    }
    setUploading(true);
    try {
      const res = await hrAgentService.uploadHRDocument(uploadFile, uploadTitle, uploadDescription, {
        document_type: uploadDocType,
        confidentiality: uploadConfidentiality,
      });
      const status = res?.data?.processing_status;
      const mode = res?.data?.dispatch_mode;
      toast({
        title: 'Document uploaded',
        description: mode === 'inline'
          ? `Processed inline. Status: ${status}.`
          : 'Processing in the background — refresh to see status.',
      });
      setUploadOpen(false);
      setUploadFile(null);
      setUploadTitle('');
      setUploadDescription('');
      loadDocuments();
    } catch (e) {
      toast({ title: 'Upload failed', description: e.message, variant: 'destructive' });
    } finally {
      setUploading(false);
    }
  };

  // ---------- Render ----------
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Users className="h-7 w-7 text-violet-400" />
        <div>
          <h1 className="text-2xl font-semibold">HR Support Agent</h1>
          <p className="text-sm text-muted-foreground">
            Knowledge Q&A · Documents · Workflows · Notifications · Meetings — for your employees
          </p>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="flex flex-wrap h-auto p-1 gap-1">
          <TabsTrigger value="overview"><LayoutDashboard className="h-4 w-4 mr-1" />Overview</TabsTrigger>
          <TabsTrigger value="qa"><MessageSquare className="h-4 w-4 mr-1" />Knowledge Q&A</TabsTrigger>
          <TabsTrigger value="employees"><Users className="h-4 w-4 mr-1" />Employees</TabsTrigger>
          <TabsTrigger value="documents"><FileText className="h-4 w-4 mr-1" />Documents</TabsTrigger>
          <TabsTrigger value="workflows"><GitBranch className="h-4 w-4 mr-1" />Workflows</TabsTrigger>
          <TabsTrigger value="meetings"><CalendarClock className="h-4 w-4 mr-1" />Meetings</TabsTrigger>
        </TabsList>

        {/* OVERVIEW */}
        <TabsContent value="overview" className="mt-6">
          <ErrorBoundary>
            {statsLoading ? (
              <div className="flex justify-center py-10"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
            ) : !stats ? (
              <div className="text-center py-10 text-muted-foreground">No overview data yet.</div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <StatCard label="Active employees" value={stats.employees?.active ?? 0} sub={`${stats.employees?.total ?? 0} total`} />
                <StatCard label="On leave" value={stats.employees?.on_leave ?? 0} sub={`${stats.employees?.on_probation ?? 0} on probation`} />
                <StatCard label="Pending leave requests" value={stats.leave_requests?.pending ?? 0} />
                <StatCard label="Upcoming meetings" value={stats.meetings_upcoming ?? 0} />
                <StatCard label="Indexed documents" value={stats.documents?.indexed ?? 0} sub={`${stats.documents?.total ?? 0} uploaded · ${stats.documents?.failed ?? 0} failed`} />
                <StatCard label="Probation ending in 30d" value={stats.probation_ending_soon ?? 0} />
              </div>
            )}
          </ErrorBoundary>
        </TabsContent>

        {/* KNOWLEDGE Q&A — full chat UI matching Project Pilot */}
        <TabsContent value="qa" className="mt-6">
          <ErrorBoundary>
            <HRKnowledgeQAAgent />
          </ErrorBoundary>
        </TabsContent>

        {/* EMPLOYEES */}
        <TabsContent value="employees" className="mt-6">
          <ErrorBoundary>
            <Card>
              <CardHeader className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                <div>
                  <CardTitle>Employees</CardTitle>
                  <CardDescription>Search and manage your employees</CardDescription>
                </div>
                <div className="flex gap-2">
                  <Input
                    placeholder="Search by name or email"
                    value={empSearch}
                    onChange={(e) => setEmpSearch(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') loadEmployees(); }}
                    className="w-64"
                  />
                  <Button variant="outline" onClick={loadEmployees}>Search</Button>
                </div>
              </CardHeader>
              <CardContent>
                {empLoading ? (
                  <div className="flex justify-center py-8"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
                ) : employees.length === 0 ? (
                  <div className="text-center py-10 text-muted-foreground">No employees yet — create one via <code>POST /api/hr/employees/create</code> or import.</div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
                    {employees.map((e) => (
                      <div key={e.id} className="rounded-md border border-border/50 p-3">
                        <div className="font-medium truncate">{e.full_name}</div>
                        <div className="text-xs text-muted-foreground truncate">{e.work_email}</div>
                        <div className="mt-2 flex flex-wrap gap-1">
                          <Badge variant="secondary" className="text-[10px]">{e.employment_status}</Badge>
                          {e.job_title && <Badge variant="outline" className="text-[10px]">{e.job_title}</Badge>}
                          {e.department && <Badge variant="outline" className="text-[10px]">{e.department}</Badge>}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </ErrorBoundary>
        </TabsContent>

        {/* DOCUMENTS */}
        <TabsContent value="documents" className="mt-6">
          <ErrorBoundary>
            <Card>
              <CardHeader className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                <div>
                  <CardTitle>HR Documents</CardTitle>
                  <CardDescription>Handbook, policies, contracts, payroll. Confidentiality-gated.</CardDescription>
                </div>
                <Button onClick={() => setUploadOpen(true)}><Upload className="h-4 w-4 mr-1" /> Upload</Button>
              </CardHeader>
              <CardContent>
                {docsLoading ? (
                  <div className="flex justify-center py-8"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
                ) : documents.length === 0 ? (
                  <div className="text-center py-10 text-muted-foreground">
                    No documents uploaded yet. Click <strong>Upload</strong> to add your first one.
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
                    {documents.map((d) => (
                      <div key={d.id} className="rounded-md border border-border/50 p-3">
                        <div className="font-medium truncate">{d.title}</div>
                        <div className="text-xs text-muted-foreground truncate">{d.document_type} · {(d.file_format || '').toUpperCase()}</div>
                        <div className="mt-2 flex flex-wrap gap-1">
                          <Badge variant="secondary" className="text-[10px]">{d.confidentiality}</Badge>
                          <Badge variant="outline" className="text-[10px]">{d.processing_status}</Badge>
                          {d.chunks_total > 0 && (
                            <Badge variant="outline" className="text-[10px]">
                              {d.chunks_processed}/{d.chunks_total} chunks
                            </Badge>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Upload dialog */}
            <Dialog open={uploadOpen} onOpenChange={setUploadOpen}>
              <DialogContent className="max-w-md">
                <DialogHeader>
                  <DialogTitle>Upload HR Document</DialogTitle>
                  <DialogDescription>
                    Pick a file, set its type and confidentiality. The agent indexes it for Knowledge Q&A.
                  </DialogDescription>
                </DialogHeader>
                <div className="space-y-3">
                  <div>
                    <Label htmlFor="hr-upload-file">File</Label>
                    <Input
                      id="hr-upload-file"
                      type="file"
                      accept=".pdf,.docx,.doc,.txt,.md,.html,.htm"
                      onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                    />
                  </div>
                  <div>
                    <Label htmlFor="hr-upload-title">Title</Label>
                    <Input
                      id="hr-upload-title"
                      placeholder="Defaults to filename"
                      value={uploadTitle}
                      onChange={(e) => setUploadTitle(e.target.value)}
                    />
                  </div>
                  <div>
                    <Label htmlFor="hr-upload-desc">Description</Label>
                    <Textarea
                      id="hr-upload-desc"
                      rows={2}
                      value={uploadDescription}
                      onChange={(e) => setUploadDescription(e.target.value)}
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <Label>Type</Label>
                      <Select value={uploadDocType} onValueChange={setUploadDocType}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="handbook">Employee Handbook</SelectItem>
                          <SelectItem value="policy">Policy</SelectItem>
                          <SelectItem value="procedure">Procedure / SOP</SelectItem>
                          <SelectItem value="offer_letter">Offer Letter</SelectItem>
                          <SelectItem value="contract">Contract</SelectItem>
                          <SelectItem value="payslip">Payslip</SelectItem>
                          <SelectItem value="payroll">Payroll / Comp</SelectItem>
                          <SelectItem value="performance_review">Performance Review</SelectItem>
                          <SelectItem value="leave_form">Leave Form</SelectItem>
                          <SelectItem value="training">Training</SelectItem>
                          <SelectItem value="benefits">Benefits</SelectItem>
                          <SelectItem value="compliance">Compliance</SelectItem>
                          <SelectItem value="other">Other</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label>Confidentiality</Label>
                      <Select value={uploadConfidentiality} onValueChange={setUploadConfidentiality}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="public">Public</SelectItem>
                          <SelectItem value="employee">All Employees</SelectItem>
                          <SelectItem value="manager">Managers + HR</SelectItem>
                          <SelectItem value="hr_only">HR Only</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                </div>
                <DialogFooter>
                  <Button variant="outline" onClick={() => setUploadOpen(false)} disabled={uploading}>Cancel</Button>
                  <Button onClick={handleUpload} disabled={uploading || !uploadFile}>
                    {uploading ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Upload className="h-4 w-4 mr-1" />}
                    Upload
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </ErrorBoundary>
        </TabsContent>

        {/* WORKFLOWS */}
        <TabsContent value="workflows" className="mt-6">
          <ErrorBoundary>
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <div>
                  <CardTitle>HR Workflows / SOPs</CardTitle>
                  <CardDescription>Onboarding · offboarding · approvals · reminders</CardDescription>
                </div>
                <Button variant="outline" disabled title="Builder UI is on the roadmap">
                  <Plus className="h-4 w-4 mr-1" /> New (UI WIP)
                </Button>
              </CardHeader>
              <CardContent>
                {wfLoading ? (
                  <div className="flex justify-center py-8"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
                ) : workflows.length === 0 ? (
                  <div className="text-center py-10 text-muted-foreground">No workflows yet.</div>
                ) : (
                  <div className="space-y-2">
                    {workflows.map((w) => (
                      <div key={w.id} className="rounded-md border border-border/50 p-3 flex items-center justify-between">
                        <div className="min-w-0">
                          <div className="font-medium truncate">{w.name}</div>
                          <div className="text-xs text-muted-foreground truncate">
                            Trigger: {JSON.stringify(w.trigger_conditions || {})}
                          </div>
                        </div>
                        <Badge variant={w.is_active ? 'default' : 'secondary'} className="text-[10px]">
                          {w.is_active ? 'Active' : 'Inactive'}
                        </Badge>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </ErrorBoundary>
        </TabsContent>

        {/* MEETINGS */}
        <TabsContent value="meetings" className="mt-6">
          <ErrorBoundary>
            <HRMeetingScheduler />
          </ErrorBoundary>
        </TabsContent>
      </Tabs>
    </div>
  );
};

const StatCard = ({ label, value, sub }) => (
  <Card>
    <CardContent className="p-4">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-3xl font-semibold mt-1">{value}</div>
      {sub && <div className="text-[11px] text-muted-foreground mt-1">{sub}</div>}
    </CardContent>
  </Card>
);

export default HRDashboard;
