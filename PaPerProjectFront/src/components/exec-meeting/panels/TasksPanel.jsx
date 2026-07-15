// Tasks panel for the AI Executive Meeting Assistant — extracted from
// ExecMeetingDashboard.jsx. Pure presentation: all state and handlers are
// passed in as props; the panel never owns state itself.

import React from 'react';
import { Button } from '@/components/ui/button';
import {
  Loader2, ListChecks, Plus, Trash2, Pencil, RefreshCw, ChevronRight,
} from 'lucide-react';
import {
  CARD_STYLE, ROW_STYLE, priorityBadge, statusBadge, AssigneeAvatars, EmptyState,
  BulkSelectBar, SelectCheckbox, FilterBar,
} from '../shared';

const TASK_STATUS_OPTIONS = [
  { value: 'todo', label: 'To Do' },
  { value: 'in_progress', label: 'In Progress' },
  { value: 'review', label: 'Review' },
  { value: 'done', label: 'Done' },
  { value: 'blocked', label: 'Blocked' },
];
const TASK_PRIORITY_OPTIONS = [
  { value: 'high', label: 'High' },
  { value: 'medium', label: 'Medium' },
  { value: 'low', label: 'Low' },
];

export const TasksPanel = ({
  tasks, tasksLoading,
  expandedTaskId, expandedSubtasksId,
  loadTasks, setShowTaskDialog,
  setExpandedTaskId, setExpandedSubtasksId, setEditingTask,
  setSubtaskParentTask, setConfirmDeleteTaskId,
  selectedTaskIds, toggleSelected, setSelectedTaskIds, bulkDeleteTasks, bulkDeleting,
  filters = {}, setFilters = () => {},
}) => {
  const filtersActive = !!(filters.search || filters.status || filters.priority || filters.date);
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-white font-semibold flex items-center gap-2">
          <ListChecks className="h-4 w-4 text-sky-400" />
          Tasks
        </h3>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="ghost" onClick={() => loadTasks()} disabled={tasksLoading} className="text-white/40 hover:text-white">
            <RefreshCw className={`h-3.5 w-3.5 ${tasksLoading ? 'animate-spin' : ''}`} />
          </Button>
          <Button size="sm" onClick={() => setShowTaskDialog(true)} style={{ background: 'linear-gradient(90deg, #a259ff 0%, #7c3aed 100%)' }} className="text-white border-0 hover:opacity-90">
            <Plus className="h-4 w-4 mr-1" /> Add Task
          </Button>
        </div>
      </div>

      <FilterBar
        search={filters.search || ''}
        onSearchChange={v => setFilters(f => ({ ...f, search: v }))}
        searchPlaceholder="Search tasks…"
        selects={[
          {
            value: filters.priority,
            onChange: v => setFilters(f => ({ ...f, priority: v })),
            placeholder: 'All priorities', allLabel: 'All priorities',
            options: TASK_PRIORITY_OPTIONS,
          },
          {
            value: filters.status,
            onChange: v => setFilters(f => ({ ...f, status: v })),
            placeholder: 'All statuses', allLabel: 'All statuses',
            options: TASK_STATUS_OPTIONS,
          },
        ]}
        date={filters.date}
        onDateChange={v => setFilters(f => ({ ...f, date: v }))}
        active={filtersActive}
        onClear={() => setFilters({ search: '', status: '', priority: '', date: '' })}
      />

      {tasksLoading ? (
        <div className="flex justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-violet-400" /></div>
      ) : !Array.isArray(tasks) || tasks.length === 0 ? (
        <EmptyState icon={ListChecks} label={filtersActive ? 'No tasks match these filters' : 'No tasks yet'} />
      ) : (
        <>
        <BulkSelectBar
          allIds={tasks.map(t => t.id)}
          selected={selectedTaskIds}
          onToggleAll={() => setSelectedTaskIds(selectedTaskIds.size === tasks.length ? new Set() : new Set(tasks.map(t => t.id)))}
          onDelete={bulkDeleteTasks}
          deleting={bulkDeleting}
          label="task"
        />
        <div className="rounded-2xl overflow-hidden" style={CARD_STYLE}>
          {tasks.map(t => {
            const isOpen = expandedTaskId === t.id;
            const subtasks = t.subtasks || [];
            const subtaskDone = t.subtask_done_count || 0;
            const subtaskTotal = t.subtask_count ?? subtasks.length;
            // Weighted progress so the bar also moves for in-progress work, not
            // just fully-done subtasks: done = 1.0, in_progress/review = 0.5.
            const subtaskProgress = subtaskTotal > 0
              ? Math.round(
                  (subtasks.reduce((sum, st) => sum + (st.status === 'done' ? 1 : (st.status === 'in_progress' || st.status === 'review') ? 0.5 : 0), 0) / subtaskTotal) * 100
                )
              : 0;
            return (
              <div key={t.id} style={ROW_STYLE}>
                {/* ── Row ── */}
                <div
                  className="flex items-center gap-4 px-4 py-3 cursor-pointer hover:bg-white/[0.04] transition-colors"
                  onClick={() => setExpandedTaskId(isOpen ? null : t.id)}
                >
                  <SelectCheckbox
                    checked={selectedTaskIds.has(t.id)}
                    onChange={() => toggleSelected(setSelectedTaskIds, t.id)}
                  />
                  <div className="flex-1 min-w-0">
                    <p className="text-white text-sm font-medium truncate">{t.title}</p>
                    <div className="flex items-center gap-1.5 mt-0.5">
                      <p className="text-white/40 text-xs">
                        {t.due_date ? `Due: ${t.due_date}` : 'No due date'}
                      </p>
                      {subtaskTotal > 0 && (
                        <span className="text-white/30 text-xs flex items-center gap-1">
                          · <ListChecks className="h-3 w-3" />{subtaskDone}/{subtaskTotal}
                        </span>
                      )}
                      <AssigneeAvatars assignees={t.assignees} />
                    </div>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    {priorityBadge(t.priority)}
                    {statusBadge(t.status)}
                    {/* Quick actions inline with the badges */}
                    <div className="flex items-center gap-0.5">
                      <button
                        type="button" title="Edit"
                        onClick={e => { e.stopPropagation(); setEditingTask(t); }}
                        className="p-1 rounded text-white/30 hover:text-violet-300 hover:bg-violet-500/10 transition-colors">
                        <Pencil className="h-3.5 w-3.5" />
                      </button>
                      <button
                        type="button" title="Add subtask"
                        onClick={e => { e.stopPropagation(); setSubtaskParentTask(t); }}
                        className="p-1 rounded text-white/30 hover:text-sky-300 hover:bg-sky-500/10 transition-colors">
                        <Plus className="h-3.5 w-3.5" />
                      </button>
                      <button
                        type="button" title="Delete"
                        onClick={e => { e.stopPropagation(); setConfirmDeleteTaskId(t.id); }}
                        className="p-1 rounded text-white/30 hover:text-red-400 hover:bg-red-500/10 transition-colors">
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                    <ChevronRight className={`h-4 w-4 text-white/30 transition-transform ${isOpen ? 'rotate-90' : ''}`} />
                  </div>
                </div>

                {/* ── Inline detail panel ── */}
                {isOpen && (
                  <div className="px-4 pb-4 pt-2 border-t border-white/5 space-y-3">
                    {t.description && (
                      <p className="text-white/60 text-xs whitespace-pre-wrap">{t.description}</p>
                    )}
                    {(t.assignees || []).length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        {t.assignees.map(a => (
                          <span key={a.id} className="inline-flex items-center gap-1.5 pl-1 pr-2.5 py-0.5 rounded-full bg-violet-500/20 border border-violet-500/30 text-violet-200 text-xs">
                            <span className="h-4 w-4 rounded-full bg-violet-500/40 flex items-center justify-center text-[9px] font-semibold">
                              {a.full_name?.[0]?.toUpperCase() || '?'}
                            </span>
                            {a.full_name}
                          </span>
                        ))}
                      </div>
                    )}
                    {t.ai_reasoning && (
                      <p className="text-white/40 text-xs italic">{t.ai_reasoning}</p>
                    )}

                    {/* Subtasks accordion */}
                    {subtasks.length > 0 && (() => {
                      const subOpen = expandedSubtasksId === t.id;
                      const pct = subtaskProgress;
                      return (
                        <div className="rounded-lg border border-white/10 bg-white/[0.02] overflow-hidden">
                          {/* Accordion header */}
                          <button
                            type="button"
                            className="w-full flex items-center gap-3 px-3 py-2 hover:bg-white/[0.04] transition-colors"
                            onClick={e => { e.stopPropagation(); setExpandedSubtasksId(subOpen ? null : t.id); }}
                          >
                            <ChevronRight className={`h-3.5 w-3.5 text-white/40 transition-transform ${subOpen ? 'rotate-90' : ''}`} />
                            <ListChecks className="h-3.5 w-3.5 text-sky-400" />
                            <span className="text-xs font-medium text-white/80">Subtasks</span>
                            <span className="text-[10px] text-white/40">{subtaskDone}/{subtaskTotal}</span>
                            {/* progress bar */}
                            <div className="flex-1 h-1 rounded-full bg-white/10 overflow-hidden">
                              <div className="h-full bg-sky-400/70 transition-all" style={{ width: `${pct}%` }} />
                            </div>
                          </button>

                          {/* Accordion body */}
                          {subOpen && (
                            <div className="px-2 pb-2 space-y-1.5">
                              {subtasks.map(st => (
                                <div key={st.id}
                                  className="flex items-center gap-3 rounded-lg px-3 py-2 bg-white/[0.03] border border-white/5 cursor-pointer hover:bg-white/[0.06]"
                                  onClick={e => { e.stopPropagation(); setEditingTask(st); }}>
                                  <div className="flex-1 min-w-0">
                                    <p className={`text-xs font-medium truncate ${st.status === 'done' ? 'text-white/40 line-through' : 'text-white/80'}`}>{st.title}</p>
                                    {st.due_date && <p className="text-white/30 text-[10px]">Due: {st.due_date}</p>}
                                  </div>
                                  <AssigneeAvatars assignees={st.assignees} size="sm" />
                                  {priorityBadge(st.priority)}
                                  {statusBadge(st.status)}
                                  <button
                                    className="text-white/20 hover:text-red-400 text-xs px-1"
                                    onClick={e => { e.stopPropagation(); setConfirmDeleteTaskId(st.id); }}>
                                    <Trash2 className="h-3 w-3" />
                                  </button>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      );
                    })()}
                  </div>
                )}
              </div>
            );
          })}
        </div>
        </>
      )}
    </div>
  );
};
