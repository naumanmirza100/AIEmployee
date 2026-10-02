import React, { useState } from 'react';
import { labelOf } from '@/utils/labels';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/components/ui/use-toast';
import pmAgentService from '@/services/pmAgentService';
import { apiErrorMessage, toastForError } from '@/utils/apiErrorMessage';
import { Loader2, Target, ListChecks, AlertTriangle, Users } from 'lucide-react';
import ProgressLoader from '@/components/common/ProgressLoader';
import InfoHint from '../frontline/InfoHint';
import PMEmptyState from './EmptyState';
import { PM_HINTS } from './pmTutorialSteps';
import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';

// Per-action progress configuration. The LLM call is opaque so we can't show
// real percent-done — instead we show phase-based status hints that flip on
// real elapsed-time thresholds, calibrated to what each action actually does.
const PROGRESS_PRESETS = {
  prioritize_and_order: {
    title: 'Prioritising & ordering tasks',
    typicalSeconds: 75,
    phases: [
      { at: 0,  label: 'Reading project tasks…' },
      { at: 5,  label: 'Scoring task priorities…' },
      { at: 25, label: 'Computing execution order & parallel groups…' },
      { at: 50, label: 'Building strategy summary…' },
      { at: 70, label: 'Almost done — finalising…' },
    ],
  },
  bottlenecks: {
    title: 'Finding bottlenecks',
    typicalSeconds: 30,
    phases: [
      { at: 0,  label: 'Reading workload + dependencies…' },
      { at: 5,  label: 'AI analysing risk + resource overload…' },
      { at: 20, label: 'Drafting resolution strategies…' },
    ],
  },
  delegation: {
    title: 'Suggesting delegation',
    typicalSeconds: 35,
    phases: [
      { at: 0,  label: 'Reading team workload + skills…' },
      { at: 5,  label: 'Matching tasks to best-fit owners…' },
      { at: 20, label: 'Calculating workload rebalance…' },
    ],
  },
  generate_subtasks: {
    title: 'Generating subtasks',
    typicalSeconds: 70,
    phases: [
      { at: 0,  label: 'Reading project tasks…' },
      { at: 5,  label: 'AI breaking down each task into subtasks…' },
      { at: 30, label: 'Generating 70+ subtasks — this is the slow part…' },
      { at: 60, label: 'Getting them ready for you to review…' },
    ],
  },
};

