import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import {
  Plus, Search, FolderKanban, ChevronDown, ChevronRight,
  ListTodo, Calendar, Target,
} from 'lucide-react';
import PMEmptyState from './EmptyState';
import ManualProjectCreation from './ManualProjectCreation';

// Small helper — the shared color per status. Kept inline so we don't need
// a separate styles module.
const STATUS_STYLES = {
  active: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
  in_progress: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
  planning: 'bg-amber-500/20 text-amber-300 border-amber-500/30',
  on_hold: 'bg-orange-500/20 text-orange-300 border-orange-500/30',
  completed: 'bg-sky-500/20 text-sky-300 border-sky-500/30',
  cancelled: 'bg-white/10 text-white/50 border-white/10',
};

const PRIORITY_STYLES = {
  urgent: 'border-red-500/40 text-red-300',
  high: 'border-orange-500/40 text-orange-300',
  medium: 'border-white/20 text-white/60',
  low: 'border-white/10 text-white/40',
};

/**
 * ProjectsListView (Chunk C of PM_AGENT_UX_REDESIGN.md).
 *
 * Simple, click-to-expand list of the user's projects. Reuses the `projects`
 * data already fetched by the parent (via /api/project-manager/dashboard) —
 * no new API call. Header has a client-side search + "New Project" button;
 * the button opens ManualProjectCreation inside a Dialog and re-fetches
 * (via onProjectCreated) when it succeeds.
 *
 * Deliberately kept lightweight — no sortable columns, no pagination. Once
 * users have >20 projects and start asking for those features, we'll build
 * a proper data-grid; until then this reads at a glance.
 */
