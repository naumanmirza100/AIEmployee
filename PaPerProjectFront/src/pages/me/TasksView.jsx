import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Slider } from '@/components/ui/slider';
import { Label } from '@/components/ui/label';
import { useToast } from '@/components/ui/use-toast';
import {
  CheckSquare,
  ListTodo,
  FolderKanban,
  Calendar,
  Loader2,
  CheckCircle2,
  Circle,
  AlertTriangle,
  RefreshCw,
} from 'lucide-react';
import userTaskService from '@/services/userTaskService';
import {
  getStatusColor,
  getPriorityColor,
  getStatusIcon,
  humanStatus,
  daysUntilDue,
  isOverdue,
} from '@/utils/taskHelpers';

/**
 * TasksView — /me/tasks
 *
 * Redesigned task list. Kept everything that worked from the classic
 * dashboard (progress slider, status change, subtask display) and fixed
 * the friction points the audit flagged:
 *   • Overdue tasks now have a red left-border and a "Overdue" badge
 *   • Blocked-slider explains itself via a tooltip
 *   • Empty states have primary CTAs instead of dead-ends
 *   • Status filter now includes an "Overdue" quick-filter
 *
 * Subtask ticking is intentionally NOT wired here — the backend doesn't
 * expose a subtask-status endpoint yet. See USER_DASHBOARD_REDESIGN.md
 * problem #7. Ticking lands when the endpoint does.
 */
