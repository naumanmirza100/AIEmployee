import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/components/ui/use-toast';
import pmAgentService from '@/services/pmAgentService';
import { apiErrorMessage, toastForError } from '@/utils/apiErrorMessage';
import { companyApi } from '@/services/companyAuthService';
import {
  Loader2, Workflow, CheckSquare, Square, ArrowRight, Lightbulb,
  AlertTriangle, ChevronDown, ChevronUp, Shield, Clock, ListChecks
} from 'lucide-react';

const PHASES = [
  { value: 'planning', label: 'Planning' },
  { value: 'requirements', label: 'Requirements' },
  { value: 'design', label: 'Design' },
  { value: 'development', label: 'Development' },
  { value: 'testing', label: 'Testing' },
  { value: 'deployment', label: 'Deployment' },
  { value: 'maintenance', label: 'Maintenance' },
];

export default function WorkflowSuggestionsView() {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [checklistLoading, setChecklistLoading] = useState(false);
  const [validateLoading, setValidateLoading] = useState(false);
  const [projects, setProjects] = useState([]);
  const [selectedProject, setSelectedProject] = useState(null);
  const [phase, setPhase] = useState('development');
  const [workflow, setWorkflow] = useState(null);
  const [checklist, setChecklist] = useState(null);
  const [validation, setValidation] = useState(null);
  const [checkedItems, setCheckedItems] = useState(new Set());
  const [expandedPhase, setExpandedPhase] = useState(null);

  useEffect(() => {
    const fetchProjects = async () => {
      try {
        const res = await companyApi.get('/company/projects/list');
        const data = res?.data?.data || res?.data?.results || res?.data || [];
        setProjects(Array.isArray(data) ? data : []);
      } catch (e) { console.error(e); }
    };
    fetchProjects();
  }, []);

  const fetchWorkflow = async () => {
    if (!selectedProject) {
      toast({ title: 'Error', description: 'Please select a project first.', variant: 'destructive' });
      return;
    }
    setLoading(true);
    setWorkflow(null);
    try {
      const res = await pmAgentService.workflowSuggest(selectedProject, 'suggest', phase);
      const data = res?.data?.data || res?.data || {};
      setWorkflow(data);
      // Auto-expand current phase
      if (data.current_phase) {
        setExpandedPhase(data.current_phase);
      }
    } catch (e) {
      toast({ title: 'Error', description: apiErrorMessage(e, 'Failed to get suggestions'), variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  const fetchChecklist = async () => {
    if (!selectedProject) {
      toast({ title: 'Error', description: 'Please select a project first.', variant: 'destructive' });
      return;
    }
    setChecklistLoading(true);
    setChecklist(null);
    setCheckedItems(new Set());
    try {
      const res = await pmAgentService.workflowSuggest(selectedProject, 'checklist', phase);
      const data = res?.data?.data || res?.data || {};
      setChecklist(data);
    } catch (e) {
      toast({ title: 'Error', description: apiErrorMessage(e, 'Failed to generate checklist'), variant: 'destructive' });
    } finally {
      setChecklistLoading(false);
    }
  };

  const fetchValidation = async () => {
    if (!selectedProject) {
      toast({ title: 'Error', description: 'Please select a project first.', variant: 'destructive' });
      return;
    }
    setValidateLoading(true);
    setValidation(null);
    try {
      const res = await pmAgentService.workflowSuggest(selectedProject, 'validate', phase);
      const data = res?.data?.data || res?.data || {};
      setValidation(data);
    } catch (e) {
      toast({ title: 'Error', description: apiErrorMessage(e, 'Failed to validate workflow'), variant: 'destructive' });
    } finally {
      setValidateLoading(false);
    }
  };

  const toggleCheck = (idx) => {
    setCheckedItems(prev => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  const checklistItems = checklist?.checklist || [];
  const checkedCount = checkedItems.size;
  const totalChecklistItems = checklistItems.length;
  const checklistProgress = totalChecklistItems > 0 ? Math.round((checkedCount / totalChecklistItems) * 100) : 0;

  const anyLoading = loading || checklistLoading || validateLoading;

  return (
    <div className="space-y-6">
      {/* Controls */}
      <Card className="bg-black/30 border-white/[0.06]">
        <CardHeader className="pb-3">
          <CardTitle className="text-lg text-violet-300 flex items-center gap-2">
            <Workflow className="w-5 h-5" /> Workflow & SOP
          </CardTitle>
          <CardDescription className="text-white/55">
            Get AI-powered workflow suggestions, phase checklists, and process validation
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col gap-3">
            <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
              <Select value={selectedProject || ''} onValueChange={(v) => setSelectedProject(v || null)}>
                <SelectTrigger className="flex-1 h-10 bg-white/[0.02] border-white/[0.08] text-white">
                  <SelectValue placeholder="Select a Project" />
                </SelectTrigger>
                <SelectContent className="bg-white/[0.02] border-white/[0.08] z-50">
                  {projects.map((p) => (
                    <SelectItem key={p.id} value={String(p.id)}>{p.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select value={phase} onValueChange={setPhase}>
                <SelectTrigger className="w-[160px] h-10 bg-white/[0.02] border-white/[0.08] text-white">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-white/[0.02] border-white/[0.08] z-50">
                  {PHASES.map((p) => (
                    <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button onClick={fetchWorkflow} disabled={anyLoading || !selectedProject} className="bg-violet-600 hover:bg-violet-700">
                {loading ? <><Loader2 className="w-4 h-4 animate-spin mr-2" /> Analyzing...</> : <><Lightbulb className="w-4 h-4 mr-2" /> Get Suggestions</>}
              </Button>
              <Button onClick={fetchChecklist} disabled={anyLoading || !selectedProject} variant="outline" className="border-amber-600 text-amber-300 hover:bg-amber-600/20">
                {checklistLoading ? <><Loader2 className="w-4 h-4 animate-spin mr-2" /> Loading...</> : <><ListChecks className="w-4 h-4 mr-2" /> Phase Checklist</>}
              </Button>
              <Button onClick={fetchValidation} disabled={anyLoading || !selectedProject} variant="outline" className="border-violet-600 text-violet-300 hover:bg-violet-600/20">
                {validateLoading ? <><Loader2 className="w-4 h-4 animate-spin mr-2" /> Checking...</> : <><Shield className="w-4 h-4 mr-2" /> Validate Process</>}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Loading */}
      {anyLoading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-violet-400" />
          <span className="ml-3 text-white/55">
            {loading ? 'Generating workflow suggestions...' : checklistLoading ? 'Creating checklist...' : 'Validating process...'}
          </span>
        </div>
      )}

      {/* ========== Workflow Suggestions ========== */}
      {!loading && workflow && (
        <div className="space-y-4">
          {/* Workflow Name & Current Phase */}
          {(workflow.workflow_name || workflow.current_phase) && (
            <Card className="bg-white/[0.02] border-white/[0.06]">
              <CardContent className="pt-4">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  {workflow.workflow_name && (
                    <div>
                      <div className="text-xs text-white/40 uppercase tracking-wide">Suggested Workflow</div>
                      <div className="text-lg font-semibold text-violet-300">{workflow.workflow_name}</div>
                    </div>
                  )}
                  {workflow.current_phase && (
                    <div className="px-3 py-1.5 bg-violet-600/20 border border-violet-500/30 rounded-lg">
                      <div className="text-[10px] text-white/55 uppercase">Current Phase</div>
                      <div className="text-sm font-medium text-violet-300">{workflow.current_phase}</div>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Status Flow */}
          {workflow.status_flow?.length > 0 && (
            <Card className="bg-white/[0.02] border-white/[0.06]">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-violet-300 flex items-center gap-1">
                  <ArrowRight className="w-4 h-4" /> Task Status Flow
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-1 flex-wrap">
                  {workflow.status_flow.map((s, i) => (
                    <React.Fragment key={i}>
                      <span className="px-3 py-1 bg-black/30 text-white/80 rounded text-xs font-medium capitalize">
                        {s.replace(/_/g, ' ')}
                      </span>
                      {i < workflow.status_flow.length - 1 && (
                        <ArrowRight className="w-3 h-3 text-white/35 shrink-0" />
                      )}
                    </React.Fragment>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Phases (expandable) */}
          {workflow.phases?.length > 0 && (
            <Card className="bg-white/[0.02] border-white/[0.06]">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-violet-300">Workflow Phases</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {workflow.phases.map((p, i) => {
                  const phaseName = typeof p === 'string' ? p : (p.name || p.phase || `Phase ${i + 1}`);
                  const phaseDesc = typeof p === 'object' ? p.description : null;
                  const phaseChecklist = typeof p === 'object' ? (p.checklist || []) : [];
                  const isCurrent = typeof p === 'object' ? p.is_current : (phaseName === workflow.current_phase);
                  const isExpanded = expandedPhase === phaseName;

                  return (
                    <div
                      key={i}
                      className={`rounded-lg border transition-colors ${
                        isCurrent ? 'border-violet-500/50 bg-violet-600/10' : 'border-white/[0.06] bg-black/30'
                      }`}
                    >
                      <button
                        onClick={() => setExpandedPhase(isExpanded ? null : phaseName)}
                        className="w-full flex items-center justify-between p-3 text-left"
                      >
                        <div className="flex items-center gap-3">
                          <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0 ${
                            isCurrent ? 'bg-violet-600 text-white' : 'bg-white/[0.05] text-white/65'
                          }`}>
                            {i + 1}
                          </div>
                          <div>
                            <span className={`text-sm font-medium ${isCurrent ? 'text-violet-300' : 'text-white/80'}`}>
                              {phaseName}
                            </span>
                            {isCurrent && (
                              <span className="ml-2 text-[10px] px-2 py-0.5 bg-violet-600/30 text-violet-300 rounded-full">
                                CURRENT
                              </span>
                            )}
                          </div>
                        </div>
                        {(phaseDesc || phaseChecklist.length > 0) && (
                          isExpanded ? <ChevronUp className="w-4 h-4 text-white/40" /> : <ChevronDown className="w-4 h-4 text-white/40" />
                        )}
                      </button>
                      {isExpanded && (phaseDesc || phaseChecklist.length > 0) && (
                        <div className="px-3 pb-3 pt-0 space-y-2 border-t border-white/[0.04] ml-10">
                          {phaseDesc && <p className="text-xs text-white/55 mt-2">{phaseDesc}</p>}
                          {phaseChecklist.length > 0 && (
                            <div className="space-y-1 mt-1">
                              <div className="text-[10px] text-white/40 uppercase tracking-wide">Phase Checklist</div>
                              {phaseChecklist.map((item, ci) => (
                                <div key={ci} className="text-xs text-white/65 flex items-start gap-2">
                                  <CheckSquare className="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-0.5" />
                                  <span>{typeof item === 'string' ? item : item.item || item.text || JSON.stringify(item)}</span>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </CardContent>
            </Card>
          )}

          {/* Recommendations */}
          {workflow.recommendations?.length > 0 && (
            <Card className="bg-white/[0.02] border-white/[0.06]">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-emerald-400 flex items-center gap-1">
                  <Lightbulb className="w-4 h-4" /> Recommendations
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-1.5">
                {workflow.recommendations.map((rec, i) => (
                  <div key={i} className="text-sm text-white/65 flex items-start gap-2">
                    <span className="text-emerald-400 mt-0.5">•</span>
                    <span>{typeof rec === 'string' ? rec : rec.text || JSON.stringify(rec)}</span>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {/* Bottlenecks */}
          {workflow.bottlenecks?.length > 0 && (
            <Card className="bg-white/[0.02] border-red-900/30">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-red-400 flex items-center gap-1">
                  <AlertTriangle className="w-4 h-4" /> Bottlenecks Detected
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-1.5">
                {workflow.bottlenecks.map((b, i) => (
                  <div key={i} className="text-sm text-white/65 flex items-start gap-2">
                    <span className="text-red-400 mt-0.5">⚠</span>
                    <span>{typeof b === 'string' ? b : b.text || JSON.stringify(b)}</span>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {/* Fallback: if LLM returned a text answer instead of JSON */}
          {workflow.answer && !workflow.phases && (
            <Card className="bg-white/[0.02] border-white/[0.06]">
              <CardContent className="pt-4">
                <pre className="text-sm text-white/65 whitespace-pre-wrap">{workflow.answer}</pre>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* ========== Checklist ========== */}
      {!checklistLoading && checklist && (
        <Card className="bg-white/[0.02] border-white/[0.06]">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm text-amber-400 flex items-center gap-1">
                <ListChecks className="w-4 h-4" /> Phase Checklist — {phase}
              </CardTitle>
              {totalChecklistItems > 0 && (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-white/55">{checkedCount}/{totalChecklistItems}</span>
                  <div className="w-20 h-1.5 bg-white/[0.05] rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${checklistProgress === 100 ? 'bg-emerald-500' : 'bg-amber-500'}`}
                      style={{ width: `${checklistProgress}%` }}
                    />
                  </div>
                </div>
              )}
            </div>
          </CardHeader>
          <CardContent>
            {totalChecklistItems > 0 ? (
              <div className="space-y-1">
                {checklistItems.map((item, i) => {
                  const text = typeof item === 'string' ? item : (item.item || item.text || JSON.stringify(item));
                  const priority = typeof item === 'object' ? item.priority : null;
                  const category = typeof item === 'object' ? item.category : null;
                  const isChecked = checkedItems.has(i);

                  return (
                    <button
                      key={i}
                      onClick={() => toggleCheck(i)}
                      className={`w-full flex items-start gap-3 p-2 rounded-lg text-left transition-colors hover:bg-white/[0.05]/30 ${
                        isChecked ? 'opacity-60' : ''
                      }`}
                    >
                      {isChecked ? (
                        <CheckSquare className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                      ) : (
                        <Square className="w-4 h-4 text-white/40 shrink-0 mt-0.5" />
                      )}
                      <div className="flex-1 min-w-0">
                        <span className={`text-sm ${isChecked ? 'text-white/40 line-through' : 'text-white/80'}`}>
                          {text}
                        </span>
                        <div className="flex items-center gap-2 mt-0.5">
                          {priority && (
                            <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                              priority === 'high' ? 'bg-red-500/20 text-red-400' :
                              priority === 'medium' ? 'bg-amber-500/20 text-amber-400' :
                              'bg-white/[0.05] text-white/55'
                            }`}>
                              {priority}
                            </span>
                          )}
                          {category && (
                            <span className="text-[10px] text-white/40">{category}</span>
                          )}
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            ) : (
              <div className="text-sm text-white/55">
                {checklist.answer ? (
                  <pre className="whitespace-pre-wrap">{checklist.answer}</pre>
                ) : (
                  <p>No checklist items generated.</p>
                )}
              </div>
            )}
            {/* Tips */}
            {checklist.tips?.length > 0 && (
              <div className="mt-4 pt-3 border-t border-white/[0.04]">
                <div className="text-xs text-white/40 uppercase tracking-wide mb-1.5">Tips</div>
                {checklist.tips.map((tip, i) => (
                  <div key={i} className="text-xs text-white/55 flex items-start gap-2 mb-1">
                    <Lightbulb className="w-3 h-3 text-amber-400 shrink-0 mt-0.5" />
                    <span>{typeof tip === 'string' ? tip : tip.text || JSON.stringify(tip)}</span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* ========== Validation Results ========== */}
      {!validateLoading && validation && (
        <Card className={`border-white/[0.06] ${validation.issues?.length > 0 ? 'bg-red-900/10 border-red-900/30' : 'bg-emerald-900/10 border-emerald-900/30'}`}>
          <CardHeader className="pb-2">
            <CardTitle className={`text-sm flex items-center gap-1 ${validation.issues?.length > 0 ? 'text-red-400' : 'text-emerald-400'}`}>
              <Shield className="w-4 h-4" /> Process Validation
              {validation.issues_count !== undefined && (
                <span className="ml-2 text-xs font-normal text-white/55">
                  ({validation.issues_count} issue{validation.issues_count !== 1 ? 's' : ''} found)
                </span>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {validation.issues?.length > 0 ? (
              <div className="space-y-2">
                {validation.issues.map((issue, i) => (
                  <div key={i} className="flex items-start gap-3 bg-black/30 rounded-lg p-3">
                    <AlertTriangle className={`w-4 h-4 shrink-0 mt-0.5 ${
                      issue.severity === 'high' ? 'text-red-400' : 'text-amber-400'
                    }`} />
                    <div className="flex-1">
                      <div className="text-sm text-white/80">{issue.task_title || 'Unknown Task'}</div>
                      <div className="text-xs text-white/55 mt-0.5">{issue.issue}</div>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded mt-1 inline-block ${
                        issue.severity === 'high' ? 'bg-red-500/20 text-red-400' : 'bg-amber-500/20 text-amber-400'
                      }`}>
                        {issue.severity}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="flex items-center gap-2 text-sm text-emerald-400">
                <CheckSquare className="w-4 h-4" />
                <span>{validation.message || 'All tasks are following proper workflow!'}</span>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Empty State */}
      {!anyLoading && !workflow && !checklist && !validation && (
        <div className="flex flex-col items-center justify-center py-20 text-white/40">
          <Workflow className="w-12 h-12 mb-3 text-white/35" />
          <p className="text-sm text-center max-w-md">
            Select a project and phase, then use <strong className="text-violet-400">Get Suggestions</strong> for AI workflow analysis,{' '}
            <strong className="text-amber-400">Phase Checklist</strong> for a step-by-step checklist, or{' '}
            <strong className="text-violet-400">Validate Process</strong> to check task flow issues.
          </p>
        </div>
      )}
    </div>
  );
}