const TaskPrioritizationAgent = ({ projects = [], onOpenPilot }) => {
  const [selectedProjectId, setSelectedProjectId] = useState('');
  const [action, setAction] = useState('prioritize');
  const [loading, setLoading] = useState(false);
  // Which action is currently running — drives the phase preset shown in the
  // ProgressLoader. Distinct from `action` (the user's last *clicked* action)
  // so the loader doesn't flicker labels if the user clicks while one runs.
  const [runningAction, setRunningAction] = useState(null);
  const [result, setResult] = useState(null);
  const { toast } = useToast();
  // Suggestions are reviewed before anything changes: the ticked priority
  // changes, and the kept subtasks per task (task_id -> Set of indexes).
  const [pickedPriorities, setPickedPriorities] = useState(() => new Set());
  const [prioritiesApplied, setPrioritiesApplied] = useState(false);
  const [keptSubtasks, setKeptSubtasks] = useState({});
  const [subtasksSaved, setSubtasksSaved] = useState(false);
  const [applying, setApplying] = useState(false);

  const startReview = (data) => {
    setPickedPriorities(new Set((data?.priority_changes || []).map((c) => c.task_id)));
    setPrioritiesApplied(false);
    setKeptSubtasks(Object.fromEntries((data?.proposals || []).map((p) => [
      p.task_id, new Set(p.subtasks.map((_, i) => i)),
    ])));
    setSubtasksSaved(false);
  };

  const applyPriorities = async () => {
    const changes = (result?.data?.priority_changes || [])
      .filter((c) => pickedPriorities.has(c.task_id))
      .map((c) => ({ task_id: c.task_id, priority: c.to }));
    if (!changes.length) return;
    setApplying(true);
    try {
      const res = await pmAgentService.applyTaskPriorities(changes);
      const failed = res.data?.failed || [];
      setPrioritiesApplied(true);
      toast({
        title: failed.length ? 'Some priorities not changed' : 'Priorities updated',
        description: `${res.data?.updated?.length || 0} changed${failed.length ? `, ${failed.length} refused: ${failed[0].error}` : ''}.`,
        variant: failed.length ? 'destructive' : undefined,
      });
    } catch (error) {
      toast(toastForError(error, 'Could not change the priorities'));
    } finally {
      setApplying(false);
    }
  };

  const keptCount = Object.values(keptSubtasks).reduce((n, set) => n + set.size, 0);

  const saveSubtasks = async () => {
    const proposals = (result?.data?.proposals || [])
      .map((p) => ({
        task_id: p.task_id,
        reasoning: p.reasoning,
        subtasks: p.subtasks.filter((_, i) => keptSubtasks[p.task_id]?.has(i)),
      }))
      .filter((p) => p.subtasks.length);
    if (!proposals.length) return;
    setApplying(true);
    try {
      const res = await pmAgentService.saveGeneratedSubtasks(proposals);
      setSubtasksSaved(true);
      toast({ title: 'Subtasks saved', description: `${res.data?.saved_count || 0} added. Find them under each task on the Tasks tab.` });
    } catch (error) {
      toast(toastForError(error, 'Could not save the subtasks'));
    } finally {
      setApplying(false);
    }
  };

  const toggleIn = (set, value) => {
    const next = new Set(set);
    if (next.has(value)) next.delete(value); else next.add(value);
    return next;
  };

  // Ensure projects is always an array
  const safeProjects = Array.isArray(projects) ? projects : [];

  // UX-15 / UX-16: refuse to run any Prioritization action against a project
  // that currently has 0 tasks — the LLM used to be invoked with an empty
  // list and return an empty / confusing "success" result. `tasks_count`
  // is populated by the /project-manager/dashboard endpoint.
  const selectedProject = safeProjects.find(
    (p) => String(p.id) === String(selectedProjectId),
  );
  const selectedProjectTaskCount = Number(selectedProject?.tasks_count ?? 0);
  const projectHasNoTasks = !!selectedProject && selectedProjectTaskCount === 0;

  const actions = [
    { value: 'prioritize_and_order', label: 'Prioritize & Order Tasks', icon: Target },
    { value: 'bottlenecks', label: 'Find Bottlenecks', icon: AlertTriangle },
    { value: 'delegation', label: 'Suggest Delegation', icon: Users },
  ];

  const handleAction = async (selectedAction) => {
    if (!selectedProjectId && projects.length > 0) {
      toast({
        title: 'Error',
        description: 'Please select a project',
        variant: 'destructive',
      });
      return;
    }

    try {
      setLoading(true);
      setResult(null);
      setAction(selectedAction);
      setRunningAction(selectedAction);

      const response = await pmAgentService.taskPrioritization(
        selectedAction,
        selectedProjectId || null
      );

      if (response.status === 'success') {
        setResult(response);
        startReview(response.data);
        const n = response.data?.priority_changes?.length || 0;
        toast({
          title: 'Analysis ready',
          description: n ? `${n} priority change${n === 1 ? '' : 's'} suggested — review them below.` : 'Task analysis completed',
        });
      } else {
        toast({
          title: 'Error',
          description: response.message || 'Failed to analyze tasks',
          variant: 'destructive',
        });
      }
    } catch (error) {
      console.error('Task Prioritization error:', error);
      toast(toastForError(error, 'Failed to analyze tasks'));
    } finally {
      setLoading(false);
      setRunningAction(null);
    }
  };

  const handleGenerateSubtasks = async () => {
    if (!selectedProjectId) {
      toast({
        title: 'Error',
        description: 'Please select a project',
        variant: 'destructive',
      });
      return;
    }

    try {
      setLoading(true);
      setResult(null);
      setRunningAction('generate_subtasks');

      const response = await pmAgentService.generateSubtasks(selectedProjectId);

      if (response.status === 'success') {
        setResult(response);
        startReview(response.data);
        const n = response.data?.proposed_count || 0;
        toast({
          title: n ? 'Subtasks ready to review' : 'Nothing to add',
          description: n ? `${n} proposed — keep the ones you want, then save.` : (response.message || 'No new subtasks.'),
        });
      } else {
        toast({
          title: 'Error',
          description: response.message || 'Failed to generate subtasks',
          variant: 'destructive',
        });
      }
    } catch (error) {
      console.error('Generate Subtasks error:', error);
      toast({
        title: 'Error',
        description: apiErrorMessage(error, 'Failed to generate subtasks'),
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
      setRunningAction(null);
    }
  };

  // Nothing on this tab works without at least one project — the dropdown is
  // empty, every action button stays disabled. Instead of a dead form, show
  // a clear CTA to create a project via Pilot first.
  if (safeProjects.length === 0) {
    return (
      <div className="space-y-6">
        <PMEmptyState
          title="Create a project first"
          subtitle="Task Prioritization ranks, finds bottlenecks in, and suggests delegation for tasks inside a project. Start one in Pilot to unlock this tab."
          onOpenPilot={onOpenPilot}
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Card className="border-white/10 bg-pure-black/20 backdrop-blur-sm">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Target className="h-5 w-5 text-violet-400" />
            Task Prioritization Agent
          </CardTitle>
          <CardDescription>
            Prioritize tasks, find bottlenecks, suggest order, and delegation strategies
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div data-tour-pm-tp="project-select">
            <label className="text-sm font-medium mb-2 flex items-center gap-1.5">
              Select Project
              <InfoHint {...PM_HINTS.pmTpProjectSelect} />
            </label>
            <Select value={selectedProjectId || "none"} onValueChange={setSelectedProjectId} disabled={safeProjects.length === 0}>
              <SelectTrigger>
                <SelectValue placeholder="Select a project" />
              </SelectTrigger>
              <SelectContent>
                {safeProjects.length > 0 ? (
                  safeProjects.map((project) => {
                    const tc = Number(project.tasks_count ?? 0);
                    return (
                      <SelectItem key={project.id} value={String(project.id)}>
                        {project.title || project.name}
                        {tc === 0 ? ' — 0 tasks' : ''}
                      </SelectItem>
                    );
                  })
                ) : (
                  <SelectItem value="none" disabled>No projects available</SelectItem>
                )}
              </SelectContent>
            </Select>
            {/* UX-15 / UX-16: explain why the action buttons below are
                disabled so the user knows the fix (create tasks first). */}
            {projectHasNoTasks && (
              <p className="text-xs text-amber-600 mt-2 flex items-center gap-1.5">
                <AlertTriangle className="h-3.5 w-3.5" />
                This project has no tasks yet — create at least one task before
                prioritising or generating subtasks.
              </p>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {actions.map((actionItem) => {
              const Icon = actionItem.icon;
              const hintKey = actionItem.value === 'prioritize_and_order' ? 'pmTpActionPrioritize'
                : actionItem.value === 'bottlenecks' ? 'pmTpActionBottlenecks'
                : 'pmTpActionDelegation';
              const anchor = actionItem.value === 'prioritize_and_order' ? 'action-prioritize'
                : actionItem.value === 'bottlenecks' ? 'action-bottlenecks'
                : 'action-delegation';
              return (
                <div key={actionItem.value} data-tour-pm-tp={anchor} className="flex items-center gap-1.5">
                  <Button
                    variant={action === actionItem.value ? 'default' : 'outline'}
                    onClick={() => handleAction(actionItem.value)}
                    disabled={loading || !selectedProjectId || projectHasNoTasks}
                    className="justify-start flex-1"
                  >
                    <Icon className="h-4 w-4 mr-2" />
                    {actionItem.label}
                  </Button>
                  <InfoHint {...PM_HINTS[hintKey]} />
                </div>
              );
            })}
          </div>

          <div data-tour-pm-tp="generate-subtasks" className="flex items-center gap-1.5">
          <Button
            variant="outline"
            onClick={handleGenerateSubtasks}
            disabled={loading || !selectedProjectId || projectHasNoTasks}
            className="w-full"
          >
            {loading && runningAction === 'generate_subtasks' ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Generating...
              </>
            ) : (
              <>
                <ListChecks className="h-4 w-4 mr-2" />
                Generate Subtasks
              </>
            )}
          </Button>
          <InfoHint {...PM_HINTS.pmTpGenerateSubtasks} />
          </div>
        </CardContent>
      </Card>

      {/* Long-running LLM call indicator. The underlying request is a single
          HTTP call — no real progress data — but we show elapsed time +
          phase-based status hints so the user knows the AI is still working
          (these actions normally take 30-90s and previously felt frozen). */}
      <ProgressLoader
        active={loading && !!runningAction}
        title={(PROGRESS_PRESETS[runningAction] || {}).title || 'Working…'}
        phases={(PROGRESS_PRESETS[runningAction] || {}).phases}
        typicalSeconds={(PROGRESS_PRESETS[runningAction] || {}).typicalSeconds || 60}
      />

      {result && (
        <Card data-tour-pm-tp="results" className="border-white/10 bg-pure-black/20 backdrop-blur-sm">
          <CardHeader>
            <CardTitle className="flex items-center gap-1.5">Analysis Results <InfoHint {...PM_HINTS.pmTpResults} /></CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Suggested priority changes: nothing changes until applied. */}
            {result.data?.priority_changes?.length > 0 && (
              <div className="rounded-lg border border-violet-500/30 bg-white/[0.03] p-4 space-y-3">
                <div>
                  <p className="text-sm font-medium text-foreground">Suggested priority changes</p>
                  <p className="text-xs text-muted-foreground">Nothing has changed yet. Untick any you don&apos;t want, then apply.</p>
                </div>
                <div className="space-y-1">
                  {result.data.priority_changes.map((c) => (
                    <label key={c.task_id} className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={pickedPriorities.has(c.task_id)}
                        disabled={prioritiesApplied || applying}
                        onChange={() => setPickedPriorities((s) => toggleIn(s, c.task_id))}
                      />
                      <span className="text-foreground">{c.title}</span>
                      <span className="text-muted-foreground">{c.from_label} → <span className="font-medium text-foreground">{c.to_label}</span></span>
                    </label>
                  ))}
                </div>
                {prioritiesApplied ? (
                  <p className="text-sm text-emerald-500">Applied.</p>
                ) : (
                  <Button size="sm" disabled={applying || pickedPriorities.size === 0} onClick={applyPriorities}>
                    {applying ? 'Applying…' : `Apply ${pickedPriorities.size} change${pickedPriorities.size === 1 ? '' : 's'}`}
                  </Button>
                )}
              </div>
            )}

            {/* Tasks with priorities and order - SHOW FIRST */}
            {result.data?.tasks && result.data.tasks.length > 0 && (
              <div className="space-y-3 mb-6">
                <p className="text-sm font-medium">
                  {action === 'prioritize_and_order' ? 'Task Execution Order:' : 'Task Priorities:'}
                </p>
                {result.data.tasks.map((task, index) => (
                  <div
                    key={task.id || index}
                    className="p-4 border rounded-lg bg-white/[0.03]"
                  >
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2 flex-wrap">
                          {action === 'prioritize_and_order' && task.execution_order && (
                            <Badge variant="outline" className="bg-primary/10 text-violet-400 border-primary/30">
                              Order: {task.execution_order}
                            </Badge>
                          )}
                          <p className="font-medium">{task.title}</p>
                          {task.ai_priority && (
                            <Badge
                              variant={
                                task.ai_priority === 'high'
                                  ? 'destructive'
                                  : task.ai_priority === 'medium'
                                  ? 'default'
                                  : 'secondary'
                              }
                            >
                              {task.ai_priority.toUpperCase()}
                            </Badge>
                          )}
                          {task.priority_score && (
                            <Badge variant="outline">
                              Score: {task.priority_score}
                            </Badge>
                          )}
                          {task.parallel_group && (
                            <Badge variant="outline" className="text-xs bg-violet-500/10 text-violet-400 border-violet-500/30">
                              Parallel Group: {task.parallel_group}
                            </Badge>
                          )}
                          {task.milestone_phase && (
                            <Badge variant="outline" className="text-xs bg-emerald-500/10 text-emerald-400 border-emerald-500/30">
                              {task.milestone_phase}
                            </Badge>
                          )}
                        </div>
                        <div className="flex gap-2 flex-wrap">
                          {task.business_value && (
                            <Badge variant="outline" className="text-xs">
                              Value: {task.business_value}
                            </Badge>
                          )}
                          {task.risk_level && (
                            <Badge variant="outline" className="text-xs">
                              Risk: {labelOf(task.risk_level)}
                            </Badge>
                          )}
                          {task.impact_on_others && (
                            <Badge variant="outline" className="text-xs">
                              Impact: {task.impact_on_others}
                            </Badge>
                          )}
                          {task.time_to_completion_estimate && (
                            <Badge variant="outline" className="text-xs">
                              Est: {task.time_to_completion_estimate} days
                            </Badge>
                          )}
                          {task.buffer_recommended > 0 && (
                            <Badge variant="outline" className="text-xs">
                              Buffer: {task.buffer_recommended} days
                            </Badge>
                          )}
                        </div>
                      </div>
                    </div>
                    {task.ai_reasoning && (
                      <div className="mt-3 p-3 bg-muted rounded-lg">
                        <p className="text-xs font-medium mb-1 text-muted-foreground">Reasoning:</p>
                        <p className="text-sm text-muted-foreground whitespace-pre-wrap">
                          {task.ai_reasoning}
                        </p>
                      </div>
                    )}
                    {task.actionable_recommendations && task.actionable_recommendations.length > 0 && (
                      <div className="mt-3">
                        <p className="text-sm font-medium mb-1">Actionable Recommendations:</p>
                        <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1">
                          {task.actionable_recommendations.map((rec, idx) => (
                            <li key={idx}>{rec}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Combined Prioritize and Order Action - Comprehensive Analysis */}
            {action === 'prioritize_and_order' && result.data?.combined_analysis && (
              <div className="space-y-4 mb-6">
                {/* Overall Combined Reasoning */}
                <div className="p-4 border rounded-lg bg-white/[0.03] border-primary/30">
                  <p className="text-sm font-medium mb-2 text-violet-400">Overall Strategy - Why This Approach is Optimal:</p>
                  <p className="text-sm text-muted-foreground whitespace-pre-wrap">{result.data.combined_analysis.overall_reasoning}</p>
                </div>
                
                {/* Strategic Benefits */}
                {result.data.combined_analysis.strategic_benefits && result.data.combined_analysis.strategic_benefits.length > 0 && (
                  <div className="p-4 border rounded-lg bg-white/[0.03] border-amber-500/30">
                    <p className="text-sm font-medium mb-2 text-amber-400">Strategic Benefits:</p>
                    <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1">
                      {result.data.combined_analysis.strategic_benefits.map((benefit, idx) => (
                        <li key={idx}>{benefit}</li>
                      ))}
                    </ul>
                  </div>
                )}
                
                {/* Efficiency Benefits */}
                {result.data.combined_analysis.efficiency_benefits && result.data.combined_analysis.efficiency_benefits.length > 0 && (
                  <div className="p-4 border rounded-lg bg-white/[0.03] border-amber-500/30">
                    <p className="text-sm font-medium mb-2 text-amber-400">Efficiency Benefits:</p>
                    <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1">
                      {result.data.combined_analysis.efficiency_benefits.map((benefit, idx) => (
                        <li key={idx}>{benefit}</li>
                      ))}
                    </ul>
                  </div>
                )}
                
                {/* Synergistic Benefits */}
                {result.data.combined_analysis.synergistic_benefits && result.data.combined_analysis.synergistic_benefits.length > 0 && (
                  <div className="p-4 border rounded-lg bg-white/[0.03] border-violet-500/30">
                    <p className="text-sm font-medium mb-2 text-violet-400">Integrated Benefits:</p>
                    <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1">
                      {result.data.combined_analysis.synergistic_benefits.map((benefit, idx) => (
                        <li key={idx}>{benefit}</li>
                      ))}
                    </ul>
                  </div>
                )}
                
                {/* Strategic Insights */}
                {result.data.combined_analysis.key_strategic_insights && result.data.combined_analysis.key_strategic_insights.length > 0 && (
                  <div className="p-4 border rounded-lg bg-white/[0.03] border-violet-500/30">
                    <p className="text-sm font-medium mb-2 text-violet-400">Key Strategic Insights:</p>
                    <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1">
                      {result.data.combined_analysis.key_strategic_insights.map((insight, idx) => (
                        <li key={idx}>{insight}</li>
                      ))}
                    </ul>
                  </div>
                )}
                
                {/* Execution Recommendations */}
                {result.data.combined_analysis.execution_recommendations && result.data.combined_analysis.execution_recommendations.length > 0 && (
                  <div className="p-4 border rounded-lg bg-white/[0.03] border-emerald-500/30">
                    <p className="text-sm font-medium mb-2 text-emerald-400">Execution Recommendations:</p>
                    <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1">
                      {result.data.combined_analysis.execution_recommendations.map((rec, idx) => (
                        <li key={idx}>{rec}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
            
            {/* Prioritization Section */}
            {action === 'prioritize_and_order' && result.data?.prioritization && (
              <div className="space-y-4 mb-6">
                {result.data.prioritization.summary && (
                  <>
                    <div className="p-4 border rounded-lg bg-white/[0.03] border-primary/30">
                      <p className="text-sm font-medium mb-2 text-violet-400">Prioritization Strategy:</p>
                      <p className="text-sm text-muted-foreground">{result.data.prioritization.summary.prioritization_strategy}</p>
                    </div>
                    
                    {result.data.prioritization.summary.key_insights && result.data.prioritization.summary.key_insights.length > 0 && (
                      <div className="p-4 border rounded-lg bg-white/[0.03] border-violet-500/30">
                        <p className="text-sm font-medium mb-2 text-violet-400">Prioritization Insights:</p>
                        <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1">
                          {result.data.prioritization.summary.key_insights.map((insight, idx) => (
                            <li key={idx}>{insight}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </>
                )}
                
                {result.data.prioritization.statistics && (
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="p-3 border rounded-lg bg-white/[0.03] border-white/[0.08]">
                      <div className="text-2xl font-bold">{result.data.prioritization.statistics.total_tasks || 0}</div>
                      <div className="text-sm text-muted-foreground">Total Tasks</div>
                    </div>
                    <div className="p-3 border rounded-lg bg-white/[0.03] border-red-500/30">
                      <div className="text-2xl font-bold text-red-400">{result.data.prioritization.statistics.high_priority || 0}</div>
                      <div className="text-sm text-muted-foreground">High Priority</div>
                    </div>
                    <div className="p-3 border rounded-lg bg-white/[0.03] border-amber-500/30">
                      <div className="text-2xl font-bold text-amber-400">{result.data.prioritization.statistics.medium_priority || 0}</div>
                      <div className="text-sm text-muted-foreground">Medium Priority</div>
                    </div>
                    <div className="p-3 border rounded-lg bg-white/[0.03] border-emerald-500/30">
                      <div className="text-2xl font-bold text-emerald-400">{result.data.prioritization.statistics.low_priority || 0}</div>
                      <div className="text-sm text-muted-foreground">Low Priority</div>
                    </div>
                  </div>
                )}
              </div>
            )}
            
            {/* Ordering Section */}
            {action === 'prioritize_and_order' && result.data?.ordering && (
              <div className="space-y-4 mb-6">
                {result.data.ordering.summary && (
                  <div className="p-4 border rounded-lg bg-white/[0.03] border-primary/30">
                    <p className="text-sm font-medium mb-2 text-violet-400">Execution Order Optimization:</p>
                    <div className="grid grid-cols-2 gap-4 mt-2">
                      <div>
                        <p className="text-xs text-muted-foreground">Sequential Duration</p>
                        <p className="text-lg font-bold">{result.data.ordering.summary.total_sequential_days || 0} days</p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground">Optimized Duration</p>
                        <p className="text-lg font-bold text-emerald-400">{result.data.ordering.summary.optimized_duration_days || 0} days</p>
                      </div>
                    </div>
                    {result.data.ordering.summary.parallel_execution_saves_days > 0 && (
                      <p className="text-sm text-emerald-400 mt-2">
                        Saves {result.data.ordering.summary.parallel_execution_saves_days} days through parallelization
                      </p>
                    )}
                    {result.data.ordering.summary.overall_reasoning && (
                      <div className="mt-3 p-3 bg-muted rounded-lg">
                        <p className="text-sm font-medium mb-1">Why This Order:</p>
                        <p className="text-sm text-muted-foreground whitespace-pre-wrap">{result.data.ordering.summary.overall_reasoning}</p>
                      </div>
                    )}
                  </div>
                )}
                
                {result.data.ordering.parallel_groups && result.data.ordering.parallel_groups.length > 0 && (
                  <div className="p-4 border rounded-lg bg-white/[0.03] border-violet-500/30">
                    <p className="text-sm font-medium mb-2 text-violet-400">Parallel Execution Groups:</p>
                    {result.data.ordering.parallel_groups.map((group, idx) => (
                      <div key={idx} className="mt-3 p-3 bg-muted rounded-lg">
                        <p className="text-sm font-medium">Group {group.group_id}</p>
                        <p className="text-xs text-muted-foreground mt-1">{group.reasoning}</p>
                      </div>
                    ))}
                  </div>
                )}
                
                {result.data.ordering.milestones && result.data.ordering.milestones.length > 0 && (
                  <div className="p-4 border rounded-lg bg-white/[0.03] border-emerald-500/30">
                    <p className="text-sm font-medium mb-2 text-emerald-400">Project Milestones:</p>
                    {result.data.ordering.milestones.map((milestone, idx) => (
                      <div key={idx} className="mt-3 p-3 bg-muted rounded-lg">
                        <p className="text-sm font-medium">{milestone.phase}</p>
                        <p className="text-xs text-muted-foreground mt-1">{milestone.description}</p>
                        <p className="text-xs text-muted-foreground mt-1">
                          Duration: {milestone.estimated_duration_days} days
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
            
            {/* Prioritize Action - Summary and Statistics (Legacy - for backward compatibility) */}
            {action === 'prioritize' && result.data?.summary && (
              <div className="space-y-4 mb-6">
                <div className="p-4 border rounded-lg bg-white/[0.03] border-primary/30">
                  <p className="text-sm font-medium mb-2 text-violet-400">Prioritization Strategy:</p>
                  <p className="text-sm text-muted-foreground">{result.data.summary.prioritization_strategy}</p>
                </div>
                
                {result.data.summary.overall_reasoning && (
                  <div className="p-4 border rounded-lg bg-white/[0.03] border-violet-500/30">
                    <p className="text-sm font-medium mb-2 text-violet-400">Overall Reasoning - Why This Prioritization is Better:</p>
                    <p className="text-sm text-muted-foreground whitespace-pre-wrap">{result.data.summary.overall_reasoning}</p>
                  </div>
                )}
                
                {result.data.summary.key_insights && result.data.summary.key_insights.length > 0 && (
                  <div className="p-4 border rounded-lg bg-white/[0.03] border-violet-500/30">
                    <p className="text-sm font-medium mb-2 text-violet-400">Key Insights:</p>
                    <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1">
                      {result.data.summary.key_insights.map((insight, idx) => (
                        <li key={idx}>{insight}</li>
                      ))}
                    </ul>
                  </div>
                )}
                
                {result.data.summary.top_recommendations && result.data.summary.top_recommendations.length > 0 && (
                  <div className="p-4 border rounded-lg bg-white/[0.03] border-emerald-500/30">
                    <p className="text-sm font-medium mb-2 text-emerald-400">Top Recommendations:</p>
                    <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1">
                      {result.data.summary.top_recommendations.map((rec, idx) => (
                        <li key={idx}>{rec}</li>
                      ))}
                    </ul>
                  </div>
                )}
                
                {result.data.summary.risk_alerts && result.data.summary.risk_alerts.length > 0 && (
                  <div className="p-4 border rounded-lg bg-white/[0.03] border-red-500/30">
                    <p className="text-sm font-medium mb-2 text-red-400">Risk Alerts:</p>
                    <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1">
                      {result.data.summary.risk_alerts.map((alert, idx) => (
                        <li key={idx}>{alert}</li>
                      ))}
                    </ul>
                  </div>
                )}
                
                {result.data.summary.workload_concerns && (
                  <div className="p-4 border rounded-lg bg-white/[0.03] border-amber-500/30">
                    <p className="text-sm font-medium mb-2 text-amber-400">Workload Concerns:</p>
                    <p className="text-sm text-muted-foreground">{result.data.summary.workload_concerns}</p>
                  </div>
                )}
                
                {result.data?.statistics && (
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="p-3 border rounded-lg bg-white/[0.03] border-white/[0.08]">
                      <div className="text-2xl font-bold">{result.data.statistics.total_tasks || 0}</div>
                      <div className="text-sm text-muted-foreground">Total Tasks</div>
                    </div>
                    <div className="p-3 border rounded-lg bg-white/[0.03] border-red-500/30">
                      <div className="text-2xl font-bold text-red-400">{result.data.statistics.high_priority || 0}</div>
                      <div className="text-sm text-muted-foreground">High Priority</div>
                    </div>
                    <div className="p-3 border rounded-lg bg-white/[0.03] border-amber-500/30">
                      <div className="text-2xl font-bold text-amber-400">{result.data.statistics.medium_priority || 0}</div>
                      <div className="text-sm text-muted-foreground">Medium Priority</div>
                    </div>
                    <div className="p-3 border rounded-lg bg-white/[0.03] border-emerald-500/30">
                      <div className="text-2xl font-bold text-emerald-400">{result.data.statistics.low_priority || 0}</div>
                      <div className="text-sm text-muted-foreground">Low Priority</div>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Order Action - Parallel Groups and Milestones */}
            {action === 'order' && result.data?.parallel_groups && result.data.parallel_groups.length > 0 && (
              <div className="space-y-4 mb-6">
                <div className="p-4 border rounded-lg bg-white/[0.03] border-violet-500/30">
                  <p className="text-sm font-medium mb-2 text-violet-400">Parallel Execution Groups:</p>
                  {result.data.parallel_groups.map((group, idx) => (
                    <div key={idx} className="mt-3 p-3 bg-muted rounded-lg">
                      <p className="text-sm font-medium">Group {group.group_id}</p>
                      <p className="text-xs text-muted-foreground mt-1">{group.reasoning}</p>
                    </div>
                  ))}
                </div>
                
                {result.data.milestones && result.data.milestones.length > 0 && (
                  <div className="p-4 border rounded-lg bg-white/[0.03] border-emerald-500/30">
                    <p className="text-sm font-medium mb-2 text-emerald-400">Project Milestones:</p>
                    {result.data.milestones.map((milestone, idx) => (
                      <div key={idx} className="mt-3 p-3 bg-muted rounded-lg">
                        <p className="text-sm font-medium">{milestone.phase}</p>
                        <p className="text-xs text-muted-foreground mt-1">{milestone.description}</p>
                        <p className="text-xs text-muted-foreground mt-1">
                          Duration: {milestone.estimated_duration_days} days
                        </p>
                      </div>
                    ))}
                  </div>
                )}
                
                {result.data.summary && (
                  <div className="space-y-4">
                    <div className="p-4 border rounded-lg bg-white/[0.03] border-primary/30">
                      <p className="text-sm font-medium mb-2 text-violet-400">Optimization Summary:</p>
                      <div className="grid grid-cols-2 gap-4 mt-2">
                        <div>
                          <p className="text-xs text-muted-foreground">Sequential Duration</p>
                          <p className="text-lg font-bold">{result.data.summary.total_sequential_days || 0} days</p>
                        </div>
                        <div>
                          <p className="text-xs text-muted-foreground">Optimized Duration</p>
                          <p className="text-lg font-bold text-emerald-400">{result.data.summary.optimized_duration_days || 0} days</p>
                        </div>
                      </div>
                      {result.data.summary.parallel_execution_saves_days > 0 && (
                        <p className="text-sm text-emerald-400 mt-2">
                          Saves {result.data.summary.parallel_execution_saves_days} days through parallelization
                        </p>
                      )}
                    </div>
                    
                    {result.data.summary.overall_reasoning && (
                      <div className="p-4 border rounded-lg bg-white/[0.03] border-violet-500/30">
                        <p className="text-sm font-medium mb-2 text-violet-400">Overall Reasoning - Why This Order is Better:</p>
                        <p className="text-sm text-muted-foreground whitespace-pre-wrap">{result.data.summary.overall_reasoning}</p>
                      </div>
                    )}
                    
                    {result.data.summary.optimization_benefits && result.data.summary.optimization_benefits.length > 0 && (
                      <div className="p-4 border rounded-lg bg-white/[0.03] border-emerald-500/30">
                        <p className="text-sm font-medium mb-2 text-emerald-400">Optimization Benefits:</p>
                        <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1">
                          {result.data.summary.optimization_benefits.map((benefit, idx) => (
                            <li key={idx}>{benefit}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Bottlenecks */}
            {(result.data?.bottlenecks || result.data?.analysis?.bottlenecks) && (
              <div className="space-y-4">
                {result.data?.summary && (
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                    <div className="p-3 border rounded-lg bg-white/[0.03] border-white/[0.08]">
                      <div className="text-2xl font-bold">{result.data.summary.total_bottlenecks || 0}</div>
                      <div className="text-sm text-muted-foreground">Total Bottlenecks</div>
                    </div>
                    <div className="p-3 border rounded-lg bg-white/[0.03] border-red-500/30">
                      <div className="text-2xl font-bold text-red-400">{result.data.summary.critical_count || 0}</div>
                      <div className="text-sm text-muted-foreground">Critical</div>
                    </div>
                    <div className="p-3 border rounded-lg bg-white/[0.03] border-amber-500/30">
                      <div className="text-2xl font-bold text-amber-400">{result.data.summary.high_count || 0}</div>
                      <div className="text-sm text-muted-foreground">High</div>
                    </div>
                    <div className="p-3 border rounded-lg bg-white/[0.03] border-amber-500/30">
                      <div className="text-2xl font-bold text-amber-400">
                        {result.data.summary.estimated_project_delay_days || 0}
                      </div>
                      <div className="text-sm text-muted-foreground">Days Delay</div>
                    </div>
                  </div>
                )}
                
                {(result.data?.bottlenecks || result.data?.analysis?.bottlenecks || []).map((bottleneck, index) => (
                  <div
                    key={index}
                    className={`p-4 border rounded-lg bg-white/[0.03] ${
                      bottleneck.severity === 'critical'
                        ? 'border-red-500/30'
                        : bottleneck.severity === 'high'
                        ? 'border-amber-500/30'
                        : bottleneck.severity === 'medium'
                        ? 'border-amber-500/30'
                        : 'border-white/[0.08]'
                    }`}
                  >
                    <div className="flex items-start justify-between mb-2">
                      <div>
                        <p className="font-medium">{bottleneck.description || bottleneck.type}</p>
                        <div className="flex gap-2 mt-1">
                          <Badge variant={
                            bottleneck.severity === 'critical' ? 'destructive' :
                            bottleneck.severity === 'high' ? 'default' : 'secondary'
                          }>
                            {bottleneck.severity || 'medium'}
                          </Badge>
                          {bottleneck.severity_score && (
                            <Badge variant="outline">Score: {bottleneck.severity_score}</Badge>
                          )}
                          {bottleneck.priority && (
                            <Badge variant="outline">{bottleneck.priority} priority</Badge>
                          )}
                        </div>
                      </div>
                    </div>
                    
                    {bottleneck.impact_analysis && (
                      <div className="mt-3 p-3 bg-muted rounded-lg">
                        <p className="text-sm font-medium mb-1">Impact Analysis:</p>
                        <p className="text-sm text-muted-foreground">{bottleneck.impact_analysis}</p>
                      </div>
                    )}
                    
                    {bottleneck.root_cause && (
                      <div className="mt-3">
                        <p className="text-sm font-medium mb-1">Root Cause:</p>
                        <p className="text-sm text-muted-foreground">{bottleneck.root_cause}</p>
                      </div>
                    )}
                    
                    {bottleneck.resolution_strategy && bottleneck.resolution_strategy.length > 0 && (
                      <div className="mt-3">
                        <p className="text-sm font-medium mb-1 text-emerald-400">Resolution Strategy:</p>
                        <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1">
                          {bottleneck.resolution_strategy.map((step, idx) => (
                            <li key={idx}>{step}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    
                    {bottleneck.preventive_measures && bottleneck.preventive_measures.length > 0 && (
                      <div className="mt-3">
                        <p className="text-sm font-medium mb-1 text-violet-400">Preventive Measures:</p>
                        <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1">
                          {bottleneck.preventive_measures.map((measure, idx) => (
                            <li key={idx}>{measure}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    
                    {bottleneck.affected_tasks && bottleneck.affected_tasks.length > 0 && (
                      <div className="mt-3">
                        <p className="text-sm font-medium mb-1">Affected Tasks:</p>
                        {bottleneck.affected_tasks.map((at, idx) => (
                          <div key={idx} className="p-2 bg-muted rounded mt-1">
                            <p className="text-xs font-medium">Task {at.task_id}</p>
                            {at.task_reasoning && (
                              <p className="text-xs text-muted-foreground mt-1">{at.task_reasoning}</p>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
                
                {/* Workload Heatmap */}
                {result.data?.workload_heatmap && (
                  <div className="mt-6 space-y-4">
                    <p className="text-sm font-medium">Workload Heatmap:</p>
                    
                    {result.data.workload_heatmap.overloaded_members && result.data.workload_heatmap.overloaded_members.length > 0 && (
                      <div className="p-4 border rounded-lg bg-white/[0.03] border-red-500/30">
                        <p className="text-sm font-medium mb-2 text-red-400">Overloaded Members:</p>
                        {result.data.workload_heatmap.overloaded_members.map((member, idx) => (
                          <div key={idx} className="mt-2 p-2 bg-muted rounded">
                            <p className="text-sm font-medium">{member.member}</p>
                            <p className="text-xs text-muted-foreground">
                              {member.active_tasks} tasks, {member.total_hours}h ({member.capacity_utilization}% capacity)
                            </p>
                            {member.recommendation && (
                              <p className="text-xs text-muted-foreground mt-1">{member.recommendation}</p>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                    
                    {result.data.workload_heatmap.underutilized_members && result.data.workload_heatmap.underutilized_members.length > 0 && (
                      <div className="p-4 border rounded-lg bg-white/[0.03] border-emerald-500/30">
                        <p className="text-sm font-medium mb-2 text-emerald-400">Underutilized Members:</p>
                        {result.data.workload_heatmap.underutilized_members.map((member, idx) => (
                          <div key={idx} className="mt-2 p-2 bg-muted rounded">
                            <p className="text-sm font-medium">{member.member}</p>
                            <p className="text-xs text-muted-foreground">
                              {member.active_tasks} tasks, {member.total_hours}h ({member.capacity_utilization}% capacity)
                            </p>
                            {member.recommendation && (
                              <p className="text-xs text-muted-foreground mt-1">{member.recommendation}</p>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Delegation Suggestions - show when action is delegation (result has suggestions key or summary) */}
            {(action === 'delegation' && (Array.isArray(result.data?.suggestions) || result.data?.summary)) && (
              <div className="space-y-4">
                {result.data?.summary?.message && (
                  <div className="p-3 rounded-lg bg-muted/60 border border-white/[0.08] text-sm text-muted-foreground">
                    {result.data.summary.message}
                  </div>
                )}
                {result.data?.summary && (
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                    <div className="p-3 border rounded-lg bg-white/[0.03] border-white/[0.08]">
                      <div className="text-2xl font-bold">{result.data.summary.total_suggestions || 0}</div>
                      <div className="text-sm text-muted-foreground">Total Suggestions</div>
                    </div>
                    <div className="p-3 border rounded-lg bg-white/[0.03] border-violet-500/30">
                      <div className="text-2xl font-bold text-violet-400">{result.data.summary.new_assignments || 0}</div>
                      <div className="text-sm text-muted-foreground">New Assignments</div>
                    </div>
                    <div className="p-3 border rounded-lg bg-white/[0.03] border-amber-500/30">
                      <div className="text-2xl font-bold text-amber-400">{result.data.summary.reassignments || 0}</div>
                      <div className="text-sm text-muted-foreground">Reassignments</div>
                    </div>
                    <div className="p-3 border rounded-lg bg-white/[0.03] border-emerald-500/30">
                      <div className="text-2xl font-bold text-emerald-400">
                        {result.data.summary.workload_balance_improvement || 'N/A'}
                      </div>
                      <div className="text-sm text-muted-foreground">Balance Improvement</div>
                    </div>
                  </div>
                )}
                
                {(result.data?.suggestions || result.data?.suggestions?.suggestions || []).map((suggestion, index) => (
                  <div
                    key={index}
                    className="p-4 border rounded-lg bg-white/[0.03]"
                  >
                    <div className="flex items-start justify-between mb-2">
                      <div>
                        <p className="font-medium">{suggestion.task_title || `Task #${suggestion.task_id}`}</p>
                        <div className="flex gap-2 mt-1">
                          <Badge variant="outline">
                            → {suggestion.suggested_assignee}
                          </Badge>
                          {suggestion.delegation_type && (
                            <Badge variant="secondary">{labelOf(suggestion.delegation_type)}</Badge>
                          )}
                          {suggestion.skill_match_score && (
                            <Badge variant="outline">Match: {suggestion.skill_match_score}%</Badge>
                          )}
                          {suggestion.workload_impact && (
                            <Badge variant="outline">Impact: {suggestion.workload_impact}</Badge>
                          )}
                        </div>
                      </div>
                    </div>
                    
                    {suggestion.reasoning && (
                      <div className="mt-3 p-3 bg-muted rounded-lg">
                        <p className="text-sm text-muted-foreground whitespace-pre-wrap">
                          {suggestion.reasoning}
                        </p>
                      </div>
                    )}
                    
                    {suggestion.support_needed && suggestion.support_needed.length > 0 && (
                      <div className="mt-3">
                        <p className="text-sm font-medium mb-1">Support Needed:</p>
                        <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1">
                          {suggestion.support_needed.map((support, idx) => (
                            <li key={idx}>{support}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                ))}
                
                {/* Workload Analysis */}
                {result.data?.workload_analysis && (
                  <div className="mt-6 space-y-4">
                    <p className="text-sm font-medium">Workload Analysis:</p>
                    
                    {result.data.workload_analysis.before_delegation && (
                      <div className="p-4 border rounded-lg bg-white/[0.03] border-amber-500/30">
                        <p className="text-sm font-medium mb-2 text-amber-400">Before Delegation:</p>
                        {result.data.workload_analysis.before_delegation.overloaded_members && (
                          <p className="text-sm text-muted-foreground">
                            Overloaded: {result.data.workload_analysis.before_delegation.overloaded_members.join(', ')}
                          </p>
                        )}
                        {result.data.workload_analysis.before_delegation.underutilized_members && (
                          <p className="text-sm text-muted-foreground">
                            Underutilized: {result.data.workload_analysis.before_delegation.underutilized_members.join(', ')}
                          </p>
                        )}
                      </div>
                    )}
                    
                    {result.data.workload_analysis.after_delegation && (
                      <div className="p-4 border rounded-lg bg-white/[0.03] border-emerald-500/30">
                        <p className="text-sm font-medium mb-2 text-emerald-400">After Delegation:</p>
                        <p className="text-sm text-muted-foreground">
                          {result.data.workload_analysis.after_delegation.improvement || 'Workload balanced'}
                        </p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Subtask Generation Results (UX-16: tell the user WHERE the
                generated subtasks appear now — they nest under each task's
                row on the Tasks tab, and used to appear only as this toast). */}
            {Array.isArray(result.data?.proposals) && (
              result.data.proposals.length === 0 ? (
                <p className="text-sm text-muted-foreground">No new subtasks were generated.</p>
              ) : (
                <div className="rounded-lg border border-violet-500/30 bg-white/[0.03] p-4 space-y-3">
                  <div>
                    <p className="text-sm font-medium text-foreground">Proposed subtasks</p>
                    <p className="text-xs text-muted-foreground">
                      Nothing is saved yet. Untick any you don&apos;t want, then save — they&apos;ll nest under each task on the Tasks tab.
                    </p>
                  </div>
                  {result.data.proposals.map((p) => (
                    <div key={p.task_id} className="space-y-1">
                      <p className="text-sm font-medium text-foreground">{p.task_title}</p>
                      {p.subtasks.map((st, i) => (
                        <label key={i} className="flex items-start gap-2 pl-2 text-sm">
                          <input
                            type="checkbox"
                            className="mt-1"
                            checked={!!keptSubtasks[p.task_id]?.has(i)}
                            disabled={subtasksSaved || applying}
                            onChange={() => setKeptSubtasks((k) => ({ ...k, [p.task_id]: toggleIn(k[p.task_id] || new Set(), i) }))}
                          />
                          <span>
                            <span className="text-foreground">{st.title}</span>
                            {st.description && <span className="block text-xs text-muted-foreground">{st.description}</span>}
                          </span>
                        </label>
                      ))}
                    </div>
                  ))}
                  {subtasksSaved ? (
                    <p className="text-sm text-emerald-500">Saved — they&apos;re under each task on the <b>Tasks</b> tab.</p>
                  ) : (
                    <Button size="sm" disabled={applying || keptCount === 0} onClick={saveSubtasks}>
                      {applying ? 'Saving…' : `Save ${keptCount} subtask${keptCount === 1 ? '' : 's'}`}
                    </Button>
                  )}
                </div>
              )
            )}

            {/* General Answer */}
            {result.data?.answer && (
              <div className="p-4 bg-muted rounded-lg">
                <p className="text-sm font-medium mb-2">Analysis:</p>
                <p className="whitespace-pre-wrap text-sm">{result.data.answer}</p>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default TaskPrioritizationAgent;