export default function ProjectsListView({ projects = [], loading, onProjectCreated, onOpenPilot }) {
  const [query, setQuery] = useState('');
  const [expandedId, setExpandedId] = useState(null);
  const [dialogOpen, setDialogOpen] = useState(false);

  const safeProjects = Array.isArray(projects) ? projects : [];
  const q = query.trim().toLowerCase();
  const filtered = q
    ? safeProjects.filter((p) =>
        (p.name || '').toLowerCase().includes(q) ||
        (p.description || '').toLowerCase().includes(q))
    : safeProjects;

  const toggle = (id) => setExpandedId((cur) => (cur === id ? null : id));

  // Fresh-user branch: no projects at all → hero CTA to Pilot (which is the
  // fast, AI-first path to a first project) with the manual form still
  // reachable via the "New Project" button.
  if (!loading && safeProjects.length === 0) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-end">
          <Button
            onClick={() => setDialogOpen(true)}
            className="gap-1.5"
            style={{
              background: 'linear-gradient(90deg, #06b6d4 0%, #8b5cf6 100%)',
              boxShadow: '0 6px 20px rgba(6,182,212,0.25)',
            }}
          >
            <Plus className="h-4 w-4" /> New Project
          </Button>
        </div>
        <PMEmptyState
          title="No projects yet"
          subtitle="Describe your project or upload a spec — Pilot will set it up for you with tasks, timeline, and team assignments. Prefer to fill a form? Click New Project above."
          buttonLabel="Open Project Pilot"
          onOpenPilot={onOpenPilot}
        />
        <NewProjectDialog open={dialogOpen} onOpenChange={setDialogOpen} onProjectCreated={onProjectCreated} />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header — search + New Project. Kept simple: one row, no filter chips
          yet (until users ask for them). */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-white/40" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search projects…"
            className="pl-9 bg-white/[0.03] border-white/[0.08] text-white placeholder:text-white/40 focus:border-cyan-400/40"
          />
        </div>
        <Button
          onClick={() => setDialogOpen(true)}
          className="gap-1.5 shrink-0"
          style={{
            background: 'linear-gradient(90deg, #06b6d4 0%, #8b5cf6 100%)',
            boxShadow: '0 6px 20px rgba(6,182,212,0.25)',
          }}
        >
          <Plus className="h-4 w-4" /> New Project
        </Button>
      </div>

      {/* Result count — small text below the header so the list feels
          responsive when the search filter narrows it. */}
      <div className="text-xs text-white/45">
        {loading ? 'Loading…' : `${filtered.length} of ${safeProjects.length} project${safeProjects.length === 1 ? '' : 's'}`}
      </div>

      {/* List — one card per project. Click header to expand for details.
          Deliberately not linking anywhere yet (no project detail page in
          the current app) — expansion shows description + task summary,
          which is enough for now. */}
      <div className="space-y-3">
        {filtered.length === 0 && !loading && (
          <div className="text-sm text-white/50 text-center py-8">
            No matching projects. Try a different search.
          </div>
        )}
        {filtered.map((project) => {
          const isExpanded = expandedId === project.id;
          const statusClass = STATUS_STYLES[project.status] || STATUS_STYLES.cancelled;
          const priorityClass = PRIORITY_STYLES[project.priority] || PRIORITY_STYLES.medium;
          const taskCount = project.tasks_count ?? project.task_count ?? (project.tasks?.length || 0);
          return (
            <Card key={project.id} className="bg-[#120d22] border border-[#2d2342] hover:border-cyan-400/30 transition-colors">
              <CardHeader onClick={() => toggle(project.id)} className="pb-3 cursor-pointer">
                <div className="flex items-start gap-3">
                  <div className="mt-1 shrink-0">
                    {isExpanded
                      ? <ChevronDown className="h-4 w-4 text-white/40" />
                      : <ChevronRight className="h-4 w-4 text-white/40" />}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-start justify-between gap-2">
                      <CardTitle className="text-base text-white truncate">{project.name}</CardTitle>
                    </div>
                    <div className="mt-2 flex items-center gap-2 flex-wrap">
                      <Badge className={`border ${statusClass}`}>{project.status}</Badge>
                      {project.priority && (
                        <Badge variant="outline" className={priorityClass}>{project.priority}</Badge>
                      )}
                      <span className="text-xs text-white/45 inline-flex items-center gap-1">
                        <ListTodo className="h-3 w-3" />
                        {taskCount} task{taskCount === 1 ? '' : 's'}
                      </span>
                      {project.created_at && (
                        <span className="text-xs text-white/45 inline-flex items-center gap-1">
                          <Calendar className="h-3 w-3" />
                          {new Date(project.created_at).toLocaleDateString()}
                        </span>
                      )}
                    </div>
                    {project.description && !isExpanded && (
                      <p className="text-sm text-white/50 mt-2 line-clamp-2">{project.description}</p>
                    )}
                  </div>
                </div>
              </CardHeader>
              {isExpanded && (
                <CardContent className="pt-0 pl-11">
                  {project.description && (
                    <p className="text-sm text-white/60 mb-4 pb-3 border-b border-white/[0.06]">
                      {project.description}
                    </p>
                  )}
                  {project.tasks && project.tasks.length > 0 ? (
                    <div className="space-y-2">
                      <h4 className="text-xs font-semibold text-white/60 uppercase tracking-wider flex items-center gap-1.5">
                        <ListTodo className="h-3 w-3" /> Recent tasks ({project.tasks.length})
                      </h4>
                      <ul className="space-y-1.5">
                        {project.tasks.slice(0, 5).map((t) => (
                          <li key={t.id} className="text-sm text-white/70 flex items-center gap-2">
                            <span className="w-1.5 h-1.5 rounded-full bg-white/25 shrink-0" />
                            <span className="flex-1 truncate">{t.title}</span>
                            {t.status && (
                              <span className="text-[10px] uppercase tracking-wider text-white/40">{t.status}</span>
                            )}
                          </li>
                        ))}
                      </ul>
                      {project.tasks.length > 5 && (
                        <div className="text-xs text-white/40 pl-3.5 pt-1">…and {project.tasks.length - 5} more</div>
                      )}
                    </div>
                  ) : (
                    <div className="text-sm text-white/40 inline-flex items-center gap-2">
                      <Target className="h-3.5 w-3.5" />
                      No tasks yet — ask Pilot to break this project down for you.
                    </div>
                  )}
                </CardContent>
              )}
            </Card>
          );
        })}
      </div>

      <NewProjectDialog open={dialogOpen} onOpenChange={setDialogOpen} onProjectCreated={onProjectCreated} />
    </div>
  );
}

/**
 * Thin dialog wrapper around ManualProjectCreation. Passes `onSuccess` to
 * close the dialog after a successful create, and `onProjectCreated` to
 * bubble the refresh signal up to the dashboard so the list re-fetches.
 */
function NewProjectDialog({ open, onOpenChange, onProjectCreated }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto bg-[#0d0b1f] border-white/10">
        <DialogHeader>
          <DialogTitle className="text-white flex items-center gap-2">
            <FolderKanban className="h-5 w-5 text-cyan-300" />
            New Project
          </DialogTitle>
        </DialogHeader>
        <ManualProjectCreation
          onProjectCreated={onProjectCreated}
          onSuccess={() => onOpenChange(false)}
        />
      </DialogContent>
    </Dialog>
  );
}