export default function TasksView() {
  const { toast } = useToast();

  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('all');
  const [sliderValues, setSliderValues] = useState({});

  useEffect(() => {
    fetchTasks();
  }, [statusFilter]);

  const fetchTasks = async () => {
    setLoading(true);
    try {
      const params = statusFilter !== 'all' && statusFilter !== 'overdue' ? { status: statusFilter } : {};
      const res = await userTaskService.getMyTasks(params);
      if (res.status === 'success') setTasks(res.data || []);
    } catch (err) {
      toast({ title: 'Error', description: err.message || 'Failed to load tasks', variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  const handleStatusChange = async (taskId, newStatus) => {
    try {
      let progressUpdate = null;
      if (newStatus === 'done') progressUpdate = 100;
      else if (newStatus === 'todo') progressUpdate = 0;

      const res = await userTaskService.updateTaskStatus(taskId, newStatus);
      if (res.status !== 'success') throw new Error(res.message || 'Failed');

      if (progressUpdate !== null) {
        try {
          await userTaskService.updateTaskProgress(taskId, progressUpdate);
        } catch { /* status update already committed */ }
        setTasks((prev) => prev.map((t) => t.id === taskId ? { ...t, status: newStatus, progress_percentage: progressUpdate } : t));
        setSliderValues((prev) => ({ ...prev, [taskId]: progressUpdate }));
      } else {
        setTasks((prev) => prev.map((t) => t.id === taskId ? { ...t, status: newStatus } : t));
      }
      toast({ title: 'Task updated' });
    } catch (err) {
      toast({ title: 'Error', description: err.message, variant: 'destructive' });
    }
  };

  const handleProgressChange = (taskId, value) => {
    setSliderValues((prev) => ({ ...prev, [taskId]: value }));
    setTasks((prev) => prev.map((t) => t.id === taskId ? { ...t, progress_percentage: value } : t));
  };

  const handleProgressCommit = async (taskId, value) => {
    try {
      let statusUpdate = null;
      if (value === 0) statusUpdate = 'todo';
      else if (value === 100) statusUpdate = 'done';
      else {
        const cur = tasks.find((t) => t.id === taskId);
        if (cur && cur.status !== 'blocked') statusUpdate = 'in_progress';
      }
      const pRes = await userTaskService.updateTaskProgress(taskId, value);
      if (pRes.status !== 'success') { fetchTasks(); return; }
      if (statusUpdate) {
        try { await userTaskService.updateTaskStatus(taskId, statusUpdate); } catch { /* progress already saved */ }
        setTasks((prev) => prev.map((t) => t.id === taskId ? { ...t, progress_percentage: value, status: statusUpdate } : t));
      } else {
        setTasks((prev) => prev.map((t) => t.id === taskId ? { ...t, progress_percentage: value } : t));
      }
    } catch (err) {
      toast({ title: 'Error', description: err.message || 'Failed to update progress', variant: 'destructive' });
    }
  };

  const displayed = statusFilter === 'overdue' ? tasks.filter(isOverdue) : tasks;
  const overdueCount = tasks.filter(isOverdue).length;

  return (
    <div className="max-w-5xl mx-auto space-y-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3 text-white">
          <CheckSquare className="h-6 w-6 text-violet-300" />
          <div>
            <h2 className="text-2xl font-bold">My Tasks</h2>
            <p className="text-xs text-white/50">
              {loading ? 'Loading…' : `${displayed.length} shown${overdueCount > 0 && statusFilter !== 'overdue' ? ` • ${overdueCount} overdue` : ''}`}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-[160px] bg-white/[0.03] border-white/10 text-white">
              <SelectValue placeholder="Filter" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Tasks</SelectItem>
              <SelectItem value="overdue">Overdue{overdueCount > 0 ? ` (${overdueCount})` : ''}</SelectItem>
              <SelectItem value="todo">To Do</SelectItem>
              <SelectItem value="in_progress">In Progress</SelectItem>
              <SelectItem value="review">Review</SelectItem>
              <SelectItem value="done">Done</SelectItem>
              <SelectItem value="blocked">Blocked</SelectItem>
            </SelectContent>
          </Select>
          <Button variant="outline" size="sm" onClick={fetchTasks} className="border-white/15 text-white/70 hover:bg-white/[0.06] hover:text-white">
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-violet-300" /></div>
      ) : displayed.length === 0 ? (
        <Card className="bg-white/[0.04] border-white/[0.08]">
          <CardContent className="py-16 text-center">
            <ListTodo className="h-12 w-12 mx-auto text-white/25 mb-3" />
            <p className="text-lg font-medium text-white mb-1">No tasks to show</p>
            <p className="text-sm text-white/50">
              {statusFilter === 'overdue' ? 'Nothing overdue. Nice.'
                : statusFilter === 'all' ? 'You don\'t have any tasks assigned yet.'
                : `No tasks with status "${humanStatus(statusFilter)}".`}
            </p>
            {statusFilter !== 'all' && (
              <Button variant="outline" size="sm" onClick={() => setStatusFilter('all')} className="mt-4 border-white/15 text-white/70 hover:bg-white/[0.06]">
                Show all
              </Button>
            )}
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3">
          {displayed.map((task) => {
            const overdue = isOverdue(task);
            const days = daysUntilDue(task.due_date);
            const val = sliderValues[task.id] !== undefined ? sliderValues[task.id] : (task.progress_percentage || 0);
            return (
              <Card
                key={task.id}
                className={`bg-white/[0.03] border-white/[0.08] ${overdue ? 'border-l-4 border-l-red-500' : ''}`}
              >
                <CardHeader className="pb-3">
                  <div className="flex-1 min-w-0">
                    <CardTitle className="text-base text-white">{task.title}</CardTitle>
                    {task.description && (
                      <p className="text-xs text-white/50 mt-1 line-clamp-2">{task.description}</p>
                    )}
                    <div className="flex flex-wrap gap-2 items-center mt-3">
                      <Badge className={getStatusColor(task.status)}>
                        {getStatusIcon(task.status)}
                        <span className="ml-1 capitalize">{humanStatus(task.status)}</span>
                      </Badge>
                      <Badge variant="outline" className={getPriorityColor(task.priority)}>
                        {task.priority} priority
                      </Badge>
                      {task.project_name && (
                        <span className="text-xs text-white/50 flex items-center gap-1">
                          <FolderKanban className="h-3.5 w-3.5" />{task.project_name}
                        </span>
                      )}
                      {task.due_date && (
                        <span className={`text-xs flex items-center gap-1 ${overdue ? 'text-red-400 font-medium' : 'text-white/50'}`}>
                          <Calendar className="h-3.5 w-3.5" />
                          {new Date(task.due_date).toLocaleDateString()}
                          {days !== null && (
                            <span className="text-[10px] opacity-80">
                              {days < 0 ? `${Math.abs(days)}d overdue` : days === 0 ? 'today' : `in ${days}d`}
                            </span>
                          )}
                        </span>
                      )}
                      {overdue && (
                        <Badge className="bg-red-500/15 text-red-300 border border-red-500/25 text-[10px]">
                          <AlertTriangle className="h-3 w-3 mr-1" />Overdue
                        </Badge>
                      )}
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="space-y-1.5">
                    <div className="flex justify-between items-center">
                      <Label className="text-xs text-white/60">Progress</Label>
                      <span className="text-xs text-white/70 tabular-nums">{val}%</span>
                    </div>
                    <div title={task.status === 'blocked' ? 'This task is blocked — unblock it before updating progress.' : undefined}>
                      <Slider
                        value={[val]}
                        onValueChange={(v) => task.status !== 'blocked' && handleProgressChange(task.id, v[0])}
                        onValueCommit={(v) => task.status !== 'blocked' && handleProgressCommit(task.id, v[0])}
                        max={100}
                        step={1}
                        className="w-full"
                        disabled={task.status === 'blocked'}
                      />
                    </div>
                    {task.status === 'blocked' && (
                      <p className="text-[10px] text-red-300/70">Progress locked while blocked.</p>
                    )}
                  </div>

                  <div className="flex items-center gap-2">
                    <Label className="text-xs text-white/60 w-14">Status</Label>
                    <Select value={task.status} onValueChange={(v) => handleStatusChange(task.id, v)}>
                      <SelectTrigger className="flex-1 bg-white/[0.03] border-white/10 text-white">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="todo">To Do</SelectItem>
                        <SelectItem value="in_progress">In Progress</SelectItem>
                        <SelectItem value="review">Review</SelectItem>
                        <SelectItem value="done">Done</SelectItem>
                        <SelectItem value="blocked">Blocked</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  {task.subtasks?.length > 0 && (
                    <div className="pt-3 border-t border-white/5">
                      <p className="text-xs text-white/60 mb-1.5">
                        Subtasks ({task.subtasks.filter((s) => s.status === 'done').length}/{task.subtasks.length})
                      </p>
                      <div className="space-y-1">
                        {task.subtasks.map((s) => (
                          <div key={s.id} className="flex items-center gap-2 text-xs">
                            {s.status === 'done'
                              ? <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />
                              : <Circle className="h-3.5 w-3.5 text-white/30" />}
                            <span className={s.status === 'done' ? 'line-through text-white/40' : 'text-white/80'}>
                              {s.title}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
