"""
Task & Prioritization Agent
Manages tasks, assigns priorities, and optimizes task execution.
"""

from .base_agent import BaseAgent
from .enhancements.task_prioritization_enhancements import TaskPrioritizationEnhancements
from .enhancements.chart_generation import ChartGenerator
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import json


class TaskPrioritizationAgent(BaseAgent):
    """
    Agent responsible for:
    - Create, update, and delete tasks
    - Assign priority levels (High, Medium, Low)
    - Auto-prioritize tasks based on deadlines and dependencies
    - Suggest task ordering for optimal execution
    - Track task completion status
    - Assign tasks to team members
    - Calculate task effort estimates
    - Identify bottlenecks and overloaded resources
    - Suggest task delegation strategies
    """
    
    def __init__(self):
        super().__init__()
        self.system_prompt = """You are a Task & Prioritization Agent for a project management system.
        Your role is to help manage tasks, assign priorities, and optimize task execution.
        You should consider deadlines, dependencies, team capacity, and project goals when prioritizing tasks.
        Always provide clear, actionable recommendations."""
    
    def prioritize_tasks(self, tasks: List[Dict], context: Optional[Dict] = None) -> List[Dict]:
        """
        Auto-prioritize tasks based on deadlines, dependencies, and importance.
        Enhanced with multi-factor scoring and critical path analysis.
        
        Args:
            tasks (List[Dict]): List of tasks to prioritize
            context (Dict): Optional project context for enhanced analysis
            
        Returns:
            List[Dict]: Tasks with assigned priorities
        """
        self.log_action("Prioritizing tasks", {"task_count": len(tasks)})
        
        # Enhanced: Use multi-factor scoring if context available
        if context:
            try:
                # Calculate priority scores for each task
                for task in tasks:
                    priority_score = TaskPrioritizationEnhancements.calculate_priority_score(
                        task, context
                    )
                    task['priority_score'] = round(priority_score, 2)
                    
                    # Convert score to priority level
                    if priority_score >= 70:
                        task['ai_priority'] = 'high'
                    elif priority_score >= 40:
                        task['ai_priority'] = 'medium'
                    else:
                        task['ai_priority'] = 'low'
                
                # Calculate critical path
                critical_path_analysis = TaskPrioritizationEnhancements.calculate_critical_path(tasks)
                if critical_path_analysis:
                    # Add critical path info to tasks
                    critical_path_ids = {cp['task_id'] for cp in critical_path_analysis.get('critical_path', [])}
                    for task in tasks:
                        if task.get('id') in critical_path_ids:
                            task['is_critical_path'] = True
                            task['slack'] = critical_path_analysis['slack_times'].get(task['id'], {}).get('total_float', 0)
                
                # Generate charts for visualization
                try:
                    charts = {}
                    charts['priority_distribution'] = ChartGenerator.generate_priority_distribution_chart(tasks)
                    charts['status_distribution'] = ChartGenerator.generate_status_distribution_chart(tasks)
                    
                    # Add priority score chart if scores are available
                    if any('priority_score' in task for task in tasks):
                        charts['priority_scores'] = ChartGenerator.generate_priority_score_chart(tasks)
                    
                    # Add critical path chart if available
                    if critical_path_analysis and critical_path_analysis.get('critical_path'):
                        charts['critical_path'] = ChartGenerator.generate_critical_path_chart(
                            critical_path_analysis['critical_path']
                        )
                    
                    context['charts'] = charts
                except Exception as e:
                    self.log_action("Chart generation failed", {"error": str(e)})
            except Exception as e:
                self.log_action("Enhanced prioritization failed, using fallback", {"error": str(e)})
        
        # Calculate workload analysis
        workload_by_user = {}
        if context and 'workload_analysis' in context:
            workload_by_user = context['workload_analysis'].get('workload_by_user', {})
        
        # Prepare comprehensive task data for AI analysis
        tasks_summary = []
        for task in tasks:
            assignee_id = task.get('assignee_id')
            assignee_workload = workload_by_user.get(assignee_id, {}) if assignee_id else {}
            
            task_info = {
                "id": task.get('id', ''),
                "title": task.get('title', ''),
                "description": task.get('description', '')[:200] if task.get('description') else '',
                "due_date": str(task.get('due_date', '')),
                "status": task.get('status', ''),
                "current_priority": task.get('priority', 'medium'),
                "estimated_hours": task.get('estimated_hours'),
                "actual_hours": task.get('actual_hours'),
                "dependencies": task.get('dependencies', []),
                "dependent_count": task.get('dependent_count', 0),
                "assignee_name": task.get('assignee_name'),
                "assignee_workload": {
                    "active_tasks": assignee_workload.get('active_tasks', 0),
                    "total_hours": assignee_workload.get('total_estimated_hours', 0),
                    "is_overloaded": assignee_workload.get('overloaded', False)
                } if assignee_id else None,
                "progress_percentage": task.get('progress_percentage'),
                "is_critical_path": task.get('is_critical_path', False),
                "priority_score": task.get('priority_score'),
            }
            tasks_summary.append(task_info)
        
        # Get project context
        project_info = context.get('project', {}) if context else {}
        team_size = context.get('workload_analysis', {}).get('team_size', 1) if context else 1
        
        prompt = f"""You are an expert project prioritization analyst. Analyze these tasks and provide comprehensive priority recommendations.

PROJECT CONTEXT:
- Project: {project_info.get('name', 'N/A')}
- Status: {project_info.get('status', 'N/A')}
- Team Size: {team_size} members
- Total Tasks: {len(tasks)}

TASK DATA:
{json.dumps(tasks_summary, indent=2)}

ANALYSIS REQUIREMENTS:
Analyze each task considering:

1. DEADLINE URGENCY:
   - Overdue tasks = highest priority
   - Tasks due within 1-3 days = high priority
   - Tasks due within 4-7 days = medium-high priority
   - Tasks due within 8-14 days = medium priority
   - Tasks due later = lower priority (unless other factors override)

2. DEPENDENCY CRITICALITY:
   - Tasks blocking many others (high dependent_count) = high priority
   - Tasks on critical path = high priority
   - Tasks with no dependencies = can be parallelized (medium priority)
   - Tasks with many dependencies = may need to wait (lower priority)

3. BUSINESS VALUE & IMPACT:
   - Analyze task title and description to assess business value
   - High-value tasks that unlock other work = high priority
   - Tasks critical to project goals = high priority
   - Low-value or nice-to-have tasks = lower priority

4. TEAM WORKLOAD & CAPACITY:
   - If assignee is overloaded (>8 active tasks or >40 hours), consider reassignment
   - Balance workload across team members
   - Consider team member availability and current commitments

5. RISK ASSESSMENT:
   - Blocked tasks = high risk, high priority
   - Tasks significantly over estimate (actual > 1.5x estimated) = high risk
   - High priority tasks not started = high risk
   - Tasks with many dependencies = higher risk of delays

6. STATUS & PROGRESS:
   - In-progress tasks should continue (maintain or increase priority)
   - Completed tasks = lowest priority
   - Tasks with good progress (>50%) = maintain momentum

7. IMPACT ANALYSIS:
   - How does prioritizing this task affect other tasks?
   - Does it unblock other work?
   - Does it delay critical path?

For EACH task, provide:
- recommended_priority: "high", "medium", or "low"
- priority_score: number (0-100) indicating priority strength
- business_value: "high|medium|low" - estimated business impact
- risk_level: "high|medium|low" - risk of delays or issues
- impact_on_others: "high|medium|low" - how this task affects other tasks
- time_to_completion_estimate: estimated days to complete if prioritized now
- reasoning: DETAILED explanation (6-8 sentences) covering:
  * WHY this priority level is appropriate (specific factors)
  * WHAT business value or impact this task provides
  * HOW this priority affects project timeline and other tasks
  * WHAT risks are associated with this task
  * HOW team workload and capacity factor into this decision
  * WHAT should be done first and why (specific execution strategy)
  * HOW to approach this task given its priority and constraints
  * WHAT dependencies or blockers need to be addressed
- suggested_order: Number indicating execution order (1 = first)
- actionable_recommendations: Array of 2-3 specific, actionable steps to execute this task effectively

Return JSON array:
[
  {{
    "id": "task_id",
    "recommended_priority": "high|medium|low",
    "priority_score": 85,
    "business_value": "high|medium|low",
    "risk_level": "high|medium|low",
    "impact_on_others": "high|medium|low",
    "time_to_completion_estimate": 5,
    "reasoning": "Comprehensive 6-8 sentence explanation covering all factors...",
    "suggested_order": 1,
    "actionable_recommendations": [
      "Specific action 1",
      "Specific action 2",
      "Specific action 3"
    ]
  }}
]"""
        
        try:
            response = self._call_llm(prompt, self.system_prompt, temperature=0.3)
            
            # Parse AI response
            # Try to extract JSON from response
            if "```json" in response:
                json_start = response.find("```json") + 7
                json_end = response.find("```", json_start)
                response = response[json_start:json_end].strip()
            elif "```" in response:
                json_start = response.find("```") + 3
                json_end = response.find("```", json_start)
                response = response[json_start:json_end].strip()
            
            priorities = json.loads(response)
            
            # Update tasks with priorities and enhanced reasoning
            priority_map = {str(item['id']): item for item in priorities}
            high_priority_count = 0
            medium_priority_count = 0
            low_priority_count = 0
            
            # Build dependency map for better reasoning
            dependency_map = {}
            for task in tasks:
                task_id = str(task.get('id', ''))
                deps = task.get('dependencies', [])
                for dep_id in deps:
                    dep_id_str = str(dep_id)
                    if dep_id_str not in dependency_map:
                        dependency_map[dep_id_str] = []
                    dependency_map[dep_id_str].append(task_id)
            
            for task in tasks:
                task_id = str(task.get('id', ''))
                if task_id in priority_map:
                    priority_data = priority_map[task_id]
                    task['ai_priority'] = priority_data.get('recommended_priority', 'medium')
                    task['priority_score'] = priority_data.get('priority_score', task.get('priority_score', 50))
                    task['business_value'] = priority_data.get('business_value', 'medium')
                    task['risk_level'] = priority_data.get('risk_level', 'medium')
                    task['impact_on_others'] = priority_data.get('impact_on_others', 'medium')
                    task['time_to_completion_estimate'] = priority_data.get('time_to_completion_estimate')
                    task['actionable_recommendations'] = priority_data.get('actionable_recommendations', [])
                    task['suggested_order'] = priority_data.get('suggested_order', 999)
                    
                    # Get tasks that depend on this task
                    dependent_tasks = dependency_map.get(task_id, [])
                    dependent_count = len(dependent_tasks)
                    
                    # Store comprehensive reasoning (will be enhanced with order reasoning later)
                    task['ai_reasoning'] = priority_data.get('reasoning', '')
                    task['dependent_task_count'] = dependent_count
                    task['dependent_task_ids'] = dependent_tasks
                    
                    # Count priorities
                    if task['ai_priority'] == 'high':
                        high_priority_count += 1
                    elif task['ai_priority'] == 'medium':
                        medium_priority_count += 1
                    else:
                        low_priority_count += 1
            
            # Generate AI summary of prioritization strategy with overall reasoning
            summary_prompt = f"""Based on the prioritization analysis of {len(tasks)} tasks, provide a comprehensive summary:

Priority Distribution:
- High Priority: {high_priority_count} tasks
- Medium Priority: {medium_priority_count} tasks  
- Low Priority: {low_priority_count} tasks

Task Details:
{json.dumps([{"id": t.get('id'), "title": t.get('title'), "ai_priority": t.get('ai_priority'), "priority_score": t.get('priority_score'), "business_value": t.get('business_value'), "risk_level": t.get('risk_level')} for t in tasks[:10]], indent=2)}

Provide a summary JSON with:
{{
  "prioritization_strategy": "2-3 sentence overview of the overall prioritization approach",
  "overall_reasoning": "DETAILED explanation (6-8 sentences): WHY this prioritization is better than other approaches. Explain the strategic thinking behind prioritizing these tasks in this way, HOW this prioritization maximizes project value and minimizes risks, WHAT benefits this approach provides (faster delivery, better resource utilization, risk mitigation), HOW this prioritization aligns with project goals and deadlines, and WHY this specific order of priorities will lead to better project outcomes.",
  "key_insights": [
    "Insight 1 about the prioritization",
    "Insight 2 about risks or opportunities",
    "Insight 3 about team workload or capacity"
  ],
  "top_recommendations": [
    "Specific actionable recommendation 1",
    "Specific actionable recommendation 2",
    "Specific actionable recommendation 3"
  ],
  "risk_alerts": [
    "Risk or concern 1 that needs attention",
    "Risk or concern 2 that needs attention"
  ],
  "workload_concerns": "Analysis of team workload and capacity issues, if any"
}}"""
            
            try:
                summary_response = self._call_llm(summary_prompt, self.system_prompt, temperature=0.3, max_tokens=800)
                if "```json" in summary_response:
                    json_start = summary_response.find("```json") + 7
                    json_end = summary_response.find("```", json_start)
                    summary_response = summary_response[json_start:json_end].strip()
                elif "```" in summary_response:
                    json_start = summary_response.find("```") + 3
                    json_end = summary_response.find("```", json_start)
                    if json_end > json_start:
                        summary_response = summary_response[json_start:json_end].strip()
                summary = json.loads(summary_response)
            except Exception as e:
                self.log_action("Summary generation failed", {"error": str(e)})
                summary = {
                    "prioritization_strategy": f"Prioritized {len(tasks)} tasks with {high_priority_count} high, {medium_priority_count} medium, and {low_priority_count} low priority tasks.",
                    "key_insights": [],
                    "top_recommendations": [],
                    "risk_alerts": [],
                    "workload_concerns": ""
                }
            
            # Build return value with all enhancements
            result_data = {
                'tasks': tasks,
                'summary': summary,
                'statistics': {
                    'total_tasks': len(tasks),
                    'high_priority': high_priority_count,
                    'medium_priority': medium_priority_count,
                    'low_priority': low_priority_count,
                    'tasks_with_dependencies': len([t for t in tasks if t.get('dependencies')]),
                    'tasks_on_critical_path': len([t for t in tasks if t.get('is_critical_path')]),
                }
            }
            
            # Add charts if available
            if context and 'charts' in context:
                result_data['charts'] = context['charts']
                result_data['critical_path_analysis'] = context.get('critical_path_analysis')
            
            # Add workload analysis
            if context and 'workload_analysis' in context:
                result_data['workload_analysis'] = context['workload_analysis']
            
            return result_data
            
        except Exception as e:
            self.log_action("Error prioritizing tasks", {"error": str(e)})
            # Fallback: simple priority based on due date
            for task in tasks:
                due_date = task.get('due_date')
                if due_date:
                    try:
                        due = datetime.fromisoformat(str(due_date).replace('Z', '+00:00'))
                        days_until = (due - datetime.now()).days
                        if days_until < 3:
                            task['ai_priority'] = 'high'
                        elif days_until < 7:
                            task['ai_priority'] = 'medium'
                        else:
                            task['ai_priority'] = 'low'
                    except:
                        task['ai_priority'] = task.get('priority', 'medium')
                else:
                    task['ai_priority'] = task.get('priority', 'medium')
            return tasks
    
    def predict_priority_changes(self, tasks: List[Dict], days_ahead: int = 7) -> List[Dict]:
        """
        Predict how priorities should change in the future.
        
        Args:
            tasks (List[Dict]): List of tasks
            days_ahead (int): Number of days to look ahead
            
        Returns:
            List[Dict]: Predicted priority changes
        """
        return TaskPrioritizationEnhancements.predict_priority_changes(tasks, days_ahead)
    
    def suggest_task_order(self, tasks: List[Dict], team_members: List[Dict] = None, context: Optional[Dict] = None) -> Dict:
        """
        Suggest optimal task ordering for execution with parallel execution groups.
        
        Args:
            tasks (List[Dict]): List of tasks
            team_members (List[Dict]): Optional team members for resource analysis
            context (Dict): Optional project context
            
        Returns:
            Dict: Tasks in suggested execution order with parallel groups and analysis
        """
        self.log_action("Suggesting task order", {"task_count": len(tasks)})
        
        # Calculate workload if team members provided
        workload_by_user = {}
        if team_members:
            for member in team_members:
                member_tasks = [t for t in tasks if t.get('assignee_id') == member.get('id')]
                active_tasks = [t for t in member_tasks if t.get('status') in ['todo', 'in_progress', 'review']]
                workload_by_user[member.get('id')] = {
                    'active_tasks': len(active_tasks),
                    'total_hours': sum(t.get('estimated_hours', 0) or 0 for t in active_tasks)
                }
        
        tasks_data = []
        for task in tasks:
            assignee_id = task.get('assignee_id')
            assignee_workload = workload_by_user.get(assignee_id, {}) if assignee_id else {}
            
            tasks_data.append({
                "id": task.get('id', ''),
                "title": task.get('title', ''),
                "description": task.get('description', '')[:150] if task.get('description') else '',
                "dependencies": task.get('dependencies', []),
                "dependent_count": task.get('dependent_count', 0),
                "due_date": str(task.get('due_date', '')),
                "priority": task.get('priority', 'medium'),
                "status": task.get('status', ''),
                "estimated_hours": task.get('estimated_hours'),
                "assignee_name": task.get('assignee_name'),
                "assignee_workload": assignee_workload if assignee_id else None,
            })
        
        team_size = len(team_members) if team_members else 1
        
        prompt = f"""You are an expert project sequencing analyst. Analyze these tasks and suggest optimal execution order with parallel execution groups.

TEAM CONTEXT:
- Team Size: {team_size} members
- Tasks can be executed in parallel by different team members

TASK DATA:
{json.dumps(tasks_data, indent=2)}

ANALYSIS REQUIREMENTS:

1. DEPENDENCY ANALYSIS:
   - Tasks with no dependencies can run in parallel
   - Tasks that block others must come first
   - Identify dependency chains and critical path

2. PARALLEL EXECUTION OPPORTUNITIES:
   - Group tasks that can be done simultaneously
   - Consider team size for parallelization
   - Balance workload across team members

3. RESOURCE CONFLICTS:
   - Identify tasks competing for same assignee
   - Suggest workload balancing
   - Detect resource bottlenecks

4. MILESTONE-BASED ORDERING:
   - Group tasks by logical project phases
   - Identify milestone dependencies
   - Suggest buffer times between phases

5. OPTIMAL SEQUENCING:
   - Minimize project duration
   - Maximize parallel execution
   - Respect dependencies and constraints

For EACH task, provide:
- execution_order: Number (1 = first, tasks with same number can run in parallel)
- parallel_group: Group ID for tasks that can run simultaneously (same group = can parallelize)
- milestone_phase: "phase_1|phase_2|phase_3" - which project phase this belongs to
- resource_conflicts: Array of task IDs that compete for same resources
- buffer_recommended: Number of days buffer before this task (0 if none)
- reasoning: DETAILED explanation (6-8 sentences):
  * WHY this task should be done at this position
  * WHAT dependencies or prerequisites make this order optimal
  * HOW this sequencing affects project flow and timeline
  * WHAT happens if this order is changed
  * HOW to execute this task in this position
  * WHICH tasks can run in parallel with this one
  * WHAT resources or constraints need consideration

Return JSON:
{{
  "execution_plan": [
    {{
      "id": "task_id",
      "execution_order": 1,
      "parallel_group": 1,
      "milestone_phase": "phase_1",
      "resource_conflicts": ["task_id2"],
      "buffer_recommended": 0,
      "reasoning": "Comprehensive explanation..."
    }}
  ],
  "parallel_groups": [
    {{
      "group_id": 1,
      "tasks": ["task_id1", "task_id2"],
      "can_parallelize": true,
      "reasoning": "These tasks have no dependencies and can run simultaneously"
    }}
  ],
  "milestones": [
    {{
      "phase": "phase_1",
      "tasks": ["task_id1", "task_id2"],
      "estimated_duration_days": 5,
      "description": "Description of this phase"
    }}
  ],
  "summary": {{
    "total_sequential_days": 15,
    "parallel_execution_saves_days": 5,
    "optimized_duration_days": 10,
    "key_insights": ["insight1", "insight2"],
    "recommendations": ["recommendation1", "recommendation2"]
  }}
}}"""
        
        try:
            response = self._call_llm(prompt, self.system_prompt, temperature=0.3, max_tokens=2500)
            
            # Extract JSON
            if "```json" in response:
                json_start = response.find("```json") + 7
                json_end = response.find("```", json_start)
                response = response[json_start:json_end].strip()
            elif "```" in response:
                json_start = response.find("```") + 3
                json_end = response.find("```", json_start)
                if json_end > json_start:
                    response = response[json_start:json_end].strip()
            
            order_analysis = json.loads(response)
            execution_plan = order_analysis.get('execution_plan', [])
            order_map = {str(item['id']): item for item in execution_plan}
            
            # Build dependency map for enhanced reasoning
            dependency_map = {}
            task_title_map = {str(t.get('id', '')): t.get('title', 'Unknown') for t in tasks}
            for task in tasks:
                task_id = str(task.get('id', ''))
                deps = task.get('dependencies', [])
                for dep_id in deps:
                    dep_id_str = str(dep_id)
                    if dep_id_str not in dependency_map:
                        dependency_map[dep_id_str] = []
                    dependency_map[dep_id_str].append({
                        'id': task_id,
                        'title': task.get('title', 'Unknown')
                    })
            
            # Generate combined reasoning for each task
            for task in tasks:
                task_id = str(task.get('id', ''))
                if task_id in order_map:
                    order_data = order_map[task_id]
                    task['execution_order'] = order_data.get('execution_order', 999)
                    task['parallel_group'] = order_data.get('parallel_group')
                    task['milestone_phase'] = order_data.get('milestone_phase')
                    task['resource_conflicts'] = order_data.get('resource_conflicts', [])
                    task['buffer_recommended'] = order_data.get('buffer_recommended', 0)
                    
                    # Get tasks that depend on this task
                    dependent_tasks = dependency_map.get(task_id, [])
                    dependent_count = len(dependent_tasks)
                    dependent_titles = [dt['title'] for dt in dependent_tasks[:3]]  # Show first 3
                    
                    # Get task dependencies
                    task_dependencies = task.get('dependencies', [])
                    dependency_titles = [task_title_map.get(str(dep_id), 'Unknown') for dep_id in task_dependencies[:3]]
                    
                    # Generate enhanced combined reasoning
                    combined_reasoning_prompt = f"""Generate a comprehensive, project-focused reasoning for this task in the execution order:

Task: {task.get('title', 'Unknown')}
Task ID: {task_id}
Execution Order: {order_data.get('execution_order', 999)}
Priority: {task.get('ai_priority', 'medium')}
Business Value: {task.get('business_value', 'medium')}
Risk Level: {task.get('risk_level', 'medium')}
Parallel Group: {order_data.get('parallel_group', 'N/A')}
Milestone Phase: {order_data.get('milestone_phase', 'N/A')}

Dependencies (tasks this depends on): {', '.join(dependency_titles) if dependency_titles else 'None'}
Tasks that depend on this task ({dependent_count} total): {', '.join(dependent_titles) if dependent_titles else 'None'}

Current Priority Reasoning: {task.get('ai_reasoning', '')[:200]}
Current Order Reasoning: {order_data.get('reasoning', '')[:200]}

Generate a SINGLE, comprehensive reasoning (6-8 sentences) that:
1. Explains WHY this task should be done at this position in the execution order
2. Mentions SPECIFIC dependency information: "This task should be done before [X tasks] because [Y tasks] depend on it" or "This task must be done after [X tasks] because it depends on them"
3. Explains HOW this position optimizes the project timeline and workflow
4. Mentions parallelization opportunities if applicable (parallel group)
5. Explains the strategic importance considering priority, business value, and risk
6. Provides project context about how this task fits into the overall execution plan

Return ONLY the reasoning text (no prefixes, no labels, just the reasoning). Make it natural and project-focused."""
                    
                    try:
                        combined_reasoning = self._call_llm(combined_reasoning_prompt, self.system_prompt, temperature=0.3, max_tokens=300)
                        # Clean up the response
                        combined_reasoning = combined_reasoning.strip()
                        # Remove any prefixes if AI added them
                        for prefix in ["[Reasoning]", "Reasoning:", "Reasoning"]:
                            if combined_reasoning.startswith(prefix):
                                combined_reasoning = combined_reasoning[len(prefix):].strip()
                        task['ai_reasoning'] = combined_reasoning
                    except Exception as e:
                        self.log_action("Combined reasoning generation failed", {"error": str(e), "task_id": task_id})
                        # Fallback: combine existing reasoning
                        priority_reasoning = task.get('ai_reasoning', '')
                        order_reasoning = order_data.get('reasoning', '')
                        if priority_reasoning and order_reasoning:
                            # Merge intelligently
                            if dependent_count > 0:
                                task['ai_reasoning'] = f"{priority_reasoning} This task should be completed at position {order_data.get('execution_order', 999)} because {dependent_count} task(s) depend on it. {order_reasoning}"
                            else:
                                task['ai_reasoning'] = f"{priority_reasoning} {order_reasoning}"
                        else:
                            task['ai_reasoning'] = priority_reasoning or order_reasoning or "Task reasoning not available."
            
            # Sort tasks by suggested order
            sorted_tasks = sorted(tasks, key=lambda t: order_map.get(str(t.get('id', '')), {}).get('execution_order', 999))
            
            # Calculate durations if not provided or if they're 0
            if not order_analysis.get('summary') or order_analysis.get('summary', {}).get('total_sequential_days', 0) == 0:
                # Calculate based on task estimated hours
                total_hours = sum(t.get('estimated_hours', 0) or 0 for t in sorted_tasks)
                # Assume 8 hours per day, 5 days per week
                sequential_days = (total_hours / 8) if total_hours > 0 else len(sorted_tasks) * 2
                
                # Calculate optimized duration based on parallel groups
                if order_analysis.get('parallel_groups'):
                    # Find the longest path through parallel groups
                    max_group_duration = 0
                    for group in order_analysis.get('parallel_groups', []):
                        group_tasks = [t for t in sorted_tasks if str(t.get('id')) in [str(tid) for tid in group.get('tasks', [])]]
                        group_hours = sum(t.get('estimated_hours', 0) or 0 for t in group_tasks)
                        group_days = (group_hours / 8) if group_hours > 0 else len(group_tasks) * 2
                        max_group_duration = max(max_group_duration, group_days)
                    
                    # Sum up milestone durations if available
                    if order_analysis.get('milestones'):
                        optimized_days = sum(m.get('estimated_duration_days', 0) for m in order_analysis.get('milestones', []))
                        if optimized_days == 0:
                            optimized_days = max_group_duration * len(order_analysis.get('milestones', [])) if order_analysis.get('milestones') else max_group_duration
                    else:
                        optimized_days = max_group_duration if max_group_duration > 0 else sequential_days * 0.7
                else:
                    # No parallel groups, use sequential but with some optimization
                    optimized_days = sequential_days * 0.8 if sequential_days > 0 else len(sorted_tasks) * 1.5
                
                # Update summary with calculated values
                if not order_analysis.get('summary'):
                    order_analysis['summary'] = {}
                order_analysis['summary']['total_sequential_days'] = round(sequential_days, 1)
                order_analysis['summary']['optimized_duration_days'] = round(optimized_days, 1)
                order_analysis['summary']['parallel_execution_saves_days'] = round(sequential_days - optimized_days, 1)
            
            # Generate overall reasoning for why this order is better
            overall_reasoning_prompt = f"""Based on the task ordering analysis, provide a comprehensive explanation of why this execution order is optimal:

Execution Plan Summary:
- Total Tasks: {len(sorted_tasks)}
- Sequential Duration: {order_analysis.get('summary', {}).get('total_sequential_days', 0)} days
- Optimized Duration: {order_analysis.get('summary', {}).get('optimized_duration_days', 0)} days
- Time Saved: {order_analysis.get('summary', {}).get('parallel_execution_saves_days', 0)} days

Task Order:
{json.dumps([{"order": t.get('execution_order'), "title": t.get('title'), "parallel_group": t.get('parallel_group'), "milestone_phase": t.get('milestone_phase')} for t in sorted_tasks[:15]], indent=2)}

Parallel Groups: {len(order_analysis.get('parallel_groups', []))}
Milestones: {len(order_analysis.get('milestones', []))}

Provide a detailed JSON response:
{{
  "overall_reasoning": "DETAILED explanation (8-10 sentences): WHY this execution order is better than other possible orders. Explain the strategic thinking behind this sequencing, HOW this order minimizes project duration through parallelization, WHAT dependencies and constraints were considered, HOW this order optimizes resource utilization and team capacity, WHY tasks are grouped in this way (parallel groups and milestones), WHAT benefits this order provides (faster delivery, reduced bottlenecks, better workflow), HOW this order minimizes risks and dependencies, and WHY this specific sequence will lead to the most efficient project completion.",
  "optimization_benefits": [
    "Benefit 1 of this order",
    "Benefit 2 of this order",
    "Benefit 3 of this order"
  ],
  "key_considerations": [
    "Consideration 1 that influenced the order",
    "Consideration 2 that influenced the order"
  ]
}}"""
            
            try:
                reasoning_response = self._call_llm(overall_reasoning_prompt, self.system_prompt, temperature=0.3, max_tokens=1000)
                if "```json" in reasoning_response:
                    json_start = reasoning_response.find("```json") + 7
                    json_end = reasoning_response.find("```", json_start)
                    reasoning_response = reasoning_response[json_start:json_end].strip()
                elif "```" in reasoning_response:
                    json_start = reasoning_response.find("```") + 3
                    json_end = reasoning_response.find("```", json_start)
                    if json_end > json_start:
                        reasoning_response = reasoning_response[json_start:json_end].strip()
                overall_reasoning = json.loads(reasoning_response)
                
                # Merge overall reasoning into summary
                if order_analysis.get('summary'):
                    order_analysis['summary']['overall_reasoning'] = overall_reasoning.get('overall_reasoning', '')
                    order_analysis['summary']['optimization_benefits'] = overall_reasoning.get('optimization_benefits', [])
                    order_analysis['summary']['key_considerations'] = overall_reasoning.get('key_considerations', [])
                else:
                    order_analysis['summary'] = overall_reasoning
            except Exception as e:
                self.log_action("Overall reasoning generation failed", {"error": str(e)})
                if not order_analysis.get('summary'):
                    order_analysis['summary'] = {}
                order_analysis['summary']['overall_reasoning'] = f"This execution order optimizes project duration through strategic parallelization and dependency management."
            
            # Return enhanced result with parallel groups and milestones
            return {
                'tasks': sorted_tasks,
                'parallel_groups': order_analysis.get('parallel_groups', []),
                'milestones': order_analysis.get('milestones', []),
                'summary': order_analysis.get('summary', {})
            }
            
        except Exception as e:
            self.log_action("Error suggesting task order", {"error": str(e)})
            # Fallback: sort by priority and due date
            sorted_tasks = sorted(tasks, key=lambda t: (
                {'high': 0, 'medium': 1, 'low': 2}.get(t.get('priority', 'medium'), 1),
                t.get('due_date', datetime.max) if t.get('due_date') else datetime.max
            ))
            return {
                'tasks': sorted_tasks,
                'parallel_groups': [],
                'milestones': [],
                'summary': {
                    'total_sequential_days': len(sorted_tasks) * 3,
                    'parallel_execution_saves_days': 0,
                    'optimized_duration_days': len(sorted_tasks) * 3,
                    'key_insights': ['Fallback ordering used'],
                    'recommendations': ['Review task dependencies for better ordering']
                }
            }
    
    def calculate_effort_estimate(self, task: Dict) -> Dict:
        """
        Calculate effort estimate for a task.
        
        Args:
            task (Dict): Task information
            
        Returns:
            Dict: Effort estimate with time and complexity
        """
        self.log_action("Calculating effort estimate", {"task": task.get('title', '')})
        
        prompt = f"""Estimate the effort required for this task:

Title: {task.get('title', '')}
Description: {task.get('description', '')}
Current Status: {task.get('status', '')}
Priority: {task.get('priority', 'medium')}

Provide an effort estimate including:
1. Estimated hours (number)
2. Complexity level (low, medium, high)
3. Reasoning (brief explanation)

Return JSON format:
{{
  "estimated_hours": 8,
  "complexity": "medium",
  "reasoning": "explanation"
}}"""
        
        try:
            response = self._call_llm(prompt, self.system_prompt, temperature=0.3)
            
            # Extract JSON
            if "```json" in response:
                json_start = response.find("```json") + 7
                json_end = response.find("```", json_start)
                response = response[json_start:json_end].strip()
            elif "```" in response:
                json_start = response.find("```") + 3
                json_end = response.find("```", json_start)
                response = response[json_start:json_end].strip()
            
            estimate = json.loads(response)
            return estimate
            
        except Exception as e:
            self.log_action("Error calculating effort", {"error": str(e)})
            # Fallback estimate
            return {
                "estimated_hours": 4,
                "complexity": "medium",
                "reasoning": "Default estimate (AI analysis unavailable)"
            }
    
    def identify_bottlenecks(self, tasks: List[Dict], team_members: List[Dict], context: Optional[Dict] = None) -> Dict:
        """
        Identify bottlenecks and overloaded resources with comprehensive analysis.
        
        Args:
            tasks (List[Dict]): List of tasks
            team_members (List[Dict]): List of team members
            context (Dict): Optional project context
            
        Returns:
            Dict: Comprehensive bottleneck analysis with workload heatmap and dependency chains
        """
        self.log_action("Identifying bottlenecks", {"tasks": len(tasks), "team": len(team_members)})
        
        # Calculate comprehensive workload analysis
        workload_by_user = {}
        active_tasks_by_user = {}
        hours_by_user = {}
        
        for task in tasks:
            assignee_id = task.get('assignee_id')
            if assignee_id:
                if assignee_id not in workload_by_user:
                    workload_by_user[assignee_id] = 0
                    active_tasks_by_user[assignee_id] = []
                    hours_by_user[assignee_id] = 0
                
                workload_by_user[assignee_id] += 1
                if task.get('status') in ['todo', 'in_progress', 'review']:
                    active_tasks_by_user[assignee_id].append(task)
                    hours_by_user[assignee_id] += task.get('estimated_hours', 0) or 0
        
        # Find overloaded members with detailed metrics
        overloaded = []
        for member in team_members:
            member_id = member.get('id')
            task_count = workload_by_user.get(member_id, 0)
            active_count = len(active_tasks_by_user.get(member_id, []))
            total_hours = hours_by_user.get(member_id, 0)
            
            # Enhanced thresholds
            is_overloaded = active_count > 8 or total_hours > 40 or task_count > 10
            
            if is_overloaded:
                overloaded.append({
                    "member_id": member_id,
                    "member": member.get('name', 'Unknown'),
                    "task_count": task_count,
                    "active_task_count": active_count,
                    "total_hours": round(total_hours, 1),
                    "status": "overloaded",
                    "severity": "critical" if active_count > 12 or total_hours > 60 else "high"
                })
        
        # Find blocking tasks and dependency chains
        blocking_tasks = [t for t in tasks if t.get('status') == 'blocked']
        
        # Build dependency chains
        dependency_chains = {}
        for task in tasks:
            deps = task.get('dependencies', [])
            if deps:
                for dep_id in deps:
                    if dep_id not in dependency_chains:
                        dependency_chains[dep_id] = []
                    dependency_chains[dep_id].append(task.get('id'))
        
        # Find critical dependency chains (tasks blocking many others)
        critical_dependencies = {k: v for k, v in dependency_chains.items() if len(v) >= 3}
        
        # Prepare comprehensive task data for AI
        tasks_summary = []
        for task in tasks:
            assignee_id = task.get('assignee_id')
            is_in_critical_chain = task.get('id') in critical_dependencies or task.get('id') in [k for k, v in critical_dependencies.items()]
            
            tasks_summary.append({
                "id": task.get('id', ''),
                "title": task.get('title', ''),
                "status": task.get('status', ''),
                "priority": task.get('priority', 'medium'),
                "due_date": str(task.get('due_date', '')),
                "estimated_hours": task.get('estimated_hours'),
                "dependencies": task.get('dependencies', []),
                "dependent_count": task.get('dependent_count', 0),
                "assignee_name": task.get('assignee_name'),
                "is_blocking_others": task.get('id') in critical_dependencies,
                "blocks_count": len(dependency_chains.get(task.get('id'), [])),
                "progress_percentage": task.get('progress_percentage', 0),
            })
        
        prompt = f"""You are an expert bottleneck analysis specialist. Analyze this project data and identify ALL bottlenecks with comprehensive analysis.

PROJECT CONTEXT:
- Total Tasks: {len(tasks)}
- Team Members: {len(team_members)}
- Overloaded Members: {len(overloaded)}
- Blocking Tasks: {len(blocking_tasks)}
- Critical Dependency Chains: {len(critical_dependencies)}

WORKLOAD ANALYSIS:
{json.dumps([{"member": m.get('name'), "active_tasks": len(active_tasks_by_user.get(m.get('id'), [])), "total_hours": hours_by_user.get(m.get('id'), 0)} for m in team_members], indent=2)}

TASK DATA:
{json.dumps(tasks_summary, indent=2)}

ANALYSIS REQUIREMENTS:

1. RESOURCE OVERLOAD BOTTLENECKS:
   - Identify team members with excessive workload
   - Calculate impact on project timeline
   - Suggest workload redistribution strategies

2. DEPENDENCY CHAIN BOTTLENECKS:
   - Identify tasks blocking many others
   - Analyze critical path dependencies
   - Suggest parallelization opportunities

3. TASK BLOCKING BOTTLENECKS:
   - Identify blocked tasks and root causes
   - Analyze why tasks are blocked
   - Suggest unblocking strategies

4. WORKLOAD HEATMAP:
   - Identify workload distribution patterns
   - Find capacity imbalances
   - Suggest resource reallocation

5. SEVERITY SCORING:
   - Rate each bottleneck severity (critical/high/medium/low)
   - Calculate impact on project delivery
   - Prioritize resolution order

For EACH bottleneck, provide:
- type: "resource_overload|dependency_chain|task_blocking|workload_imbalance|skill_gap"
- description: Clear description of the bottleneck
- severity: "critical|high|medium|low" with severity_score (0-100)
- affected_tasks: Array of affected task IDs with detailed reasoning
- affected_resources: Array of affected team members
- impact_analysis: "DETAILED explanation (4-6 sentences): How this bottleneck impacts project timeline, delivery, quality, and team morale. What is the estimated delay? What are the cascading effects?"
- root_cause: "DETAILED explanation (3-4 sentences): Why this bottleneck exists. What are the underlying causes? What led to this situation?"
- resolution_strategy: "DETAILED actionable steps (3-5 steps) to resolve this bottleneck immediately"
- preventive_measures: "DETAILED steps (2-3 steps) to prevent this bottleneck from recurring"
- estimated_resolution_time: Number of days to resolve
- priority: "immediate|high|medium|low" - resolution priority

For EACH affected task, provide:
- task_id: Task ID
- task_reasoning: "DETAILED explanation (4-6 sentences): Why this task is part of the bottleneck, how the bottleneck affects this task's execution, what should be done to unblock this task, and how to prevent it from becoming a bottleneck again."

Return JSON:
{{
  "bottlenecks": [
    {{
      "type": "resource_overload",
      "description": "Clear description",
      "severity": "critical",
      "severity_score": 95,
      "affected_tasks": [
        {{
          "task_id": "task_id1",
          "task_reasoning": "Detailed explanation..."
        }}
      ],
      "affected_resources": ["member_name1"],
      "impact_analysis": "Detailed impact explanation...",
      "root_cause": "Detailed root cause...",
      "resolution_strategy": ["Step 1", "Step 2", "Step 3"],
      "preventive_measures": ["Measure 1", "Measure 2"],
      "estimated_resolution_time": 3,
      "priority": "immediate"
    }}
  ],
  "workload_heatmap": {{
    "overloaded_members": [
      {{
        "member": "name",
        "active_tasks": 12,
        "total_hours": 50,
        "capacity_utilization": 125,
        "recommendation": "Reduce workload by X tasks or Y hours"
      }}
    ],
    "underutilized_members": [
      {{
        "member": "name",
        "active_tasks": 2,
        "total_hours": 10,
        "capacity_utilization": 25,
        "recommendation": "Can take on X more tasks"
      }}
    ]
  }},
  "dependency_chain_analysis": {{
    "critical_chains": [
      {{
        "chain_id": "chain_1",
        "tasks": ["task_id1", "task_id2"],
        "blocking_count": 5,
        "estimated_delay_days": 3,
        "recommendation": "Break dependency or parallelize"
      }}
    ]
  }},
  "summary": {{
    "total_bottlenecks": 3,
    "critical_count": 1,
    "high_count": 2,
    "estimated_project_delay_days": 5,
    "key_insights": ["insight1", "insight2"],
    "top_priorities": ["priority1", "priority2"]
  }}
}}"""
        
        try:
            response = self._call_llm(prompt, self.system_prompt, temperature=0.3, max_tokens=3000)
            
            # Extract JSON
            if "```json" in response:
                json_start = response.find("```json") + 7
                json_end = response.find("```", json_start)
                response = response[json_start:json_end].strip()
            elif "```" in response:
                json_start = response.find("```") + 3
                json_end = response.find("```", json_start)
                if json_end > json_start:
                    response = response[json_start:json_end].strip()
            
            analysis = json.loads(response)
            
            # Add computed data
            analysis['overloaded_members'] = overloaded
            analysis['blocking_tasks_count'] = len(blocking_tasks)
            analysis['blocking_tasks'] = [{"id": t.get('id'), "title": t.get('title')} for t in blocking_tasks[:10]]
            
            return analysis
            
        except Exception as e:
            self.log_action("Error identifying bottlenecks", {"error": str(e)})
            return {
                "bottlenecks": [
                    {
                        "type": "resource_overload",
                        "description": f"{len(overloaded)} team members are overloaded",
                        "severity": "high" if len(overloaded) > 0 else "low",
                        "severity_score": 80 if len(overloaded) > 0 else 20,
                        "affected_resources": [m.get('member') for m in overloaded],
                        "resolution_strategy": ["Redistribute tasks", "Add resources", "Extend deadlines"],
                        "priority": "high" if len(overloaded) > 0 else "low"
                    }
                ],
                "summary": {
                    "total_bottlenecks": len(overloaded),
                    "critical_count": len([m for m in overloaded if m.get('severity') == 'critical']),
                    "high_count": len([m for m in overloaded if m.get('severity') == 'high']),
                },
                "overloaded_members": overloaded,
                "blocking_tasks_count": len(blocking_tasks)
            }
    
    def suggest_delegation(self, tasks: List[Dict], team_members: List[Dict], context: Optional[Dict] = None) -> Dict:
        """
        Suggest task delegation strategies with skill matching and workload balancing.
        
        Args:
            tasks (List[Dict]): List of tasks
            team_members (List[Dict]): List of team members
            context (Dict): Optional project context
            
        Returns:
            Dict: Comprehensive delegation suggestions with analysis
        """
        self.log_action("Suggesting delegation", {"tasks": len(tasks), "team": len(team_members)})
        
        # Calculate workload for each team member
        workload_by_user = {}
        for task in tasks:
            assignee_id = task.get('assignee_id')
            if assignee_id:
                if assignee_id not in workload_by_user:
                    workload_by_user[assignee_id] = {
                        'active_tasks': [],
                        'total_hours': 0,
                        'task_count': 0
                    }
                if task.get('status') in ['todo', 'in_progress', 'review']:
                    workload_by_user[assignee_id]['active_tasks'].append(task)
                    workload_by_user[assignee_id]['total_hours'] += task.get('estimated_hours', 0) or 0
                workload_by_user[assignee_id]['task_count'] += 1
        
        # Find unassigned tasks and overloaded tasks
        unassigned_tasks = [t for t in tasks if not t.get('assignee_id')]
        
        # Find tasks that might need reassignment (overloaded assignees)
        overloaded_assignees = {k: v for k, v in workload_by_user.items() 
                               if len(v['active_tasks']) > 8 or v['total_hours'] > 40}
        tasks_for_reassignment = [t for t in tasks 
                                 if t.get('assignee_id') in overloaded_assignees 
                                 and t.get('status') in ['todo', 'in_progress']]
        
        all_tasks_to_delegate = unassigned_tasks + tasks_for_reassignment[:5]  # Limit reassignments

        def _build_workload_analysis(members: List[Dict], workload_by_user: dict) -> Dict:
            """Build before_delegation workload analysis from current state."""
            overloaded = []
            underutilized = []
            total_hours = 0
            count = 0
            for m in members:
                uid = m.get('id')
                w = workload_by_user.get(uid, {'active_tasks': [], 'total_hours': 0})
                name = m.get('name') or m.get('username') or f'User #{uid}'
                if len(w['active_tasks']) > 8 or w['total_hours'] > 40:
                    overloaded.append(name)
                elif w['total_hours'] < 10:
                    underutilized.append(name)
                total_hours += w['total_hours']
                count += 1
            avg = round(total_hours / count, 1) if count else 0
            return {
                'before_delegation': {
                    'overloaded_members': overloaded,
                    'underutilized_members': underutilized,
                    'average_workload': avg,
                }
            }

        if not team_members:
            return {
                "suggestions": [],
                "workload_analysis": {},
                "summary": {
                    "message": "No team members found for this project. Add members to the project team (or assign tasks to users) to get delegation suggestions.",
                    "total_suggestions": 0,
                    "new_assignments": 0,
                    "reassignments": 0,
                },
                "reassignment_opportunities": []
            }

        if not all_tasks_to_delegate:
            workload_analysis = _build_workload_analysis(team_members, workload_by_user)
            return {
                "suggestions": [],
                "workload_analysis": workload_analysis,
                "summary": {
                    "message": "No delegation needed right now. All tasks are assigned and no one is overloaded (over 8 active tasks or 40 estimated hours).",
                    "total_suggestions": 0,
                    "new_assignments": 0,
                    "reassignments": 0,
                    "key_insights": [
                        f"{len(unassigned_tasks)} unassigned task(s)." if unassigned_tasks else "All tasks have an assignee.",
                        f"{len(overloaded_assignees)} overloaded member(s)." if overloaded_assignees else "No overloaded members.",
                    ],
                },
                "reassignment_opportunities": []
            }

        # Prepare team member data with workload
        team_data = []
        for member in team_members:
            member_id = member.get('id')
            workload = workload_by_user.get(member_id, {'active_tasks': [], 'total_hours': 0, 'task_count': 0})
            team_data.append({
                "id": member_id,
                "name": member.get('name', 'Unknown'),
                "username": member.get('username', ''),
                "role": member.get('role', ''),
                "current_active_tasks": len(workload['active_tasks']),
                "current_total_hours": round(workload['total_hours'], 1),
                "current_task_count": workload['task_count'],
                "capacity_available": max(0, 40 - workload['total_hours']),  # Assuming 40h/week capacity
                "is_overloaded": len(workload['active_tasks']) > 8 or workload['total_hours'] > 40
            })
        
        # Prepare task data
        tasks_data = []
        for task in all_tasks_to_delegate:
            current_assignee_id = task.get('assignee_id')
            current_assignee_workload = workload_by_user.get(current_assignee_id, {}) if current_assignee_id else {}
            
            tasks_data.append({
                "id": task.get('id', ''),
                "title": task.get('title', ''),
                "description": task.get('description', '')[:200] if task.get('description') else '',
                "priority": task.get('priority', 'medium'),
                "status": task.get('status', ''),
                "estimated_hours": task.get('estimated_hours'),
                "due_date": str(task.get('due_date', '')),
                "dependencies": task.get('dependencies', []),
                "current_assignee": task.get('assignee_name'),
                "current_assignee_overloaded": current_assignee_id in overloaded_assignees if current_assignee_id else False,
                "is_unassigned": not current_assignee_id
            })
        
        prompt = f"""You are an expert task delegation specialist. Analyze these tasks and team members to suggest optimal task assignments.

TEAM MEMBERS (with current workload):
{json.dumps(team_data, indent=2)}

TASKS TO DELEGATE:
{json.dumps(tasks_data, indent=2)}

DELEGATION ANALYSIS REQUIREMENTS:

1. SKILL MATCHING:
   - Analyze task requirements (title, description, estimated hours)
   - Match tasks to team members based on role, expertise, and past assignments
   - Consider task complexity and team member capabilities

2. WORKLOAD BALANCING:
   - Distribute tasks to balance workload across team
   - Avoid overloading already busy members
   - Utilize underutilized team members
   - Consider current active tasks and total hours

3. AVAILABILITY ANALYSIS:
   - Check if team member has capacity (hours available)
   - Consider current commitments and deadlines
   - Factor in task priority and urgency

4. REASSIGNMENT OPPORTUNITIES:
   - Identify tasks from overloaded members that can be reassigned
   - Suggest better distribution for workload balance
   - Consider impact of reassignment on project timeline

5. PRIORITY CONSIDERATION:
   - High priority tasks should go to most capable/available members
   - Urgent tasks need immediate assignment
   - Consider task dependencies when assigning

For EACH task, provide:
- task_id: Task ID
- task_title: Task title
- suggested_assignee: Team member name
- assignee_id: Team member ID
- current_assignee: Current assignee (if being reassigned)
- delegation_type: "new_assignment|reassignment|workload_balance"
- skill_match_score: Number (0-100) indicating how well skills match
- workload_impact: "low|medium|high" - impact on assignee's workload
- reasoning: "DETAILED explanation (6-8 sentences):
  * WHY this team member is the best fit (specific skills, expertise, experience)
  * WHAT makes them suitable for this task (role match, capability, availability)
  * HOW their current workload allows for this assignment (capacity analysis)
  * WHAT benefits this delegation brings (project efficiency, skill utilization, timeline)
  * HOW to ensure successful task completion (support needed, resources required)
  * WHAT risks or challenges might arise and how to mitigate them"
- priority: "high|medium|low" - assignment priority
- estimated_start_date: Suggested start date (if applicable)
- support_needed: Array of support/resources needed for successful completion

Return JSON:
{{
  "suggestions": [
    {{
      "task_id": "id",
      "task_title": "title",
      "suggested_assignee": "member_name",
      "assignee_id": "id",
      "current_assignee": "current_name or null",
      "delegation_type": "new_assignment",
      "skill_match_score": 85,
      "workload_impact": "medium",
      "reasoning": "Comprehensive explanation...",
      "priority": "high",
      "estimated_start_date": "2024-01-15",
      "support_needed": ["resource1", "resource2"]
    }}
  ],
  "workload_analysis": {{
    "before_delegation": {{
      "overloaded_members": ["member1"],
      "underutilized_members": ["member2"],
      "average_workload": 35.5
    }},
    "after_delegation": {{
      "overloaded_members": [],
      "underutilized_members": [],
      "average_workload": 32.0,
      "improvement": "Workload balanced across team"
    }}
  }},
  "reassignment_opportunities": [
    {{
      "task_id": "id",
      "from_assignee": "overloaded_member",
      "to_assignee": "available_member",
      "reasoning": "Why this reassignment helps"
    }}
  ],
  "summary": {{
    "total_suggestions": 5,
    "new_assignments": 3,
    "reassignments": 2,
    "workload_balance_improvement": "High",
    "key_insights": ["insight1", "insight2"],
    "recommendations": ["recommendation1", "recommendation2"]
  }}
}}"""
        
        try:
            response = self._call_llm(prompt, self.system_prompt, temperature=0.3, max_tokens=2500)
            
            # Extract JSON
            if "```json" in response:
                json_start = response.find("```json") + 7
                json_end = response.find("```", json_start)
                response = response[json_start:json_end].strip()
            elif "```" in response:
                json_start = response.find("```") + 3
                json_end = response.find("```", json_start)
                if json_end > json_start:
                    response = response[json_start:json_end].strip()
            
            suggestions = json.loads(response)
            
            # Add computed workload analysis if not in response
            if 'workload_analysis' not in suggestions:
                suggestions['workload_analysis'] = {
                    'before_delegation': {
                        'overloaded_members': [m.get('name') for m in team_data if m.get('is_overloaded')],
                        'underutilized_members': [m.get('name') for m in team_data if m.get('current_total_hours', 0) < 10]
                    }
                }
            
            return suggestions
            
        except Exception as e:
            self.log_action("Error suggesting delegation", {"error": str(e)})
            # Fallback: round-robin assignment
            suggestions = []
            for i, task in enumerate(all_tasks_to_delegate[:len(team_members)]):
                member = team_members[i % len(team_members)]
                suggestions.append({
                    "task_id": task.get('id'),
                    "task_title": task.get('title'),
                    "suggested_assignee": member.get('name', 'Unknown'),
                    "assignee_id": member.get('id'),
                    "delegation_type": "new_assignment",
                    "skill_match_score": 50,
                    "workload_impact": "medium",
                    "reasoning": "Round-robin assignment (AI analysis unavailable)",
                    "priority": task.get('priority', 'medium')
                })
            return {
                "suggestions": suggestions,
                "workload_analysis": {},
                "summary": {"message": "Fallback delegation used"}
            }
    
    def prioritize_and_order_tasks(self, tasks: List[Dict], team_members: List[Dict] = None, context: Optional[Dict] = None) -> Dict:
        """
        Combined method that prioritizes tasks and suggests optimal execution order.
        This provides a comprehensive analysis combining priority and sequencing.
        
        Args:
            tasks (List[Dict]): List of tasks
            team_members (List[Dict]): Optional team members for resource analysis
            context (Dict): Optional project context
            
        Returns:
            Dict: Combined prioritization and ordering results with comprehensive reasoning
        """
        self.log_action("Prioritizing and ordering tasks", {"task_count": len(tasks)})
        
        # Step 1: Prioritize tasks
        prioritized_result = self.prioritize_tasks(tasks, context=context)
        
        # Extract prioritized tasks
        if isinstance(prioritized_result, dict):
            prioritized_tasks = prioritized_result.get('tasks', tasks)
            prioritization_summary = prioritized_result.get('summary', {})
            prioritization_stats = prioritized_result.get('statistics', {})
            charts = prioritized_result.get('charts', {})
            critical_path_analysis = prioritized_result.get('critical_path_analysis')
            workload_analysis = prioritized_result.get('workload_analysis')
        else:
            prioritized_tasks = prioritized_result if isinstance(prioritized_result, list) else tasks
            prioritization_summary = {}
            prioritization_stats = {}
            charts = {}
            critical_path_analysis = None
            workload_analysis = None
        
        # Step 2: Suggest execution order based on prioritized tasks
        order_result = self.suggest_task_order(prioritized_tasks, team_members=team_members, context=context)
        
        # Extract ordering data
        if isinstance(order_result, dict):
            ordered_tasks = order_result.get('tasks', prioritized_tasks)
            parallel_groups = order_result.get('parallel_groups', [])
            milestones = order_result.get('milestones', [])
            order_summary = order_result.get('summary', {})
        else:
            ordered_tasks = order_result if isinstance(order_result, list) else prioritized_tasks
            parallel_groups = []
            milestones = []
            order_summary = {}
        
        # Calculate durations if not provided or if they're 0
        if not order_summary or order_summary.get('total_sequential_days', 0) == 0:
            # Calculate based on task estimated hours
            total_hours = sum(t.get('estimated_hours', 0) or 0 for t in ordered_tasks)
            # Assume 8 hours per day
            sequential_days = (total_hours / 8) if total_hours > 0 else len(ordered_tasks) * 2
            
            # Calculate optimized duration based on parallel groups
            if parallel_groups:
                # Find the longest path through parallel groups
                max_group_duration = 0
                for group in parallel_groups:
                    group_task_ids = [str(tid) for tid in group.get('tasks', [])]
                    group_tasks = [t for t in ordered_tasks if str(t.get('id')) in group_task_ids]
                    group_hours = sum(t.get('estimated_hours', 0) or 0 for t in group_tasks)
                    group_days = (group_hours / 8) if group_hours > 0 else len(group_tasks) * 2
                    max_group_duration = max(max_group_duration, group_days)
                
                # Sum up milestone durations if available
                if milestones:
                    optimized_days = sum(m.get('estimated_duration_days', 0) for m in milestones)
                    if optimized_days == 0:
                        optimized_days = max_group_duration * len(milestones) if milestones else max_group_duration
                else:
                    optimized_days = max_group_duration if max_group_duration > 0 else sequential_days * 0.7
            else:
                # No parallel groups, use sequential but with some optimization
                optimized_days = sequential_days * 0.8 if sequential_days > 0 else len(ordered_tasks) * 1.5
            
            # Update order_summary with calculated values
            if not order_summary:
                order_summary = {}
            order_summary['total_sequential_days'] = round(sequential_days, 1)
            order_summary['optimized_duration_days'] = round(optimized_days, 1)
            order_summary['parallel_execution_saves_days'] = round(max(0, sequential_days - optimized_days), 1)
        
        # Step 3: Generate comprehensive overall reasoning explaining why this approach is optimal
        overall_reasoning_prompt = f"""You are an expert project management analyst. Analyze this project execution strategy:

PROJECT SUMMARY:
- Total Tasks: {len(ordered_tasks)}
- High Priority Tasks: {prioritization_stats.get('high_priority', 0)}
- Medium Priority Tasks: {prioritization_stats.get('medium_priority', 0)}
- Low Priority Tasks: {prioritization_stats.get('low_priority', 0)}
- Tasks on Critical Path: {prioritization_stats.get('tasks_on_critical_path', 0)}

EXECUTION PLAN SUMMARY:
- Sequential Duration: {order_summary.get('total_sequential_days', 0)} days
- Optimized Duration: {order_summary.get('optimized_duration_days', 0)} days
- Time Saved: {order_summary.get('parallel_execution_saves_days', 0)} days
- Parallel Execution Groups: {len(parallel_groups)}
- Project Milestones: {len(milestones)}

TASK DETAILS (First 10 tasks):
{json.dumps([{
    "execution_sequence": t.get('execution_order', 999),
    "title": t.get('title', ''),
    "priority_level": t.get('ai_priority', t.get('priority', 'medium')),
    "importance_score": t.get('priority_score'),
    "business_value": t.get('business_value'),
    "risk_level": t.get('risk_level'),
    "parallel_group": t.get('parallel_group'),
    "milestone_phase": t.get('milestone_phase')
} for t in ordered_tasks[:10]], indent=2)}

IMPORTANT: Do NOT mention "prioritization", "ordering", "prioritization agent", "ordering agent", or similar technical terms. Instead, explain the strategy in natural, business-focused language.

Provide a comprehensive JSON response explaining why THIS EXECUTION STRATEGY is optimal:
{{
  "overall_reasoning": "DETAILED explanation (10-12 sentences): WHY this execution strategy is the BEST approach for this project. Explain in natural, business-focused language: 1) HOW focusing on high-value, urgent tasks first maximizes project success, 2) WHAT strategic benefits this approach provides (faster delivery, risk mitigation, resource optimization, value maximization), 3) HOW the task sequence minimizes bottlenecks and dependencies, 4) WHY this specific sequence of tasks is better than other possible sequences, 5) WHAT dependencies and constraints were considered in the strategy, 6) HOW parallel execution opportunities were identified and utilized, 7) WHAT the overall project strategy is and how this execution plan supports it, 8) HOW this approach balances urgency, importance, dependencies, and resource availability, 9) WHY this will lead to the most efficient and successful project completion, 10) WHAT makes this strategy superior to alternative approaches. Use natural business language - avoid technical terms like 'prioritization' or 'ordering'.",
  "strategic_benefits": [
    "Benefit 1 of focusing on high-value tasks first",
    "Benefit 2 of the optimized task sequence",
    "Benefit 3 of the strategic approach"
  ],
  "efficiency_benefits": [
    "Efficiency benefit 1 of this execution plan",
    "Efficiency benefit 2 of this execution plan",
    "Efficiency benefit 3 of this execution plan"
  ],
  "synergistic_benefits": [
    "Benefit 1 of the integrated approach",
    "Benefit 2 of the integrated approach",
    "Benefit 3 of the integrated approach"
  ],
  "key_strategic_insights": [
    "Strategic insight 1 about the execution strategy",
    "Strategic insight 2 about the execution strategy",
    "Strategic insight 3 about the execution strategy"
  ],
  "execution_recommendations": [
    "Specific recommendation 1 for executing this plan",
    "Specific recommendation 2 for executing this plan",
    "Specific recommendation 3 for executing this plan"
  ]
}}"""
        
        try:
            reasoning_response = self._call_llm(overall_reasoning_prompt, self.system_prompt, temperature=0.3, max_tokens=2000)
            if "```json" in reasoning_response:
                json_start = reasoning_response.find("```json") + 7
                json_end = reasoning_response.find("```", json_start)
                reasoning_response = reasoning_response[json_start:json_end].strip()
            elif "```" in reasoning_response:
                json_start = reasoning_response.find("```") + 3
                json_end = reasoning_response.find("```", json_start)
                if json_end > json_start:
                    reasoning_response = reasoning_response[json_start:json_end].strip()
            overall_reasoning = json.loads(reasoning_response)
        except Exception as e:
            self.log_action("Overall reasoning generation failed", {"error": str(e)})
            overall_reasoning = {
                "overall_reasoning": f"This execution strategy optimizes project delivery by focusing on high-value, urgent tasks first and sequencing them for maximum parallelization and efficiency. The approach balances urgency, importance, dependencies, and resource availability to achieve optimal project outcomes.",
                "strategic_benefits": [],
                "efficiency_benefits": [],
                "synergistic_benefits": [],
                "key_strategic_insights": [],
                "execution_recommendations": []
            }
        
        # Recalculate statistics from ordered tasks to ensure accuracy
        high_priority_count = len([t for t in ordered_tasks if t.get('ai_priority') == 'high'])
        medium_priority_count = len([t for t in ordered_tasks if t.get('ai_priority') == 'medium'])
        low_priority_count = len([t for t in ordered_tasks if t.get('ai_priority') == 'low'])
        
        # Ensure statistics are properly calculated
        final_statistics = {
            'total_tasks': len(ordered_tasks),
            'high_priority': high_priority_count,
            'medium_priority': medium_priority_count,
            'low_priority': low_priority_count,
            'tasks_with_dependencies': len([t for t in ordered_tasks if t.get('dependencies')]),
            'tasks_on_critical_path': len([t for t in ordered_tasks if t.get('is_critical_path')]),
        }
        
        # Use recalculated statistics if prioritization_stats is empty or incorrect
        if not prioritization_stats or prioritization_stats.get('total_tasks', 0) == 0:
            prioritization_stats = final_statistics
        else:
            # Merge to ensure all fields are present
            prioritization_stats.update(final_statistics)
        
        # Combine all results
        combined_result = {
            'tasks': ordered_tasks,
            'prioritization': {
                'summary': prioritization_summary,
                'statistics': prioritization_stats,
                'overall_reasoning': prioritization_summary.get('overall_reasoning', '')
            },
            'ordering': {
                'parallel_groups': parallel_groups,
                'milestones': milestones,
                'summary': order_summary
            },
            'combined_analysis': {
                'overall_reasoning': overall_reasoning.get('overall_reasoning', ''),
                'strategic_benefits': overall_reasoning.get('strategic_benefits', []),
                'efficiency_benefits': overall_reasoning.get('efficiency_benefits', []),
                'synergistic_benefits': overall_reasoning.get('synergistic_benefits', []),
                'key_strategic_insights': overall_reasoning.get('key_strategic_insights', []),
                'execution_recommendations': overall_reasoning.get('execution_recommendations', [])
            },
            'charts': charts,
            'critical_path_analysis': critical_path_analysis,
            'workload_analysis': workload_analysis
        }
        
        return combined_result
    
    def process(self, action: str, **kwargs) -> Dict:
        """
        Main processing method for task prioritization agent.
        
        Args:
            action (str): Action to perform (prioritize, order, prioritize_and_order, estimate, bottlenecks, delegation)
            **kwargs: Action-specific parameters
            
        Returns:
            dict: Processing results
        """
        self.log_action(f"Processing action: {action}", kwargs)
        
        try:
            if action == "prioritize":
                tasks = kwargs.get('tasks', [])
                context = kwargs.get('context', {})
                prioritized = self.prioritize_tasks(tasks, context=context)
                # prioritize_tasks now returns a dict with tasks, summary, statistics, etc.
                if isinstance(prioritized, dict):
                    return {"success": True, **prioritized}
                else:
                    return {"success": True, "tasks": prioritized}
            
            elif action == "order":
                tasks = kwargs.get('tasks', [])
                team_members = kwargs.get('team_members', [])
                context = kwargs.get('context', {})
                ordered = self.suggest_task_order(tasks, team_members=team_members, context=context)
                return {"success": True, **ordered}
            
            elif action == "prioritize_and_order":
                tasks = kwargs.get('tasks', [])
                team_members = kwargs.get('team_members', [])
                context = kwargs.get('context', {})
                combined = self.prioritize_and_order_tasks(tasks, team_members=team_members, context=context)
                return {"success": True, **combined}
            
            elif action == "estimate":
                task = kwargs.get('task', {})
                estimate = self.calculate_effort_estimate(task)
                return {"success": True, "estimate": estimate}
            
            elif action == "bottlenecks":
                tasks = kwargs.get('tasks', [])
                team_members = kwargs.get('team_members', [])
                context = kwargs.get('context', {})
                analysis = self.identify_bottlenecks(tasks, team_members, context=context)
                return {"success": True, **analysis}
            
            elif action == "delegation":
                tasks = kwargs.get('tasks', [])
                team_members = kwargs.get('team_members', [])
                context = kwargs.get('context', {})
                suggestions = self.suggest_delegation(tasks, team_members, context=context)
                return {"success": True, **suggestions}
            
            else:
                return {"success": False, "error": f"Unknown action: {action}"}
                
        except Exception as e:
            self.log_action(f"Error processing {action}", {"error": str(e)})
            return {"success": False, "error": str(e)}

