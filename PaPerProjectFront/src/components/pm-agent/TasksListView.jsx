import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Tabs, TabsContent } from '@/components/ui/tabs';
import { useToast } from '@/components/ui/use-toast';
import { companyApi } from '@/services/companyAuthService';
import { apiErrorMessage } from '@/utils/apiErrorMessage';
import {
  Plus, Search, ListChecks, Calendar as CalendarIcon, Loader2, User,
  CheckSquare, Target, BarChart3, RotateCw,
} from 'lucide-react';
import PMEmptyState from './EmptyState';
import ManualTaskCreation from './ManualTaskCreation';
import TaskPrioritizationAgent from './TaskPrioritizationAgent';
import TimelineGanttAgent from './TimelineGanttAgent';

// Status → colour. Aligned to what the backend actually sends
// (see api/serializers/user_tasks.py — TaskSerializer.status field).
const STATUS_STYLES = {
  todo: 'bg-white/10 text-white/60 border-white/10',
  pending: 'bg-white/10 text-white/60 border-white/10',
  in_progress: 'bg-cyan-500/20 text-cyan-300 border-cyan-500/30',
  blocked: 'bg-orange-500/20 text-orange-300 border-orange-500/30',
  completed: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
  cancelled: 'bg-white/5 text-white/40 border-white/10',
};

const PRIORITY_STYLES = {
  urgent: 'border-red-500/40 text-red-300',
  high: 'border-orange-500/40 text-orange-300',
  medium: 'border-white/20 text-white/60',
  low: 'border-white/10 text-white/40',
};

/**
 * TasksListView (Chunk D of PM_AGENT_UX_REDESIGN.md).
 *
 * Consolidates three previously-separate tabs into one, via nested sub-tabs:
 *   • List        — flat task list across all projects (paginated backend)
 *   • Prioritize  — the existing TaskPrioritizationAgent
 *   • Timeline    — the existing TimelineGanttAgent
 *
 * The two "folded-in" tools are rendered as-is (they already accept the
 * projects prop we pass through). The List tab is new; it hits
 * `/api/company/users/tasks` which returns a rich TaskSerializer response.
 */
const TASKS_SUB_VALUES = ['list', 'prioritize', 'timeline'];
const TASKS_DEFAULT_SUB = 'list';

