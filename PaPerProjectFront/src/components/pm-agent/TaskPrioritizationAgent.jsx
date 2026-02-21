import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/components/ui/use-toast';
import pmAgentService from '@/services/pmAgentService';
import { Loader2, Target, ListChecks, AlertTriangle, Users } from 'lucide-react';
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

const TaskPrioritizationAgent = ({ projects = [] }) => {
  const [selectedProjectId, setSelectedProjectId] = useState('');
  const [action, setAction] = useState('prioritize');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const { toast } = useToast();
  
  // Ensure projects is always an array
  const safeProjects = Array.isArray(projects) ? projects : [];

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

      const response = await pmAgentService.taskPrioritization(
        selectedAction,
        selectedProjectId || null
      );

      if (response.status === 'success') {
        setResult(response);
        toast({
          title: 'Success',
          description: 'Task analysis completed',
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
      toast({
        title: 'Error',
        description: error.message || 'Failed to analyze tasks',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
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

      const response = await pmAgentService.generateSubtasks(selectedProjectId);

      if (response.status === 'success') {
        setResult(response);
        toast({
          title: 'Success',
          description: `Generated ${response.data?.saved_count || 0} subtasks`,
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
        description: error.message || 'Failed to generate subtasks',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Target className="h-5 w-5 text-primary" />
            Task Prioritization Agent
          </CardTitle>
          <CardDescription>
            Prioritize tasks, find bottlenecks, suggest order, and delegation strategies
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="text-sm font-medium mb-2 block">
              Select Project
            </label>
            <Select value={selectedProjectId || "none"} onValueChange={setSelectedProjectId} disabled={safeProjects.length === 0}>
              <SelectTrigger>
                <SelectValue placeholder="Select a project" />
              </SelectTrigger>
              <SelectContent>
                {safeProjects.length > 0 ? (
                  safeProjects.map((project) => (
                    <SelectItem key={project.id} value={String(project.id)}>
                      {project.title || project.name}
                    </SelectItem>
                  ))
                ) : (
                  <SelectItem value="none" disabled>No projects available</SelectItem>
                )}
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {actions.map((actionItem) => {
              const Icon = actionItem.icon;
              return (
                <Button
                  key={actionItem.value}
                  variant={action === actionItem.value ? 'default' : 'outline'}
                  onClick={() => handleAction(actionItem.value)}
                  disabled={loading || !selectedProjectId}
                  className="justify-start"
                >
                  <Icon className="h-4 w-4 mr-2" />
                  {actionItem.label}
                </Button>
              );
            })}
          </div>

          <Button
            variant="outline"
            onClick={handleGenerateSubtasks}
            disabled={loading || !selectedProjectId}
            className="w-full"
          >
            {loading ? (
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
        </CardContent>
      </Card>

      {result && (
        <Card>
          <CardHeader>
            <CardTitle>Analysis Results</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Tasks with priorities and order - SHOW FIRST */}
            {result.data?.tasks && result.data.tasks.length > 0 && (
              <div className="space-y-3 mb-6">
                <p className="text-sm font-medium">
                  {action === 'prioritize_and_order' ? 'Task Execution Order:' : 'Task Priorities:'}
                </p>
                {result.data.tasks.map((task, index) => (
                  <div
                    key={task.id || index}
                    className="p-4 border rounded-lg bg-card"
                  >
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2 flex-wrap">
                          {action === 'prioritize_and_order' && task.execution_order && (
                            <Badge variant="outline" className="bg-primary/10 text-primary border-primary/30">
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
                            <Badge variant="outline" className="text-xs bg-blue-500/10 text-blue-400 border-blue-500/30">
                              Parallel Group: {task.parallel_group}
                            </Badge>
                          )}
                          {task.milestone_phase && (
                            <Badge variant="outline" className="text-xs bg-green-500/10 text-green-400 border-green-500/30">
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
                              Risk: {task.risk_level}
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
                <div className="p-4 border rounded-lg bg-card border-primary/30">
                  <p className="text-sm font-medium mb-2 text-primary">Overall Strategy - Why This Approach is Optimal:</p>
                  <p className="text-sm text-muted-foreground whitespace-pre-wrap">{result.data.combined_analysis.overall_reasoning}</p>
                </div>
                
                {/* Strategic Benefits */}
                {result.data.combined_analysis.strategic_benefits && result.data.combined_analysis.strategic_benefits.length > 0 && (
                  <div className="p-4 border rounded-lg bg-card border-yellow-500/30">
                    <p className="text-sm font-medium mb-2 text-yellow-400">Strategic Benefits:</p>
                    <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1">
                      {result.data.combined_analysis.strategic_benefits.map((benefit, idx) => (
                        <li key={idx}>{benefit}</li>
                      ))}
                    </ul>
                  </div>
                )}
                
                {/* Efficiency Benefits */}
                {result.data.combined_analysis.efficiency_benefits && result.data.combined_analysis.efficiency_benefits.length > 0 && (
                  <div className="p-4 border rounded-lg bg-card border-orange-500/30">
                    <p className="text-sm font-medium mb-2 text-orange-400">Efficiency Benefits:</p>
                    <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1">
                      {result.data.combined_analysis.efficiency_benefits.map((benefit, idx) => (
                        <li key={idx}>{benefit}</li>
                      ))}
                    </ul>
                  </div>
                )}
                
                {/* Synergistic Benefits */}
                {result.data.combined_analysis.synergistic_benefits && result.data.combined_analysis.synergistic_benefits.length > 0 && (
                  <div className="p-4 border rounded-lg bg-card border-purple-500/30">
                    <p className="text-sm font-medium mb-2 text-purple-400">Integrated Benefits:</p>
                    <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1">
                      {result.data.combined_analysis.synergistic_benefits.map((benefit, idx) => (
                        <li key={idx}>{benefit}</li>
                      ))}
                    </ul>
                  </div>
                )}
                
                {/* Strategic Insights */}
                {result.data.combined_analysis.key_strategic_insights && result.data.combined_analysis.key_strategic_insights.length > 0 && (
                  <div className="p-4 border rounded-lg bg-card border-blue-500/30">
                    <p className="text-sm font-medium mb-2 text-blue-400">Key Strategic Insights:</p>
                    <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1">
                      {result.data.combined_analysis.key_strategic_insights.map((insight, idx) => (
                        <li key={idx}>{insight}</li>
                      ))}
                    </ul>
                  </div>
                )}
                
                {/* Execution Recommendations */}
                {result.data.combined_analysis.execution_recommendations && result.data.combined_analysis.execution_recommendations.length > 0 && (
                  <div className="p-4 border rounded-lg bg-card border-green-500/30">
                    <p className="text-sm font-medium mb-2 text-green-400">Execution Recommendations:</p>
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
                    <div className="p-4 border rounded-lg bg-card border-primary/30">
                      <p className="text-sm font-medium mb-2 text-primary">Prioritization Strategy:</p>
                      <p className="text-sm text-muted-foreground">{result.data.prioritization.summary.prioritization_strategy}</p>
                    </div>
                    
                    {result.data.prioritization.summary.key_insights && result.data.prioritization.summary.key_insights.length > 0 && (
                      <div className="p-4 border rounded-lg bg-card border-blue-500/30">
                        <p className="text-sm font-medium mb-2 text-blue-400">Prioritization Insights:</p>
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
                    <div className="p-3 border rounded-lg bg-card border-border">
                      <div className="text-2xl font-bold">{result.data.prioritization.statistics.total_tasks || 0}</div>
                      <div className="text-sm text-muted-foreground">Total Tasks</div>
                    </div>
                    <div className="p-3 border rounded-lg bg-card border-red-500/30">
                      <div className="text-2xl font-bold text-red-400">{result.data.prioritization.statistics.high_priority || 0}</div>
                      <div className="text-sm text-muted-foreground">High Priority</div>
                    </div>
                    <div className="p-3 border rounded-lg bg-card border-yellow-500/30">
                      <div className="text-2xl font-bold text-yellow-400">{result.data.prioritization.statistics.medium_priority || 0}</div>
                      <div className="text-sm text-muted-foreground">Medium Priority</div>
                    </div>
                    <div className="p-3 border rounded-lg bg-card border-green-500/30">
                      <div className="text-2xl font-bold text-green-400">{result.data.prioritization.statistics.low_priority || 0}</div>
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
                  <div className="p-4 border rounded-lg bg-card border-primary/30">
                    <p className="text-sm font-medium mb-2 text-primary">Execution Order Optimization:</p>
                    <div className="grid grid-cols-2 gap-4 mt-2">
                      <div>
                        <p className="text-xs text-muted-foreground">Sequential Duration</p>
                        <p className="text-lg font-bold">{result.data.ordering.summary.total_sequential_days || 0} days</p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground">Optimized Duration</p>
                        <p className="text-lg font-bold text-green-400">{result.data.ordering.summary.optimized_duration_days || 0} days</p>
                      </div>
                    </div>
                    {result.data.ordering.summary.parallel_execution_saves_days > 0 && (
                      <p className="text-sm text-green-400 mt-2">
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
                  <div className="p-4 border rounded-lg bg-card border-blue-500/30">
                    <p className="text-sm font-medium mb-2 text-blue-400">Parallel Execution Groups:</p>
                    {result.data.ordering.parallel_groups.map((group, idx) => (
                      <div key={idx} className="mt-3 p-3 bg-muted rounded-lg">
                        <p className="text-sm font-medium">Group {group.group_id}</p>
                        <p className="text-xs text-muted-foreground mt-1">{group.reasoning}</p>
                      </div>
                    ))}
                  </div>
                )}
                
                {result.data.ordering.milestones && result.data.ordering.milestones.length > 0 && (
                  <div className="p-4 border rounded-lg bg-card border-green-500/30">
                    <p className="text-sm font-medium mb-2 text-green-400">Project Milestones:</p>
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
                <div className="p-4 border rounded-lg bg-card border-primary/30">
                  <p className="text-sm font-medium mb-2 text-primary">Prioritization Strategy:</p>
                  <p className="text-sm text-muted-foreground">{result.data.summary.prioritization_strategy}</p>
                </div>
                
                {result.data.summary.overall_reasoning && (
                  <div className="p-4 border rounded-lg bg-card border-blue-500/30">
                    <p className="text-sm font-medium mb-2 text-blue-400">Overall Reasoning - Why This Prioritization is Better:</p>
                    <p className="text-sm text-muted-foreground whitespace-pre-wrap">{result.data.summary.overall_reasoning}</p>
                  </div>
                )}
                
                {result.data.summary.key_insights && result.data.summary.key_insights.length > 0 && (
                  <div className="p-4 border rounded-lg bg-card border-blue-500/30">
                    <p className="text-sm font-medium mb-2 text-blue-400">Key Insights:</p>
                    <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1">
                      {result.data.summary.key_insights.map((insight, idx) => (
                        <li key={idx}>{insight}</li>
                      ))}
                    </ul>
                  </div>
                )}
                
                {result.data.summary.top_recommendations && result.data.summary.top_recommendations.length > 0 && (
                  <div className="p-4 border rounded-lg bg-card border-green-500/30">
                    <p className="text-sm font-medium mb-2 text-green-400">Top Recommendations:</p>
                    <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1">
                      {result.data.summary.top_recommendations.map((rec, idx) => (
                        <li key={idx}>{rec}</li>
                      ))}
                    </ul>
                  </div>
                )}
                
                {result.data.summary.risk_alerts && result.data.summary.risk_alerts.length > 0 && (
                  <div className="p-4 border rounded-lg bg-card border-red-500/30">
                    <p className="text-sm font-medium mb-2 text-red-400">Risk Alerts:</p>
                    <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1">
                      {result.data.summary.risk_alerts.map((alert, idx) => (
                        <li key={idx}>{alert}</li>
                      ))}
                    </ul>
                  </div>
                )}
                
                {result.data.summary.workload_concerns && (
                  <div className="p-4 border rounded-lg bg-card border-orange-500/30">
                    <p className="text-sm font-medium mb-2 text-orange-400">Workload Concerns:</p>
                    <p className="text-sm text-muted-foreground">{result.data.summary.workload_concerns}</p>
                  </div>
                )}
                
                {result.data?.statistics && (
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="p-3 border rounded-lg bg-card border-border">
                      <div className="text-2xl font-bold">{result.data.statistics.total_tasks || 0}</div>
                      <div className="text-sm text-muted-foreground">Total Tasks</div>
                    </div>
                    <div className="p-3 border rounded-lg bg-card border-red-500/30">
                      <div className="text-2xl font-bold text-red-400">{result.data.statistics.high_priority || 0}</div>
                      <div className="text-sm text-muted-foreground">High Priority</div>
                    </div>
                    <div className="p-3 border rounded-lg bg-card border-yellow-500/30">
                      <div className="text-2xl font-bold text-yellow-400">{result.data.statistics.medium_priority || 0}</div>
                      <div className="text-sm text-muted-foreground">Medium Priority</div>
                    </div>
                    <div className="p-3 border rounded-lg bg-card border-green-500/30">
                      <div className="text-2xl font-bold text-green-400">{result.data.statistics.low_priority || 0}</div>
                      <div className="text-sm text-muted-foreground">Low Priority</div>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Order Action - Parallel Groups and Milestones */}
            {action === 'order' && result.data?.parallel_groups && result.data.parallel_groups.length > 0 && (
              <div className="space-y-4 mb-6">
                <div className="p-4 border rounded-lg bg-card border-blue-500/30">
                  <p className="text-sm font-medium mb-2 text-blue-400">Parallel Execution Groups:</p>
                  {result.data.parallel_groups.map((group, idx) => (
                    <div key={idx} className="mt-3 p-3 bg-muted rounded-lg">
                      <p className="text-sm font-medium">Group {group.group_id}</p>
                      <p className="text-xs text-muted-foreground mt-1">{group.reasoning}</p>
                    </div>
                  ))}
                </div>
                
                {result.data.milestones && result.data.milestones.length > 0 && (
                  <div className="p-4 border rounded-lg bg-card border-green-500/30">
                    <p className="text-sm font-medium mb-2 text-green-400">Project Milestones:</p>
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
                    <div className="p-4 border rounded-lg bg-card border-primary/30">
                      <p className="text-sm font-medium mb-2 text-primary">Optimization Summary:</p>
                      <div className="grid grid-cols-2 gap-4 mt-2">
                        <div>
                          <p className="text-xs text-muted-foreground">Sequential Duration</p>
                          <p className="text-lg font-bold">{result.data.summary.total_sequential_days || 0} days</p>
                        </div>
                        <div>
                          <p className="text-xs text-muted-foreground">Optimized Duration</p>
                          <p className="text-lg font-bold text-green-400">{result.data.summary.optimized_duration_days || 0} days</p>
                        </div>
                      </div>
                      {result.data.summary.parallel_execution_saves_days > 0 && (
                        <p className="text-sm text-green-400 mt-2">
                          Saves {result.data.summary.parallel_execution_saves_days} days through parallelization
                        </p>
                      )}
                    </div>
                    
                    {result.data.summary.overall_reasoning && (
                      <div className="p-4 border rounded-lg bg-card border-blue-500/30">
                        <p className="text-sm font-medium mb-2 text-blue-400">Overall Reasoning - Why This Order is Better:</p>
                        <p className="text-sm text-muted-foreground whitespace-pre-wrap">{result.data.summary.overall_reasoning}</p>
                      </div>
                    )}
                    
                    {result.data.summary.optimization_benefits && result.data.summary.optimization_benefits.length > 0 && (
                      <div className="p-4 border rounded-lg bg-card border-green-500/30">
                        <p className="text-sm font-medium mb-2 text-green-400">Optimization Benefits:</p>
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
                    <div className="p-3 border rounded-lg bg-card border-border">
                      <div className="text-2xl font-bold">{result.data.summary.total_bottlenecks || 0}</div>
                      <div className="text-sm text-muted-foreground">Total Bottlenecks</div>
                    </div>
                    <div className="p-3 border rounded-lg bg-card border-red-500/30">
                      <div className="text-2xl font-bold text-red-400">{result.data.summary.critical_count || 0}</div>
                      <div className="text-sm text-muted-foreground">Critical</div>
                    </div>
                    <div className="p-3 border rounded-lg bg-card border-orange-500/30">
                      <div className="text-2xl font-bold text-orange-400">{result.data.summary.high_count || 0}</div>
                      <div className="text-sm text-muted-foreground">High</div>
                    </div>
                    <div className="p-3 border rounded-lg bg-card border-yellow-500/30">
                      <div className="text-2xl font-bold text-yellow-400">
                        {result.data.summary.estimated_project_delay_days || 0}
                      </div>
                      <div className="text-sm text-muted-foreground">Days Delay</div>
                    </div>
                  </div>
                )}
                
                {(result.data?.bottlenecks || result.data?.analysis?.bottlenecks || []).map((bottleneck, index) => (
                  <div
                    key={index}
                    className={`p-4 border rounded-lg bg-card ${
                      bottleneck.severity === 'critical'
                        ? 'border-red-500/30'
                        : bottleneck.severity === 'high'
                        ? 'border-orange-500/30'
                        : bottleneck.severity === 'medium'
                        ? 'border-yellow-500/30'
                        : 'border-border'
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
                        <p className="text-sm font-medium mb-1 text-green-400">Resolution Strategy:</p>
                        <ul className="list-disc list-inside text-sm text-muted-foreground space-y-1">
                          {bottleneck.resolution_strategy.map((step, idx) => (
                            <li key={idx}>{step}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    
                    {bottleneck.preventive_measures && bottleneck.preventive_measures.length > 0 && (
                      <div className="mt-3">
                        <p className="text-sm font-medium mb-1 text-blue-400">Preventive Measures:</p>
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
                      <div className="p-4 border rounded-lg bg-card border-red-500/30">
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
                      <div className="p-4 border rounded-lg bg-card border-green-500/30">
                        <p className="text-sm font-medium mb-2 text-green-400">Underutilized Members:</p>
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
                  <div className="p-3 rounded-lg bg-muted/60 border border-border text-sm text-muted-foreground">
                    {result.data.summary.message}
                  </div>
                )}
                {result.data?.summary && (
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                    <div className="p-3 border rounded-lg bg-card border-border">
                      <div className="text-2xl font-bold">{result.data.summary.total_suggestions || 0}</div>
                      <div className="text-sm text-muted-foreground">Total Suggestions</div>
                    </div>
                    <div className="p-3 border rounded-lg bg-card border-blue-500/30">
                      <div className="text-2xl font-bold text-blue-400">{result.data.summary.new_assignments || 0}</div>
                      <div className="text-sm text-muted-foreground">New Assignments</div>
                    </div>
                    <div className="p-3 border rounded-lg bg-card border-orange-500/30">
                      <div className="text-2xl font-bold text-orange-400">{result.data.summary.reassignments || 0}</div>
                      <div className="text-sm text-muted-foreground">Reassignments</div>
                    </div>
                    <div className="p-3 border rounded-lg bg-card border-green-500/30">
                      <div className="text-2xl font-bold text-green-400">
                        {result.data.summary.workload_balance_improvement || 'N/A'}
                      </div>
                      <div className="text-sm text-muted-foreground">Balance Improvement</div>
                    </div>
                  </div>
                )}
                
                {(result.data?.suggestions || result.data?.suggestions?.suggestions || []).map((suggestion, index) => (
                  <div
                    key={index}
                    className="p-4 border rounded-lg bg-card"
                  >
                    <div className="flex items-start justify-between mb-2">
                      <div>
                        <p className="font-medium">{suggestion.task_title || `Task #${suggestion.task_id}`}</p>
                        <div className="flex gap-2 mt-1">
                          <Badge variant="outline">
                            → {suggestion.suggested_assignee}
                          </Badge>
                          {suggestion.delegation_type && (
                            <Badge variant="secondary">{suggestion.delegation_type}</Badge>
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
                      <div className="p-4 border rounded-lg bg-card border-yellow-500/30">
                        <p className="text-sm font-medium mb-2 text-yellow-400">Before Delegation:</p>
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
                      <div className="p-4 border rounded-lg bg-card border-green-500/30">
                        <p className="text-sm font-medium mb-2 text-green-400">After Delegation:</p>
                        <p className="text-sm text-muted-foreground">
                          {result.data.workload_analysis.after_delegation.improvement || 'Workload balanced'}
                        </p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Subtask Generation Results */}
            {result.data?.saved_count !== undefined && (
              <div className="p-4 bg-green-50 border border-green-200 rounded-lg dark:bg-green-950 dark:border-green-800">
                <p className="text-sm font-medium text-green-800 dark:text-green-200">
                  Generated {result.data.saved_count} subtasks successfully
                </p>
                {result.data.reasoning_updated_count > 0 && (
                  <p className="text-xs text-green-700 dark:text-green-300 mt-1">
                    Updated reasoning for {result.data.reasoning_updated_count} tasks
                  </p>
                )}
              </div>
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



