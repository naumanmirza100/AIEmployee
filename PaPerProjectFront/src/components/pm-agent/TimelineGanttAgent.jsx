import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/components/ui/use-toast';
import pmAgentService from '@/services/pmAgentService';
import { Loader2, Calendar, BarChart3, Clock, AlertCircle, Settings, Layers, ChevronDown, ChevronUp, BrainCircuit, TrendingUp } from 'lucide-react';
import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';

const TimelineGanttAgent = ({ projects = [] }) => {
  const [selectedProjectId, setSelectedProjectId] = useState('');
  const [action, setAction] = useState('create_timeline');
  const [daysAhead, setDaysAhead] = useState(7);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [hoveredMarker, setHoveredMarker] = useState(null); // Track hovered marker: { taskIndex, markerIdx }
  const [expandedTasks, setExpandedTasks] = useState(new Set()); // Track expanded tasks
  const { toast } = useToast();
  
  // Ensure projects is always an array
  const safeProjects = Array.isArray(projects) ? projects : [];

  const actions = [
    { value: 'create_timeline', label: 'Create Timeline', icon: Calendar },
    { value: 'generate_gantt', label: 'Generate Gantt Chart', icon: BarChart3 },
    { value: 'check_deadlines', label: 'Check Deadlines', icon: Clock },
    { value: 'suggest_adjustments', label: 'Suggest Adjustments', icon: Settings },
    { value: 'calculate_duration', label: 'Calculate Duration', icon: Layers },
    { value: 'manage_phases', label: 'Manage Phases', icon: Layers },
  ];

  const handleAction = async (selectedAction) => {
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
      setAction(selectedAction);

      const options = {};
      if (selectedAction === 'check_deadlines') {
        options.days_ahead = daysAhead;
      }

      const response = await pmAgentService.timelineGantt(
        selectedAction,
        selectedProjectId,
        options
      );

      if (response.status === 'success') {
        setResult(response);
        toast({
          title: 'Success',
          description: 'Timeline analysis completed',
        });
      } else {
        toast({
          title: 'Error',
          description: response.message || 'Failed to process timeline request',
          variant: 'destructive',
        });
      }
    } catch (error) {
      console.error('Timeline/Gantt error:', error);
      toast({
        title: 'Error',
        description: error.message || 'Failed to process timeline request',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  // Extract chart data from result
  const getCharts = () => {
    if (!result?.data) return null;
    
    // Check for charts in different response structures
    const charts = result.data.charts || 
                   result.data.gantt_chart?.charts || 
                   result.data.timeline?.charts ||
                   result.data.charts;
    
    return charts;
  };

  const charts = getCharts();

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Calendar className="h-5 w-5 text-primary" />
            Timeline & Gantt Agent
          </CardTitle>
          <CardDescription>
            Create timelines, generate Gantt charts, check deadlines, and manage project schedules
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="text-sm font-medium mb-2 block">
              Select Project *
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

          {action === 'check_deadlines' && (
            <div>
              <label className="text-sm font-medium mb-2 block">
                Days Ahead
              </label>
              <Input
                type="number"
                value={daysAhead}
                onChange={(e) => setDaysAhead(parseInt(e.target.value) || 7)}
                min={1}
                max={365}
              />
            </div>
          )}

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
                  {loading && action === actionItem.value ? (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  ) : (
                    <Icon className="h-4 w-4 mr-2" />
                  )}
                  {actionItem.label}
                </Button>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {result && (
        <div className="space-y-6">
          {/* Charts Section - Hide for create_timeline action */}
          {charts && action !== 'create_timeline' && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Task Status Distribution Pie Chart */}
              {charts.status_distribution && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg">{charts.status_distribution.title}</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ResponsiveContainer width="100%" height={300}>
                      <PieChart>
                        <Pie
                          data={charts.status_distribution.data}
                          cx="50%"
                          cy="50%"
                          labelLine={false}
                          label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
                          outerRadius={80}
                          fill="#8884d8"
                          dataKey="value"
                        >
                          {charts.status_distribution.data.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={entry.color} />
                          ))}
                        </Pie>
                        <Tooltip />
                        <Legend />
                      </PieChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              )}

              {/* Priority Distribution Bar Chart */}
              {charts.priority_distribution && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg">{charts.priority_distribution.title}</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ResponsiveContainer width="100%" height={300}>
                      <BarChart data={charts.priority_distribution.data}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="name" />
                        <YAxis />
                        <Tooltip />
                        <Legend />
                        <Bar dataKey="value" fill="#8884d8">
                          {charts.priority_distribution.data.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={entry.color} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              )}

              {/* Burndown Chart */}
              {charts.burndown && charts.burndown.data && charts.burndown.data.length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg">{charts.burndown.title}</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ResponsiveContainer width="100%" height={300}>
                      <LineChart data={charts.burndown.data}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="week" />
                        <YAxis />
                        <Tooltip />
                        <Legend />
                        <Line type="monotone" dataKey="completed" stroke="#10b981" name="Completed" />
                        <Line type="monotone" dataKey="total" stroke="#3b82f6" name="Total" />
                        <Line type="monotone" dataKey="remaining" stroke="#ef4444" name="Remaining" />
                      </LineChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              )}

              {/* Resource Utilization */}
              {charts.resource_utilization && charts.resource_utilization.data && charts.resource_utilization.data.length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg">{charts.resource_utilization.title}</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ResponsiveContainer width="100%" height={300}>
                      <BarChart data={charts.resource_utilization.data}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="name" />
                        <YAxis yAxisId="left" />
                        <YAxis yAxisId="right" orientation="right" />
                        <Tooltip />
                        <Legend />
                        <Bar yAxisId="left" dataKey="hours" fill="#3b82f6" name="Hours" />
                        <Bar yAxisId="right" dataKey="tasks" fill="#10b981" name="Tasks" />
                      </BarChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              )}

              {/* Completion Rate Progress */}
              {charts.completion_rate && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg">{charts.completion_rate.title}</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-4">
                      <div className="text-center">
                        <div className="text-4xl font-bold text-primary mb-2">
                          {charts.completion_rate.percentage}%
                        </div>
                        <div className="text-sm text-muted-foreground">
                          {charts.completion_rate.completed} of {charts.completion_rate.total} tasks completed
                        </div>
                      </div>
                      <div className="w-full bg-secondary rounded-full h-4">
                        <div
                          className="bg-primary h-4 rounded-full transition-all duration-500"
                          style={{ width: `${charts.completion_rate.percentage}%` }}
                        />
                      </div>
                      <div className="grid grid-cols-3 gap-4 text-sm">
                        <div className="text-center">
                          <div className="font-semibold">{charts.completion_rate.completed}</div>
                          <div className="text-muted-foreground">Completed</div>
                        </div>
                        <div className="text-center">
                          <div className="font-semibold">{charts.completion_rate.inProgress}</div>
                          <div className="text-muted-foreground">In Progress</div>
                        </div>
                        <div className="text-center">
                          <div className="font-semibold">{charts.completion_rate.todo}</div>
                          <div className="text-muted-foreground">To Do</div>
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Milestone Status Chart */}
              {charts.milestone_status && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg">{charts.milestone_status.title}</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ResponsiveContainer width="100%" height={300}>
                      <PieChart>
                        <Pie
                          data={charts.milestone_status.data}
                          cx="50%"
                          cy="50%"
                          labelLine={false}
                          label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
                          outerRadius={80}
                          fill="#8884d8"
                          dataKey="value"
                        >
                          {charts.milestone_status.data.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={entry.color} />
                          ))}
                        </Pie>
                        <Tooltip />
                        <Legend />
                      </PieChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              )}
            </div>
          )}

          {/* Unified Timeline Chart for create_timeline action */}
          {action === 'create_timeline' && result.data?.timeline && result.data.timeline.tasks && result.data.timeline.tasks.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Project Timeline Visualization</CardTitle>
                <CardDescription>
                  All tasks displayed on a unified timeline showing start dates, status changes, deadlines, and completions
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {/* Calculate project-wide timeline bounds (first task start to last task completion) */}
                  {(() => {
                    const allTaskDates = [];
                    result.data.timeline.tasks.forEach(task => {
                      const startDate = new Date(task.date_range.start_date);
                      const endDate = new Date(task.date_range.end_date);
                      const completedDate = task.completed_at ? new Date(task.completed_at) : null;
                      
                      allTaskDates.push(startDate);
                      if (completedDate) {
                        allTaskDates.push(completedDate);
                      } else {
                        allTaskDates.push(endDate);
                      }
                    });
                    
                    const projectStart = new Date(Math.min(...allTaskDates.map(d => d.getTime())));
                    const projectEnd = new Date(Math.max(...allTaskDates.map(d => d.getTime())));
                    const totalMinutes = (projectEnd - projectStart) / (1000 * 60);
                    const totalHours = totalMinutes / 60;
                    const totalDays = totalMinutes / (60 * 24);
                    
                    // Generate calendar scale with days and hours
                    const generateCalendarScale = () => {
                      const scale = [];
                      const currentDate = new Date(projectStart);
                      const endDate = new Date(projectEnd);
                      
                      // Add day markers
                      while (currentDate <= endDate) {
                        const dayStart = new Date(currentDate);
                        dayStart.setHours(0, 0, 0, 0);
                        const dayEnd = new Date(dayStart);
                        dayEnd.setHours(23, 59, 59, 999);
                        
                        // Only add if within project range
                        if (dayEnd >= projectStart && dayStart <= projectEnd) {
                          const dayMinutes = (dayStart - projectStart) / (1000 * 60);
                          const dayPosition = (dayMinutes / totalMinutes) * 100;
                          
                          scale.push({
                            type: 'day',
                            date: new Date(dayStart),
                            position: dayPosition,
                            label: dayStart.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
                          });
                          
                          // Add hour markers for this day (every 12 hours for better spacing, or every 6 if timeline is short)
                          const hourInterval = totalDays > 7 ? 12 : 6;
                          for (let hour = 0; hour < 24; hour += hourInterval) {
                            const hourDate = new Date(dayStart);
                            hourDate.setHours(hour, 0, 0, 0);
                            
                            if (hourDate >= projectStart && hourDate <= projectEnd) {
                              const hourMinutes = (hourDate - projectStart) / (1000 * 60);
                              const hourPosition = (hourMinutes / totalMinutes) * 100;
                              
                              scale.push({
                                type: 'hour',
                                date: new Date(hourDate),
                                position: hourPosition,
                                label: hourDate.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false })
                              });
                            }
                          }
                        }
                        
                        currentDate.setDate(currentDate.getDate() + 1);
                      }
                      
                      return scale.sort((a, b) => a.position - b.position);
                    };
                    
                    const calendarScale = generateCalendarScale();
                    
                    return (
                      <div className="space-y-4 overflow-x-auto">
                        {result.data.timeline.tasks.map((task, index) => {
                          const startDate = new Date(task.date_range.start_date);
                          const endDate = new Date(task.date_range.end_date);
                          const dueDate = task.due_date ? new Date(task.due_date) : null;
                          const completedDate = task.completed_at ? new Date(task.completed_at) : null;
                          
                          // Calculate positions in minutes for precision
                          const startMinutes = (startDate - projectStart) / (1000 * 60);
                          const endMinutes = (endDate - projectStart) / (1000 * 60);
                          const durationMinutes = endMinutes - startMinutes;
                          
                          const startPosition = (startMinutes / totalMinutes) * 100;
                          const durationPercent = (durationMinutes / totalMinutes) * 100;
                      
                      // Color based on current task status
                      let barColor = '#6b7280'; // default gray
                      if (task.status === 'done') {
                        barColor = '#10b981'; // green for completed
                      } else if (task.status === 'in_progress') {
                        barColor = '#3b82f6'; // blue for in progress
                      } else if (task.status === 'review') {
                        barColor = '#8b5cf6'; // purple for review
                      } else if (task.status === 'blocked') {
                        barColor = '#ef4444'; // red for blocked
                      } else {
                        barColor = '#f59e0b'; // yellow/orange for planned/todo
                      }
                      
                      // Calculate positions for status change markers - include ALL status changes
                      const statusChangeMarkers = [];
                      if (task.status_changes && task.status_changes.length > 0) {
                        // Sort status changes by date to ensure proper ordering
                        const sortedChanges = [...task.status_changes].sort((a, b) => {
                          return new Date(a.changed_at) - new Date(b.changed_at);
                        });
                        
                        sortedChanges.forEach((change) => {
                          const changeDate = new Date(change.changed_at);
                          const changeMinutes = (changeDate - projectStart) / (1000 * 60);
                          const changePosition = (changeMinutes / totalMinutes) * 100;
                          
                          // Include all markers within project range
                          if (changePosition >= -5 && changePosition <= 105) {
                            statusChangeMarkers.push({
                              date: changeDate,
                              position: changePosition,
                              from: change.from_status,
                              to: change.to_status,
                              changed_by: change.changed_by
                            });
                          }
                        });
                      }
                      
                      const taskKey = task.id || index;
                      const isExpanded = expandedTasks.has(taskKey);
                      
                      return (
                        <div key={taskKey} className="space-y-2">
                          {/* Task Row */}
                          <div className="flex items-start gap-4 min-w-[1200px]">
                            {/* Task Info - Enhanced Design */}
                            <div className="w-72 flex-shrink-0 pr-4 border-r border-border/50">
                              <div className="space-y-2">
                                {/* Task Title */}
                                <div className="group">
                                  <p className="font-semibold text-sm text-foreground leading-tight mb-2 line-clamp-2">
                                    {task.title}
                                  </p>
                                </div>
                                
                                {/* Task Details */}
                                <div className="space-y-1.5">
                                  {/* Assignee */}
                                  <div className="flex items-start gap-2">
                                    <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide min-w-[60px]">
                                      Assignee:
                                    </span>
                                    <p className="text-xs text-foreground break-words line-clamp-2 flex-1">
                                      {task.assignee || 'Unassigned'}
                                    </p>
                                  </div>
                                  
                                  {/* Priority */}
                                  <div className="flex items-center gap-2">
                                    <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide min-w-[60px]">
                                      Priority:
                                    </span>
                                    <Badge 
                                      variant={
                                        task.priority === 'high' ? 'destructive' :
                                        task.priority === 'medium' ? 'default' :
                                        'secondary'
                                      }
                                      className="text-[10px] px-1.5 py-0 h-5"
                                    >
                                      {task.priority}
                                    </Badge>
                                  </div>
                                  
                                  {/* Status (if different from badge on right) */}
                                  <div className="flex items-center gap-2">
                                    <span className="text-[10px] font-medium text-muted-foreground uppercase tracking-wide min-w-[60px]">
                                      Status:
                                    </span>
                                    <span className="text-xs text-muted-foreground capitalize">
                                      {task.status}
                                    </span>
                                  </div>
                                </div>
                              </div>
                            </div>
                            
                            {/* Unified Timeline Bar */}
                            <div className="flex-1 relative">
                              <div className="relative h-12 bg-secondary rounded overflow-hidden mb-2">
                                {/* Task Duration Bar */}
                                <div
                                  className="absolute h-8 rounded flex items-center px-2 text-xs font-medium text-white shadow-md cursor-pointer hover:opacity-90 transition-opacity"
                                  style={{
                                    left: `${Math.max(0, Math.min(100, startPosition))}%`,
                                    width: `${Math.max(0.1, Math.min(100, durationPercent))}%`,
                                    maxWidth: 'calc(100% - 0px)',
                                    minWidth: '40px',
                                    backgroundColor: barColor,
                                    opacity: task.status === 'done' ? 0.8 : 1,
                                    top: '8px',
                                    zIndex: 2
                                  }}
                                  title={`${task.title}: ${startDate.toLocaleString('en-US', { 
                                    month: 'short', 
                                    day: 'numeric', 
                                    hour: '2-digit', 
                                    minute: '2-digit',
                                    hour12: false 
                                  })} to ${endDate.toLocaleString('en-US', { 
                                    month: 'short', 
                                    day: 'numeric', 
                                    hour: '2-digit', 
                                    minute: '2-digit',
                                    hour12: false 
                                  })}`}
                                >
                                  <span className="truncate">{task.title}</span>
                                </div>
                                
                                {/* Status Change Markers - Show ALL status changes */}
                                {statusChangeMarkers.map((marker, markerIdx) => {
                                  // Use pre-calculated position
                                  const markerPosition = Math.max(0, Math.min(100, marker.position));
                                  
                                  // For markers that are very close together, alternate vertical position
                                  const verticalOffset = markerIdx % 2 === 0 ? 0 : 3;
                                  const labelPosition = markerIdx % 2 === 0 ? 'bottom-full' : 'top-full';
                                  
                                  // Determine color based on status transition
                                  let markerColor = '#a855f7'; // default purple
                                  if (marker.to === 'done') {
                                    markerColor = '#10b981'; // green for completion
                                  } else if (marker.to === 'blocked') {
                                    markerColor = '#ef4444'; // red for blocked
                                  } else if (marker.to === 'in_progress') {
                                    markerColor = '#3b82f6'; // blue for in progress
                                  } else if (marker.to === 'review') {
                                    markerColor = '#8b5cf6'; // purple for review
                                  }
                                  
                                  return (
                                    <div
                                      key={`status-marker-${markerIdx}-${marker.date.getTime()}`}
                                      className="absolute top-0 w-0.5 h-full z-10 group/marker"
                                      style={{
                                        left: `${markerPosition}%`,
                                        transform: 'translateX(-50%)',
                                        backgroundColor: markerColor
                                      }}
                                    >
                                      <div 
                                        className="absolute left-1/2 transform -translate-x-1/2 w-2.5 h-2.5 rounded-full border-2 border-white cursor-pointer z-20 shadow-sm"
                                        style={{
                                          top: `${-2 + verticalOffset}px`,
                                          backgroundColor: markerColor
                                        }}
                                        onMouseEnter={() => setHoveredMarker({ taskIndex: index, markerIdx })}
                                        onMouseLeave={() => setHoveredMarker(null)}
                                      ></div>
                                    </div>
                                  );
                                })}
                                
                                {/* Deadline Marker */}
                                {dueDate && (() => {
                                  const deadlineMinutes = (dueDate - projectStart) / (1000 * 60);
                                  const deadlinePosition = Math.max(0, Math.min(100, (deadlineMinutes / totalMinutes) * 100));
                                  return (
                                    <div
                                      className="absolute top-0 w-0.5 h-full bg-red-500 z-10 cursor-pointer group"
                                      style={{
                                        left: `${deadlinePosition}%`,
                                        transform: 'translateX(-50%)'
                                      }}
                                    >
                                      <div className="absolute -bottom-1 left-1/2 transform -translate-x-1/2 w-2 h-2 bg-red-500 rounded-full border border-white"></div>
                                      {/* Tooltip */}
                                      <div className="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-2 py-1 bg-gray-900 dark:bg-gray-800 text-white text-xs rounded shadow-lg opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-20">
                                        <div className="font-medium">Deadline</div>
                                        <div>{dueDate.toLocaleString('en-US', { 
                                          month: 'short', 
                                          day: 'numeric', 
                                          hour: '2-digit', 
                                          minute: '2-digit',
                                          hour12: false 
                                        })}</div>
                                        {/* Arrow */}
                                        <div className="absolute top-full left-1/2 transform -translate-x-1/2 w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-t-gray-900 dark:border-t-gray-800"></div>
                                      </div>
                                    </div>
                                  );
                                })()}
                                
                                {/* Completion Marker */}
                                {completedDate && (() => {
                                  const completionMinutes = (completedDate - projectStart) / (1000 * 60);
                                  const completionPosition = Math.max(0, Math.min(100, (completionMinutes / totalMinutes) * 100));
                                  return (
                                    <div
                                      className="absolute top-0 w-0.5 h-full bg-green-500 z-10 cursor-pointer group"
                                      style={{
                                        left: `${completionPosition}%`,
                                        transform: 'translateX(-50%)'
                                      }}
                                    >
                                      <div className="absolute -bottom-1 left-1/2 transform -translate-x-1/2 w-2 h-2 bg-green-500 rounded-full border border-white"></div>
                                      {/* Tooltip */}
                                      <div className="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-2 py-1 bg-gray-900 dark:bg-gray-800 text-white text-xs rounded shadow-lg opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-20">
                                        <div className="font-medium">Completed</div>
                                        <div>{completedDate.toLocaleString('en-US', { 
                                          month: 'short', 
                                          day: 'numeric', 
                                          hour: '2-digit', 
                                          minute: '2-digit',
                                          hour12: false 
                                        })}</div>
                                        {/* Arrow */}
                                        <div className="absolute top-full left-1/2 transform -translate-x-1/2 w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-t-gray-900 dark:border-t-gray-800"></div>
                                      </div>
                                    </div>
                                  );
                                })()}
                              </div>
                              
                              {/* Detailed Calendar Scale - Below the timeline bar */}
                              <div className="relative border-t pt-2 mt-2 min-h-[80px]">
                                {/* Project start and end labels - Bottom row */}
                                <div className="absolute top-6 left-0 text-[10px] font-semibold text-primary whitespace-nowrap bg-background px-1 rounded z-20">
                                  {projectStart.toLocaleString('en-US', { 
                                    month: 'short', 
                                    day: 'numeric', 
                                    hour: '2-digit', 
                                    minute: '2-digit',
                                    hour12: false 
                                  })}
                                </div>
                                <div className="absolute top-6 right-0 text-[10px] font-semibold text-primary whitespace-nowrap bg-background px-1 rounded z-20">
                                  {projectEnd.toLocaleString('en-US', { 
                                    month: 'short', 
                                    day: 'numeric', 
                                    hour: '2-digit', 
                                    minute: '2-digit',
                                    hour12: false 
                                  })}
                                </div>
                                
                                {/* Day markers - Second row with shorter lines */}
                                {calendarScale.filter(m => m.type === 'day').map((marker, idx) => {
                                  // Check if this day marker would overlap with previous ones
                                  const dayMarkers = calendarScale.filter(m => m.type === 'day');
                                  const prevMarker = idx > 0 ? dayMarkers[idx - 1] : null;
                                  const minSpacing = totalDays > 14 ? 4 : 6; // Minimum spacing in percentage
                                  const shouldShow = !prevMarker || (marker.position - prevMarker.position) >= minSpacing;
                                  
                                  return shouldShow ? (
                                    <div
                                      key={`day-${idx}`}
                                      className="absolute top-0 z-10"
                                      style={{ left: `${marker.position}%` }}
                                    >
                                      {/* Shorter vertical line - only 20px tall, pointing down */}
                                      <div className="absolute top-0 h-5 border-l-2 border-primary/30"></div>
                                      <div className="absolute top-6 left-0 transform -translate-x-1/2 text-[10px] font-medium text-foreground whitespace-nowrap bg-background px-1 rounded z-20">
                                        {marker.label}
                                      </div>
                                    </div>
                                  ) : null;
                                })}
                                
                                {/* Hour markers - Third row with shorter lines and always show labels */}
                                {calendarScale.filter(m => m.type === 'hour').map((marker, idx) => {
                                  // Check if this hour is too close to any day marker (more lenient)
                                  const dayMarkers = calendarScale.filter(m => m.type === 'day');
                                  const tooCloseToDay = dayMarkers.some(dayMarker => Math.abs(marker.position - dayMarker.position) < 1);
                                  
                                  // Check if this hour is too close to previous hour markers (more lenient)
                                  const hourMarkers = calendarScale.filter(m => m.type === 'hour');
                                  const prevHourMarkers = hourMarkers.slice(0, idx);
                                  const minHourSpacing = totalDays > 7 ? 1 : 2; // Very lenient to show more hours
                                  const tooCloseToHour = prevHourMarkers.some(prevHour => Math.abs(marker.position - prevHour.position) < minHourSpacing);
                                  
                                  // Show hour marker if not too close to day or other hours
                                  return !tooCloseToDay && !tooCloseToHour ? (
                                    <div
                                      key={`hour-${idx}`}
                                      className="absolute top-0 z-5"
                                      style={{ left: `${marker.position}%` }}
                                    >
                                      {/* Shorter vertical line - only 12px tall, pointing down */}
                                      <div className="absolute top-0 h-3 border-l border-muted-foreground/40"></div>
                                      <div className="absolute top-3.5 left-0 transform -translate-x-1/2 text-[9px] text-muted-foreground whitespace-nowrap bg-background px-0.5 rounded z-15">
                                        {marker.label}
                                      </div>
                                    </div>
                                  ) : null;
                                })}
                              </div>
                              
                              {/* Status Change Tooltips - Positioned outside overflow-hidden container */}
                              {statusChangeMarkers.map((marker, markerIdx) => {
                                const markerPosition = Math.max(0, Math.min(100, marker.position));
                                const verticalOffset = markerIdx % 2 === 0 ? 0 : 3;
                                const labelPosition = markerIdx % 2 === 0 ? 'bottom-full' : 'top-full';
                                const isHovered = hoveredMarker?.taskIndex === index && hoveredMarker?.markerIdx === markerIdx;
                                
                                return (
                                  <div
                                    key={`tooltip-${markerIdx}-${marker.date.getTime()}`}
                                    className="absolute pointer-events-none"
                                    style={{
                                      left: `${markerPosition}%`,
                                      transform: 'translateX(-50%)',
                                      top: labelPosition === 'bottom-full' ? 'calc(100% + 8px)' : '-8px',
                                      zIndex: 50
                                    }}
                                  >
                                    {/* Tooltip - Shows on hover of the marker */}
                                    <div 
                                      className={`absolute left-1/2 transform -translate-x-1/2 px-2 py-1 bg-gray-900 dark:bg-gray-800 text-white text-xs rounded shadow-lg transition-opacity whitespace-nowrap ${
                                        isHovered ? 'opacity-100' : 'opacity-0'
                                      } ${labelPosition === 'bottom-full' ? 'top-0' : 'bottom-0'}`}
                                    >
                                      <div className="font-medium mb-1">Status Changed</div>
                                      <div className="mb-1">
                                        <span className="text-purple-300">{marker.from || 'Created'}</span>
                                        <span className="mx-1">→</span>
                                        <span className="text-purple-200">{marker.to}</span>
                                      </div>
                                      <div className="text-gray-300 text-[10px]">
                                        {marker.date.toLocaleString('en-US', { 
                                          year: 'numeric', 
                                          month: '2-digit', 
                                          day: '2-digit', 
                                          hour: '2-digit', 
                                          minute: '2-digit',
                                          second: '2-digit',
                                          hour12: false 
                                        })}
                                      </div>
                                      {marker.changed_by && (
                                        <div className="text-gray-300 text-[10px] mt-1">By: {marker.changed_by}</div>
                                      )}
                                      {/* Arrow */}
                                      <div className={`absolute left-1/2 transform -translate-x-1/2 w-0 h-0 ${
                                        labelPosition === 'bottom-full' 
                                          ? 'top-full border-l-4 border-r-4 border-t-4 border-transparent border-t-gray-900 dark:border-t-gray-800'
                                          : 'bottom-full border-l-4 border-r-4 border-b-4 border-transparent border-b-gray-900 dark:border-b-gray-800'
                                      }`}></div>
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                            
                            {/* Status Badge */}
                            <div className="w-32 flex-shrink-0 text-right">
                              {(() => {
                                // Determine badge color based on status
                                let badgeColor = '#6b7280'; // default gray
                                let textColor = '#ffffff';
                                
                                if (task.status === 'done') {
                                  badgeColor = '#10b981'; // green
                                } else if (task.status === 'in_progress') {
                                  badgeColor = '#3b82f6'; // blue
                                } else if (task.status === 'review') {
                                  badgeColor = '#8b5cf6'; // purple
                                } else if (task.status === 'blocked') {
                                  badgeColor = '#ef4444'; // red
                                } else {
                                  badgeColor = '#f59e0b'; // yellow/orange for todo/planned
                                }
                                
                                return (
                                  <Badge 
                                    className="text-white border-0"
                                    style={{ backgroundColor: badgeColor }}
                                  >
                                    {task.status}
                                  </Badge>
                                );
                              })()}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                      </div>
                    );
                  })()}
                  
                  {/* Legend */}
                  <div className="mt-6 pt-4 border-t">
                    <p className="text-xs font-medium mb-2">Legend:</p>
                    <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
                      <div className="flex items-center gap-2">
                        <div className="w-4 h-4 rounded bg-green-500"></div>
                        <span>Completed (Done)</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="w-4 h-4 rounded bg-blue-500"></div>
                        <span>In Progress</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="w-4 h-4 rounded" style={{ backgroundColor: '#8b5cf6' }}></div>
                        <span>Review</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="w-4 h-4 rounded bg-red-500"></div>
                        <span>Blocked</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="w-4 h-4 rounded bg-yellow-500"></div>
                        <span>Planned/To Do</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full bg-purple-500"></div>
                        <span>Status Change</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full bg-red-500"></div>
                        <span>Deadline</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full bg-green-500"></div>
                        <span>Completion</span>
                      </div>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Detailed Results Card - Hidden for create_timeline action */}
          {action !== 'create_timeline' && (
            <Card>
              <CardHeader>
                <CardTitle>Timeline Results</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
              {/* Gantt Chart Data */}
              {result.data?.gantt_chart && (
                <div className="space-y-3">
                  <p className="text-sm font-medium">Gantt Chart Data:</p>
                  {result.data.gantt_chart.tasks && result.data.gantt_chart.tasks.length > 0 ? (
                    <div className="space-y-2">
                      {result.data.gantt_chart.tasks.slice(0, 10).map((task, index) => (
                        <div
                          key={task.id || index}
                          className="p-3 border rounded-lg bg-card"
                        >
                          <p className="font-medium">{task.title}</p>
                          {task.start_date && task.end_date && (
                            <p className="text-sm text-muted-foreground mt-1">
                              {task.start_date} - {task.end_date}
                            </p>
                          )}
                          {task.ai_reasoning && (
                            <p className="text-sm text-muted-foreground mt-2">
                              {task.ai_reasoning}
                            </p>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">No tasks found in Gantt chart.</p>
                  )}
                </div>
              )}

              {/* Timeline with Gantt Chart */}
              {result.data?.timeline && result.data.timeline.tasks && result.data.timeline.tasks.length > 0 && (
                <div className="space-y-4">
                  <div>
                    <p className="text-sm font-medium mb-2">Project Timeline:</p>
                    <p className="text-xs text-muted-foreground">
                      {result.data.timeline.timeline_start && result.data.timeline.timeline_end && (
                        <>From {new Date(result.data.timeline.timeline_start).toLocaleDateString()} to {new Date(result.data.timeline.timeline_end).toLocaleDateString()}</>
                      )}
                    </p>
                  </div>
                  
                  {/* Visual Timeline/Gantt Chart */}
                  <div className="border rounded-lg p-4 bg-card overflow-x-auto">
                    <div className="min-w-full space-y-3">
                      {result.data.timeline.tasks.map((task, index) => {
                        const startDate = new Date(task.date_range.start_date);
                        const endDate = new Date(task.date_range.end_date);
                        const daysDiff = Math.ceil((endDate - startDate) / (1000 * 60 * 60 * 24)) + 1;
                        
                        // Color based on current task status
                        let barColor = '#6b7280'; // default gray
                        if (task.status === 'done') {
                          barColor = '#10b981'; // green for completed
                        } else if (task.status === 'in_progress') {
                          barColor = '#3b82f6'; // blue for in progress
                        } else if (task.status === 'review') {
                          barColor = '#8b5cf6'; // purple for review
                        } else if (task.status === 'blocked') {
                          barColor = '#ef4444'; // red for blocked
                        } else {
                          barColor = '#f59e0b'; // yellow/orange for planned/todo
                        }
                        
                        return (
                          <div key={task.id || index} className="space-y-2">
                            <div className="flex items-center gap-4">
                              <div className="w-48 flex-shrink-0">
                                <p className="font-medium text-sm">{task.title}</p>
                                <p className="text-xs text-muted-foreground">
                                  {task.assignee || 'Unassigned'} • {task.priority}
                                </p>
                              </div>
                              <div className="flex-1 relative">
                                <div className="relative h-8 bg-secondary rounded overflow-hidden">
                                  <div
                                    className="h-full rounded flex items-center justify-center text-xs font-medium text-white"
                                    style={{
                                      width: `${Math.max(5, daysDiff * 2)}px`,
                                      minWidth: '40px',
                                      backgroundColor: barColor,
                                      opacity: task.status === 'done' ? 0.8 : 1
                                    }}
                                    title={`${task.date_range.start_date} to ${task.date_range.end_date}`}
                                  >
                                    {daysDiff}d
                                  </div>
                                </div>
                                <div className="text-xs text-muted-foreground mt-1">
                                  {new Date(task.date_range.start_date).toLocaleDateString()} - {new Date(task.date_range.end_date).toLocaleDateString()}
                                </div>
                              </div>
                              <div className="w-32 flex-shrink-0 text-right">
                                <Badge variant={
                                  task.status === 'done' ? 'default' :
                                  task.status === 'in_progress' ? 'default' :
                                  task.status === 'blocked' ? 'destructive' :
                                  'secondary'
                                }>
                                  {task.status}
                                </Badge>
                              </div>
                            </div>
                            
                            {/* Status Change History */}
                            {task.status_changes && task.status_changes.length > 0 && (
                              <div className="ml-52 space-y-1">
                                <p className="text-xs font-medium text-muted-foreground">Status Changes:</p>
                                {task.status_changes.slice(0, 3).map((change, changeIdx) => (
                                  <div key={changeIdx} className="text-xs text-muted-foreground">
                                    {change.from_status || 'Created'} → {change.to_status} on {new Date(change.changed_at).toLocaleString()}
                                    {change.changed_by && ` by ${change.changed_by}`}
                                  </div>
                                ))}
                              </div>
                            )}
                            
                            {/* Completion Date Range for Completed Tasks */}
                            {task.date_range.type === 'completed' && task.date_range.completed_from && task.date_range.completed_to && (
                              <div className="ml-52 text-xs text-green-600 dark:text-green-400">
                                ✓ Completed from {new Date(task.date_range.completed_from).toLocaleDateString()} to {new Date(task.date_range.completed_to).toLocaleDateString()}
                              </div>
                            )}
                            
                            {/* Planned Date Range for Non-Completed Tasks */}
                            {task.date_range.type === 'planned' && task.date_range.planned_from && task.date_range.planned_to && (
                              <div className="ml-52 text-xs text-muted-foreground">
                                📅 Planned from {new Date(task.date_range.planned_from).toLocaleDateString()} to {new Date(task.date_range.planned_to).toLocaleDateString()}
                              </div>
                            )}
                            
                            {/* In Progress Since */}
                            {task.date_range.type === 'in_progress' && task.date_range.current_status_since && (
                              <div className="ml-52 text-xs text-blue-600 dark:text-blue-400">
                                🔄 In progress since {new Date(task.date_range.current_status_since).toLocaleDateString()}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
              )}

              {/* Deadline Alerts (from check_deadlines action) */}
              {(result.data?.alerts !== undefined || result.data?.summary !== undefined) && (
                <div className="space-y-3">
                  <p className="text-sm font-medium flex items-center gap-2">
                    <AlertCircle className="h-4 w-4" />
                    Deadline Alerts:
                  </p>
                  {result.data.summary && (
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                      <div className="p-3 border rounded-lg bg-card border-border">
                        <div className="text-2xl font-bold text-foreground">{result.data.summary.total_alerts || 0}</div>
                        <div className="text-sm text-muted-foreground">Total Alerts</div>
                      </div>
                      <div className="p-3 border rounded-lg bg-card border-red-500/30">
                        <div className="text-2xl font-bold text-red-400">{result.data.summary.overdue_count || 0}</div>
                        <div className="text-sm text-muted-foreground">Overdue</div>
                      </div>
                      <div className="p-3 border rounded-lg bg-card border-yellow-500/30">
                        <div className="text-2xl font-bold text-yellow-400">{result.data.summary.upcoming_count || 0}</div>
                        <div className="text-sm text-muted-foreground">Upcoming</div>
                      </div>
                      <div className="p-3 border rounded-lg bg-card border-orange-500/30">
                        <div className="text-2xl font-bold text-orange-400">{result.data.summary.critical_count || 0}</div>
                        <div className="text-sm text-muted-foreground">Critical</div>
                      </div>
                    </div>
                  )}
                  {result.data.alerts && result.data.alerts.length > 0 ? (
                    result.data.alerts.map((alert, index) => (
                      <div
                        key={index}
                        className={`p-3 border rounded-lg bg-card ${
                          alert.urgency === 'critical' 
                            ? 'border-red-500/30'
                            : alert.urgency === 'high'
                            ? 'border-orange-500/30'
                            : 'border-yellow-500/30'
                        }`}
                      >
                        <p className="font-medium text-foreground">
                          {alert.title || alert.task_title || 'Task'}
                        </p>
                        <p className="text-sm text-muted-foreground mt-1">
                          {alert.type === 'overdue' 
                            ? `Overdue by ${alert.days_overdue} day(s)`
                            : alert.type === 'upcoming'
                            ? `Due in ${alert.days_until} day(s)${alert.remaining_percentage ? ` (${alert.remaining_percentage}% time remaining)` : ''}`
                            : alert.type === 'project_deadline'
                            ? `Project deadline in ${alert.days_until} day(s)`
                            : ''}
                        </p>
                        {alert.due_date && (
                          <p className="text-xs text-muted-foreground mt-1">
                            Due: {new Date(alert.due_date).toLocaleDateString()}
                          </p>
                        )}
                        {alert.assignee_name && (
                          <p className="text-xs text-muted-foreground mt-1">
                            Assignee: {alert.assignee_name}
                          </p>
                        )}
                      </div>
                    ))
                  ) : (
                    <div className="p-4 bg-card border border-green-500/30 rounded-lg">
                      <p className="text-sm text-green-400">
                        ✓ No deadline alerts found. All tasks are on track!
                      </p>
                    </div>
                  )}
                </div>
              )}

              {/* Deadline Warnings (legacy format) */}
              {result.data?.deadline_warnings && result.data.deadline_warnings.length > 0 && (
                <div className="space-y-3">
                  <p className="text-sm font-medium flex items-center gap-2">
                    <AlertCircle className="h-4 w-4" />
                    Deadline Warnings:
                  </p>
                  {result.data.deadline_warnings.map((warning, index) => (
                    <div
                      key={index}
                      className="p-3 border border-yellow-500/30 rounded-lg bg-card"
                    >
                      <p className="font-medium text-yellow-400">
                        {warning.task_title || 'Task'}
                      </p>
                      <p className="text-sm text-muted-foreground mt-1">
                        {warning.message || warning.reasoning}
                      </p>
                    </div>
                  ))}
                </div>
              )}

              {/* Adjustments (from suggest_adjustments action) */}
              {result.data?.suggestions && result.data.suggestions.length > 0 && (
                <div className="space-y-3">
                  <p className="text-sm font-medium">Suggested Adjustments:</p>
                  {result.data.summary && (
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                      <div className="p-3 border rounded-lg">
                        <div className="text-2xl font-bold">{result.data.summary.total_suggestions}</div>
                        <div className="text-sm text-muted-foreground">Total Suggestions</div>
                      </div>
                      <div className="p-3 border rounded-lg">
                        <div className="text-2xl font-bold text-red-600">{result.data.summary.high_priority}</div>
                        <div className="text-sm text-muted-foreground">High Priority</div>
                      </div>
                      <div className="p-3 border rounded-lg">
                        <div className="text-2xl font-bold text-yellow-600">{result.data.summary.medium_priority}</div>
                        <div className="text-sm text-muted-foreground">Medium Priority</div>
                      </div>
                      <div className="p-3 border rounded-lg">
                        <div className="text-2xl font-bold text-green-600">{result.data.summary.low_priority}</div>
                        <div className="text-sm text-muted-foreground">Low Priority</div>
                      </div>
                    </div>
                  )}
                  {result.data.suggestions.map((suggestion, index) => (
                    <div
                      key={index}
                      className={`p-3 border rounded-lg bg-card ${
                        suggestion.priority === 'high' ? 'border-red-200' : 
                        suggestion.priority === 'medium' ? 'border-yellow-200' : 
                        'border-green-200'
                      }`}
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <p className="font-medium">{suggestion.task_title || suggestion.type?.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())}</p>
                          <p className="text-sm text-muted-foreground mt-1">
                            {suggestion.reasoning || suggestion.impact || suggestion.suggestion}
                          </p>
                          {suggestion.suggested_value && (
                            <p className="text-sm font-medium mt-2">
                              Suggested: {suggestion.suggested_value}
                            </p>
                          )}
                        </div>
                        <Badge variant={
                          suggestion.priority === 'high' ? 'destructive' :
                          suggestion.priority === 'medium' ? 'default' :
                          'secondary'
                        }>
                          {suggestion.priority || 'medium'}
                        </Badge>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Adjustments (legacy format) */}
              {result.data?.adjustments && result.data.adjustments.length > 0 && (
                <div className="space-y-3">
                  <p className="text-sm font-medium">Suggested Adjustments:</p>
                  {result.data.adjustments.map((adjustment, index) => (
                    <div
                      key={index}
                      className="p-3 border rounded-lg bg-card"
                    >
                      <p className="font-medium">{adjustment.task_title}</p>
                      <p className="text-sm text-muted-foreground mt-1">
                        {adjustment.suggestion || adjustment.reasoning}
                      </p>
                    </div>
                  ))}
                </div>
              )}

              {/* Duration Estimates (from calculate_duration action) */}
              {result.data?.estimates && (
                <div className="space-y-4">
                  <p className="text-sm font-medium">Duration Estimates:</p>
                  
                  {/* Team Efficiency Info */}
                  {result.data.estimates.team_efficiency && (
                    <div className="p-3 border rounded-lg bg-card">
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-3">
                        <div>
                          <div className="text-lg font-bold text-foreground">{result.data.estimates.team_efficiency.current_team_size || 1}</div>
                          <div className="text-xs text-muted-foreground">Team Members</div>
                        </div>
                        <div>
                          <div className="text-lg font-bold text-foreground">{Math.round((result.data.estimates.team_efficiency.parallelization_ratio || 0) * 100)}%</div>
                          <div className="text-xs text-muted-foreground">Parallelization</div>
                        </div>
                        <div>
                          <div className="text-lg font-bold text-foreground">{result.data.estimates.team_efficiency.optimal_team_size || result.data.estimates.team_efficiency.current_team_size || 1}</div>
                          <div className="text-xs text-muted-foreground">Optimal Team Size</div>
                        </div>
                        <div>
                          <div className="text-lg font-bold text-foreground">{result.data.estimates.team_efficiency.coordination_overhead_percent || 0}%</div>
                          <div className="text-xs text-muted-foreground">Coordination Overhead</div>
                        </div>
                      </div>
                    </div>
                  )}
                  
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div className="p-3 border rounded-lg bg-card">
                      <div className="text-2xl font-bold text-foreground">{result.data.estimates.working_days?.expected?.toFixed(1) || 'N/A'}</div>
                      <div className="text-sm text-muted-foreground">Expected Working Days</div>
                    </div>
                    <div className="p-3 border rounded-lg bg-card">
                      <div className="text-2xl font-bold text-green-400">{result.data.estimates.working_days?.optimistic?.toFixed(1) || 'N/A'}</div>
                      <div className="text-sm text-muted-foreground">Optimistic</div>
                    </div>
                    <div className="p-3 border rounded-lg bg-card">
                      <div className="text-2xl font-bold text-blue-400">{result.data.estimates.working_days?.realistic?.toFixed(1) || 'N/A'}</div>
                      <div className="text-sm text-muted-foreground">Realistic</div>
                    </div>
                    <div className="p-3 border rounded-lg bg-card">
                      <div className="text-2xl font-bold text-red-400">{result.data.estimates.working_days?.pessimistic?.toFixed(1) || 'N/A'}</div>
                      <div className="text-sm text-muted-foreground">Pessimistic</div>
                    </div>
                  </div>
                  
                  <div className="p-3 border rounded-lg bg-card">
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <div className="text-lg font-bold text-foreground">{result.data.estimates.total_estimated_hours?.toFixed(1) || 'N/A'}</div>
                        <div className="text-sm text-muted-foreground">Total Estimated Hours</div>
                      </div>
                      {result.data.estimates.calendar_days && (
                        <div>
                          <div className="text-lg font-bold text-foreground">
                            {result.data.estimates.calendar_days.expected?.toFixed(1) || 'N/A'} days ({result.data.estimates.calendar_days.weeks?.toFixed(1) || 'N/A'} weeks)
                          </div>
                          <div className="text-sm text-muted-foreground">Calendar Time</div>
                        </div>
                      )}
                    </div>
                  </div>
                  
                  {/* AI Reasoning */}
                  {result.data.recommendations?.ai_reasoning && (
                    <div className="p-4 border rounded-lg bg-card">
                      <p className="text-sm font-medium mb-2 flex items-center gap-2">
                        <BrainCircuit className="h-4 w-4" />
                        AI Analysis & Reasoning:
                      </p>
                      <p className="text-sm text-muted-foreground whitespace-pre-wrap">{result.data.recommendations.ai_reasoning}</p>
                    </div>
                  )}
                  
                  {/* Improvement Suggestions */}
                  {result.data.recommendations?.improvement_suggestions && result.data.recommendations.improvement_suggestions.length > 0 && (
                    <div className="p-4 border rounded-lg bg-card">
                      <p className="text-sm font-medium mb-3 flex items-center gap-2">
                        <TrendingUp className="h-4 w-4" />
                        How to Reduce Timeline:
                      </p>
                      <ul className="space-y-2">
                        {result.data.recommendations.improvement_suggestions.map((suggestion, idx) => (
                          <li key={idx} className="text-sm text-muted-foreground flex items-start gap-2">
                            <span className="text-primary mt-1">•</span>
                            <span>{suggestion}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  
                  {/* Dependency Analysis */}
                  {result.data.estimates.dependency_analysis && (
                    <div className="p-3 border rounded-lg bg-card">
                      <p className="text-sm font-medium mb-2">Dependency Analysis:</p>
                      <div className="grid grid-cols-2 gap-4 text-sm">
                        <div>
                          <span className="text-muted-foreground">Critical Path: </span>
                          <span className="font-medium">{result.data.estimates.dependency_analysis.critical_path_length_days?.toFixed(1) || 'N/A'} days</span>
                        </div>
                        <div>
                          <span className="text-muted-foreground">Dependency Impact: </span>
                          <span className="font-medium">{result.data.estimates.dependency_analysis.dependency_impact_percent?.toFixed(1) || 'N/A'}%</span>
                        </div>
                      </div>
                      {result.data.estimates.dependency_analysis.bottleneck_tasks && result.data.estimates.dependency_analysis.bottleneck_tasks.length > 0 && (
                        <div className="mt-2">
                          <p className="text-xs font-medium text-muted-foreground mb-1">Bottleneck Tasks:</p>
                          <ul className="list-disc list-inside text-xs text-muted-foreground">
                            {result.data.estimates.dependency_analysis.bottleneck_tasks.map((task, idx) => (
                              <li key={idx}>{task}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  )}
                  
                  {/* Recommendations */}
                  {result.data.recommendations && (
                    <div className="p-3 border rounded-lg bg-card">
                      <p className="text-sm font-medium mb-2">Recommendations:</p>
                      <div className="space-y-2 text-sm">
                        <div>
                          <span className="text-muted-foreground">Suggested Deadline: </span>
                          <span className="font-medium">{result.data.recommendations.suggested_deadline_days?.toFixed(1) || 'N/A'} days ({result.data.recommendations.suggested_deadline_weeks?.toFixed(1) || 'N/A'} weeks)</span>
                        </div>
                        <div>
                          <span className="text-muted-foreground">Confidence Level: </span>
                          <Badge variant={result.data.recommendations.confidence_level === 'high' ? 'default' : result.data.recommendations.confidence_level === 'medium' ? 'secondary' : 'outline'}>
                            {result.data.recommendations.confidence_level || 'medium'}
                          </Badge>
                        </div>
                        {result.data.recommendations.key_risks && result.data.recommendations.key_risks.length > 0 && (
                          <div className="mt-2">
                            <p className="text-xs font-medium text-muted-foreground mb-1">Key Risks:</p>
                            <ul className="list-disc list-inside text-xs text-muted-foreground">
                              {result.data.recommendations.key_risks.map((risk, idx) => (
                                <li key={idx}>{risk}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Duration (legacy format) */}
              {result.data?.duration && (
                <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg dark:bg-blue-950 dark:border-blue-800">
                  <p className="text-sm font-medium text-blue-800 dark:text-blue-200">
                    Estimated Duration: {result.data.duration}
                  </p>
                </div>
              )}

              {/* Phases (from manage_phases action) - styled design */}
              {result.data?.phases && result.data.phases.length > 0 && (
                <div className="space-y-4 p-4 rounded-lg bg-muted/50 dark:bg-muted/30 border border-border/50">
                  <div className="flex items-center gap-2 flex-wrap">
                    <Layers className="h-5 w-5 text-primary" />
                    <h3 className="text-lg font-semibold text-foreground">Project Phases</h3>
                    {result.data.total_phases != null && (
                      <Badge variant="secondary" className="text-xs">
                        {result.data.total_phases} phase{result.data.total_phases !== 1 ? 's' : ''}
                      </Badge>
                    )}
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {result.data.phases.map((phase, index) => {
                      const phaseStyles = {
                        todo: { border: 'border-l-slate-500', bg: 'bg-muted/60 dark:bg-slate-800/70', badge: 'bg-slate-600 text-slate-100 dark:bg-slate-700 dark:text-slate-200', icon: '○' },
                        in_progress: { border: 'border-l-blue-500', bg: 'bg-muted/60 dark:bg-slate-800/70', badge: 'bg-blue-600 text-blue-100 dark:bg-blue-800/80 dark:text-blue-200', icon: '◐' },
                        review: { border: 'border-l-amber-500', bg: 'bg-muted/60 dark:bg-slate-800/70', badge: 'bg-amber-700 text-amber-100 dark:bg-amber-800/80 dark:text-amber-200', icon: '◇' },
                        done: { border: 'border-l-emerald-500', bg: 'bg-muted/60 dark:bg-slate-800/70', badge: 'bg-emerald-700 text-emerald-100 dark:bg-emerald-800/80 dark:text-emerald-200', icon: '✓' },
                        blocked: { border: 'border-l-red-400', bg: 'bg-muted/60 dark:bg-slate-800/70', badge: 'bg-red-600 text-red-100 dark:bg-red-800/80 dark:text-red-200', icon: '!' },
                      };
                      const style = phaseStyles[phase.status] || phaseStyles.todo;
                      return (
                        <Card key={index} className={`overflow-hidden border-l-4 ${style.border} ${style.bg} border border-border/50 shadow-sm`}>
                          <CardHeader className="pb-2 pt-4 px-4">
                            <div className="flex items-center justify-between gap-2">
                              <div className="flex items-center gap-2">
                                <span className="text-lg font-bold text-foreground/90" aria-hidden="true">{style.icon}</span>
                                <CardTitle className="text-base m-0">{phase.phase}</CardTitle>
                              </div>
                              <Badge className={style.badge} variant="secondary">
                                {phase.task_count} task{phase.task_count !== 1 ? 's' : ''}
                              </Badge>
                            </div>
                          </CardHeader>
                          <CardContent className="px-4 pb-4 pt-0">
                            {phase.tasks && phase.tasks.length > 0 ? (
                              <ul className="space-y-2">
                                {phase.tasks.slice(0, 10).map((task, taskIdx) => (
                                  <li key={taskIdx} className="flex items-start gap-2 text-sm py-1.5 px-2 rounded-md bg-background/80 dark:bg-background/50 border border-border/60">
                                    <span className="font-medium text-foreground truncate flex-1 min-w-0">{task.title}</span>
                                    <div className="flex items-center gap-1.5 shrink-0 flex-wrap justify-end">
                                      {task.priority && (
                                        <Badge variant="outline" className="text-xs capitalize">
                                          {task.priority}
                                        </Badge>
                                      )}
                                      {task.due_date && (
                                        <span className="text-xs text-muted-foreground whitespace-nowrap">
                                          {new Date(task.due_date).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })}
                                        </span>
                                      )}
                                    </div>
                                  </li>
                                ))}
                                {phase.tasks.length > 10 && (
                                  <li className="text-xs text-muted-foreground py-1 px-2">
                                    +{phase.tasks.length - 10} more task{phase.tasks.length - 10 !== 1 ? 's' : ''}
                                  </li>
                                )}
                              </ul>
                            ) : (
                              <p className="text-sm text-muted-foreground italic py-2">No tasks in this phase</p>
                            )}
                          </CardContent>
                        </Card>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* General Answer */}
              {result.data?.answer && (
                <div className="p-4 bg-muted rounded-lg">
                  <p className="text-sm font-medium mb-2">Analysis:</p>
                  <p className="whitespace-pre-wrap text-sm">{result.data.answer}</p>
                </div>
              )}

              {/* Error Message */}
              {result.data?.error && (
                <div className="p-4 bg-red-50 border border-red-200 rounded-lg dark:bg-red-950 dark:border-red-800">
                  <p className="text-sm font-medium text-red-800 dark:text-red-200">Error:</p>
                  <p className="text-sm text-red-700 dark:text-red-300 mt-1">{result.data.error}</p>
                </div>
              )}

              {/* No Results Message */}
              {!result.data?.gantt_chart && 
               !result.data?.timeline && 
               !result.data?.alerts && 
               !result.data?.deadline_warnings && 
               !result.data?.suggestions && 
               !result.data?.adjustments && 
               !result.data?.estimates && 
               !result.data?.duration && 
               !result.data?.phases && 
               !result.data?.answer && 
               !result.data?.error && (
                <div className="p-4 bg-muted rounded-lg text-center">
                  <p className="text-sm text-muted-foreground">No results to display for this action.</p>
                </div>
              )}
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  );
};

export default TimelineGanttAgent;