export default function TasksListView({
  projects = [],
  onOpenPilot,
  activeSubTab,
  onSubTabChange,
}) {
  const [localActive, setLocalActive] = useState(TASKS_DEFAULT_SUB);
  const active = TASKS_SUB_VALUES.includes(activeSubTab)
    ? activeSubTab
    : (onSubTabChange ? TASKS_DEFAULT_SUB : localActive);
  const setActive = (v) => (onSubTabChange ? onSubTabChange(v) : setLocalActive(v));

  return (
    <div className="space-y-6">
      <Tabs value={active} onValueChange={setActive} className="w-full">
        {/* Internal sub-tab bar removed — users navigate between List /
            Prioritize / Timeline via the global AgentSidebar. Tabs wrapper
            kept so old `?sub=` bookmarks still resolve. */}

        <TabsContent value="list" className="mt-6">
          <TaskList projects={projects} onOpenPilot={onOpenPilot} />
        </TabsContent>
        <TabsContent value="prioritize" className="mt-6">
          <TaskPrioritizationAgent projects={projects} onOpenPilot={onOpenPilot} />
        </TabsContent>
        <TabsContent value="timeline" className="mt-6">
          <TimelineGanttAgent projects={projects} onOpenPilot={onOpenPilot} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

// SubTabTrigger removed — internal sub-tab bar no longer rendered.

// ─── TaskList ──────────────────────────────────────────────────────────────
// The List sub-tab. Own component so its state (search / filters / pagination
// / loading) stays scoped and doesn't force the parent Tasks tab to re-render.
function TaskList({ projects = [], onOpenPilot }) {
  const { toast } = useToast();
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [projectFilter, setProjectFilter] = useState('all');
  const [dialogOpen, setDialogOpen] = useState(false);

  // Backend endpoint: /api/company/users/tasks (see
  // api/views/company_user_tasks.py). Returns paginated results filtered by
  // status / user_id / project_id. We ask for a big first page and filter
  // client-side for now — real pagination lands when someone has 200+ tasks
  // and asks for it.
  const fetchTasks = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await companyApi.get('/company/users/tasks?page=1&limit=200');
      const data = res?.data?.data || res?.data?.results || res?.data || [];
      setTasks(Array.isArray(data) ? data : []);
    } catch (e) {
      const msg = apiErrorMessage(e);
      setError(msg);
      toast({ title: 'Failed to load tasks', description: msg, variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => { fetchTasks(); }, [fetchTasks]);

  const q = query.trim().toLowerCase();
  const filtered = tasks.filter((t) => {
    if (statusFilter !== 'all' && t.status !== statusFilter) return false;
    if (projectFilter !== 'all' && String(t.project_id) !== String(projectFilter)) return false;
    if (q && !(t.title || '').toLowerCase().includes(q)
        && !(t.description || '').toLowerCase().includes(q)) return false;
    return true;
  });

  // No projects → the endpoint has nothing to give us. Route to Pilot which
  // works with zero data; the manual "New Task" button is disabled because
  // a task must belong to a project.
  if (projects.length === 0) {
    return (
      <PMEmptyState
        title="Create a project first"
        subtitle="Tasks belong to a project. Start one in Pilot to unlock this view — you can then break it down into tasks with a single message."
        onOpenPilot={onOpenPilot}
      />
    );
  }

  return (
    <div className="space-y-4">
      {/* Header — search + filters + refresh + New Task */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:flex-wrap">
        <div className="relative flex-1 min-w-[220px] max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-white/40" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search tasks…"
            className="pl-9 bg-white/[0.03] border-white/[0.08] text-white placeholder:text-white/40 focus:border-cyan-400/40"
          />
        </div>
        <Select value={projectFilter} onValueChange={setProjectFilter}>
          <SelectTrigger className="w-full sm:w-52 bg-white/[0.03] border-white/[0.08] text-white/80">
            <SelectValue placeholder="All projects" />
          </SelectTrigger>
          <SelectContent className="bg-[#161630] border-white/10">
            <SelectItem value="all">All projects</SelectItem>
            {projects.map((p) => (
              <SelectItem key={p.id} value={String(p.id)}>{p.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-full sm:w-44 bg-white/[0.03] border-white/[0.08] text-white/80">
            <SelectValue placeholder="All statuses" />
          </SelectTrigger>
          <SelectContent className="bg-[#161630] border-white/10">
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="todo">Todo</SelectItem>
            <SelectItem value="in_progress">In progress</SelectItem>
            <SelectItem value="blocked">Blocked</SelectItem>
            <SelectItem value="completed">Completed</SelectItem>
          </SelectContent>
        </Select>
        <div className="flex items-center gap-2 sm:ml-auto">
          <Button
            variant="ghost"
            size="sm"
            onClick={fetchTasks}
            disabled={loading}
            className="text-white/60 hover:text-white"
            title="Refresh"
          >
            <RotateCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          </Button>
          <Button
            onClick={() => setDialogOpen(true)}
            className="gap-1.5 shrink-0"
            style={{
              background: 'linear-gradient(90deg, #06b6d4 0%, #8b5cf6 100%)',
              boxShadow: '0 6px 20px rgba(6,182,212,0.25)',
            }}
          >
            <Plus className="h-4 w-4" /> New Task
          </Button>
        </div>
      </div>

      {/* Count / status line */}
      <div className="text-xs text-white/45">
        {loading
          ? 'Loading…'
          : error
            ? <span className="text-rose-300">{error}</span>
            : `${filtered.length} of ${tasks.length} task${tasks.length === 1 ? '' : 's'}`}
      </div>

      {/* Body */}
      {loading ? (
        <div className="flex items-center justify-center py-10">
          <Loader2 className="h-5 w-5 animate-spin text-white/40" />
        </div>
      ) : tasks.length === 0 ? (
        <PMEmptyState
          variant="inline"
          title="No tasks yet"
          subtitle="Ask Pilot to break your project down into tasks, or click New Task to add one manually."
          buttonLabel="Open Project Pilot"
          onOpenPilot={onOpenPilot}
        />
      ) : filtered.length === 0 ? (
        <div className="text-sm text-white/50 text-center py-8">
          No tasks match your filters. Clear them or search for something else.
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map((t) => {
            const statusClass = STATUS_STYLES[t.status] || STATUS_STYLES.todo;
            const priorityClass = PRIORITY_STYLES[t.priority] || PRIORITY_STYLES.medium;
            return (
              <Card key={t.id} className="bg-[#120d22] border border-[#2d2342] hover:border-cyan-400/30 transition-colors">
                <CardContent className="py-3">
                  <div className="flex items-start gap-3">
                    <ListChecks className="h-4 w-4 text-cyan-300/70 mt-1 shrink-0" />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-sm font-medium text-white truncate">{t.title}</p>
                      </div>
                      {t.description && (
                        <p className="text-xs text-white/50 mt-0.5 line-clamp-2">{t.description}</p>
                      )}
                      <div className="mt-2 flex items-center gap-2 flex-wrap">
                        <Badge className={`border ${statusClass}`}>{(t.status || 'todo').replace('_', ' ')}</Badge>
                        {t.priority && (
                          <Badge variant="outline" className={priorityClass}>{t.priority}</Badge>
                        )}
                        {t.project_name && (
                          <span className="text-[11px] text-white/45 inline-flex items-center gap-1">
                            <Target className="h-3 w-3" />
                            {t.project_name}
                          </span>
                        )}
                        {t.assignee_name && (
                          <span className="text-[11px] text-white/45 inline-flex items-center gap-1">
                            <User className="h-3 w-3" />
                            {t.assignee_name}
                          </span>
                        )}
                        {t.due_date && (
                          <span className="text-[11px] text-white/45 inline-flex items-center gap-1">
                            <CalendarIcon className="h-3 w-3" />
                            {new Date(t.due_date).toLocaleDateString()}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      <NewTaskDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        defaultProjectId={projectFilter !== 'all' ? projectFilter : undefined}
        onTaskCreated={fetchTasks}
      />
    </div>
  );
}

/**
 * Thin dialog wrapper around ManualTaskCreation. When the current filter is
 * scoped to a specific project, we pre-select that project in the dialog —
 * saves the user one click when adding tasks in a filtered view.
 */
function NewTaskDialog({ open, onOpenChange, defaultProjectId, onTaskCreated }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto bg-[#0d0b1f] border-white/10">
        <DialogHeader>
          <DialogTitle className="text-white flex items-center gap-2">
            <ListChecks className="h-5 w-5 text-cyan-300" />
            New Task
          </DialogTitle>
        </DialogHeader>
        <ManualTaskCreation
          defaultProjectId={defaultProjectId}
          onTaskCreated={onTaskCreated}
          onSuccess={() => onOpenChange(false)}
        />
      </DialogContent>
    </Dialog>
  );
}
