"""
Task & Prioritization Agent
Manages tasks, assigns priorities, and optimizes task execution.
"""

from .base_agent import BaseAgent
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
    
    def prioritize_tasks(self, tasks: List[Dict]) -> List[Dict]:
        """
        Auto-prioritize tasks based on deadlines, dependencies, and importance.
        
        Args:
            tasks (List[Dict]): List of tasks to prioritize
            
        Returns:
            List[Dict]: Tasks with assigned priorities
        """
        self.log_action("Prioritizing tasks", {"task_count": len(tasks)})
        
        # Prepare task data for AI analysis
        tasks_summary = []
        for task in tasks:
            task_info = {
                "id": task.get('id', ''),
                "title": task.get('title', ''),
                "description": task.get('description', ''),
                "due_date": str(task.get('due_date', '')),
                "status": task.get('status', ''),
                "current_priority": task.get('priority', 'medium'),
                "dependencies": task.get('dependencies', []),
            }
            tasks_summary.append(task_info)
        
        prompt = f"""Analyze the following tasks and assign priority levels (high, medium, low) based on:
1. Due dates (urgent deadlines = high priority)
2. Task dependencies (blocking tasks = high priority)
3. Current status (in-progress tasks may need higher priority)
4. Task importance
5. Business impact and project goals

Tasks to prioritize:
{json.dumps(tasks_summary, indent=2)}

For each task, provide:
- recommended_priority: "high", "medium", or "low"
- reasoning: DETAILED implementation reasoning (4-6 sentences) explaining:
  * WHY this priority level is appropriate for this specific task
  * WHAT factors influenced this decision (deadlines, dependencies, importance, status, business impact)
  * HOW this priority affects the overall project timeline and delivery
  * WHAT should be done first and why (execution strategy)
  * HOW to approach this task given its priority level
  * WHAT risks or dependencies need to be considered
- suggested_order: Number indicating execution order (1 = first)

Return a JSON array with this structure for each task:
[
  {{
    "id": "task_id",
    "recommended_priority": "high|medium|low",
    "reasoning": "Detailed explanation of why this priority is recommended, what factors influenced the decision, how it affects the project, and what should be done first.",
    "suggested_order": 1
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
            
            # Update tasks with priorities and reasoning
            priority_map = {item['id']: item for item in priorities}
            for task in tasks:
                task_id = str(task.get('id', ''))
                if task_id in priority_map:
                    task['ai_priority'] = priority_map[task_id]['recommended_priority']
                    # Store reasoning with context prefix
                    reasoning_prefix = "[Priority Analysis] "
                    task['ai_reasoning'] = reasoning_prefix + priority_map[task_id]['reasoning']
                    task['suggested_order'] = priority_map[task_id]['suggested_order']
            
            return tasks
            
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
    
    def suggest_task_order(self, tasks: List[Dict]) -> List[Dict]:
        """
        Suggest optimal task ordering for execution.
        
        Args:
            tasks (List[Dict]): List of tasks
            
        Returns:
            List[Dict]: Tasks in suggested execution order
        """
        self.log_action("Suggesting task order", {"task_count": len(tasks)})
        
        tasks_data = []
        for task in tasks:
            tasks_data.append({
                "id": task.get('id', ''),
                "title": task.get('title', ''),
                "dependencies": task.get('dependencies', []),
                "due_date": str(task.get('due_date', '')),
                "priority": task.get('priority', 'medium'),
                "status": task.get('status', ''),
            })
        
        prompt = f"""Analyze these tasks and suggest the optimal execution order considering:
1. Task dependencies (tasks that block others should come first)
2. Due dates (urgent tasks first)
3. Priority levels
4. Current status (in-progress tasks should continue)

Tasks:
{json.dumps(tasks_data, indent=2)}

Provide a JSON array with tasks ordered by suggested execution sequence:
[
  {{
    "id": "task_id",
    "execution_order": 1,
    "reasoning": "DETAILED explanation (4-6 sentences): WHY this task should be done at this position in the sequence, WHAT dependencies or prerequisites make this order optimal, HOW this sequencing affects project flow, WHAT happens if this order is changed, and HOW to execute this task in this position."
  }}
]"""
        
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
            
            order_suggestions = json.loads(response)
            order_map = {item['id']: item for item in order_suggestions}
            
            # Add reasoning to tasks
            for task in tasks:
                task_id = str(task.get('id', ''))
                if task_id in order_map:
                    task['execution_order'] = order_map[task_id]['execution_order']
                    # Store reasoning with context prefix
                    reasoning_prefix = "[Execution Order Analysis] "
                    task['order_reasoning'] = reasoning_prefix + order_map[task_id].get('reasoning', '')
                    # Also update ai_reasoning field for consistency
                    task['ai_reasoning'] = task.get('ai_reasoning', '') + "\n\n" + task['order_reasoning'] if task.get('ai_reasoning') else task['order_reasoning']
            
            # Sort tasks by suggested order
            sorted_tasks = sorted(tasks, key=lambda t: order_map.get(str(t.get('id', '')), {}).get('execution_order', 999))
            return sorted_tasks
            
        except Exception as e:
            self.log_action("Error suggesting task order", {"error": str(e)})
            # Fallback: sort by priority and due date
            return sorted(tasks, key=lambda t: (
                {'high': 0, 'medium': 1, 'low': 2}.get(t.get('priority', 'medium'), 1),
                t.get('due_date', datetime.max)
            ))
    
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
    
    def identify_bottlenecks(self, tasks: List[Dict], team_members: List[Dict]) -> Dict:
        """
        Identify bottlenecks and overloaded resources.
        
        Args:
            tasks (List[Dict]): List of tasks
            team_members (List[Dict]): List of team members
            
        Returns:
            Dict: Bottleneck analysis
        """
        self.log_action("Identifying bottlenecks", {"tasks": len(tasks), "team": len(team_members)})
        
        # Count tasks per team member
        task_counts = {}
        for task in tasks:
            assignee_id = task.get('assignee_id')
            if assignee_id:
                task_counts[assignee_id] = task_counts.get(assignee_id, 0) + 1
        
        # Find overloaded members
        overloaded = []
        for member in team_members:
            member_id = member.get('id')
            task_count = task_counts.get(member_id, 0)
            if task_count > 5:  # Threshold for overload
                overloaded.append({
                    "member": member.get('name', 'Unknown'),
                    "task_count": task_count,
                    "status": "overloaded"
                })
        
        # Find blocking tasks
        blocking_tasks = [t for t in tasks if t.get('status') == 'blocked']
        
        # Use AI for deeper analysis
        analysis_data = {
            "tasks": tasks[:10],  # Limit for token efficiency
            "team_members": team_members,
            "overloaded_members": overloaded,
            "blocking_tasks": len(blocking_tasks)
        }
        
        prompt = f"""Analyze this project data and identify bottlenecks with detailed reasoning:

Tasks: {len(tasks)} total
Team Members: {len(team_members)}
Overloaded Members: {len(overloaded)}
Blocking Tasks: {len(blocking_tasks)}

For each bottleneck identified, provide DETAILED reasoning explaining:
- WHY this is a bottleneck (root cause analysis)
- WHAT tasks or resources are affected
- HOW this bottleneck impacts project timeline and delivery
- WHAT specific actions should be taken to resolve it
- WHAT preventive measures can be implemented

For each affected task, provide task-specific reasoning explaining:
- WHY this task is part of the bottleneck
- HOW this bottleneck affects this specific task's execution
- WHAT should be done to unblock this task
- HOW to prevent this task from becoming a bottleneck again

Provide analysis in JSON format:
{{
  "bottlenecks": [
    {{
      "type": "resource_overload|task_blocking|dependency_chain",
      "description": "what the bottleneck is",
      "severity": "high|medium|low",
      "affected_tasks": [
        {{
          "task_id": "task_id1",
          "task_reasoning": "DETAILED explanation (4-6 sentences): Why this task is part of the bottleneck, how the bottleneck affects this task's execution, what should be done to unblock this task, and how to prevent it from becoming a bottleneck again."
        }}
      ],
      "reasoning": "Detailed explanation (3-5 sentences): Why this is a bottleneck, what's affected, how it impacts the project, what actions to take, and preventive measures.",
      "recommendation": "Specific actionable steps to resolve the bottleneck"
    }}
  ],
  "summary": "overall bottleneck summary with key insights"
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
            
            analysis = json.loads(response)
            analysis['overloaded_members'] = overloaded
            analysis['blocking_tasks_count'] = len(blocking_tasks)
            return analysis
            
        except Exception as e:
            self.log_action("Error identifying bottlenecks", {"error": str(e)})
            return {
                "bottlenecks": [
                    {
                        "type": "resource_overload",
                        "description": f"{len(overloaded)} team members are overloaded",
                        "severity": "high" if len(overloaded) > 0 else "low",
                        "recommendation": "Redistribute tasks or add resources"
                    }
                ],
                "summary": f"Found {len(overloaded)} overloaded members and {len(blocking_tasks)} blocking tasks",
                "overloaded_members": overloaded,
                "blocking_tasks_count": len(blocking_tasks)
            }
    
    def suggest_delegation(self, tasks: List[Dict], team_members: List[Dict]) -> Dict:
        """
        Suggest task delegation strategies.
        
        Args:
            tasks (List[Dict]): List of tasks
            team_members (List[Dict]): List of team members
            
        Returns:
            Dict: Delegation suggestions
        """
        self.log_action("Suggesting delegation", {"tasks": len(tasks), "team": len(team_members)})
        
        unassigned_tasks = [t for t in tasks if not t.get('assignee_id')]
        
        if not unassigned_tasks or not team_members:
            return {"suggestions": [], "message": "No delegation needed"}
        
        prompt = f"""Suggest task delegation for these unassigned tasks:

Unassigned Tasks:
{json.dumps(unassigned_tasks[:10], indent=2)}

Available Team Members:
{json.dumps(team_members, indent=2)}

For each task, suggest:
- Which team member should handle it
- Why (based on skills, workload, availability, expertise match)
- Priority level
- Detailed reasoning explaining the delegation strategy

Return JSON:
{{
  "suggestions": [
    {{
      "task_id": "id",
      "task_title": "title",
      "suggested_assignee": "member_name",
      "assignee_id": "id",
      "reasoning": "DETAILED explanation (4-6 sentences): WHY this team member is the best fit for this task, WHAT skills or expertise make them suitable, HOW their current workload allows for this assignment, WHAT benefits this delegation brings to the project, and HOW to ensure successful task completion.",
      "priority": "high|medium|low"
    }}
  ]
}}"""
        
        try:
            response = self._call_llm(prompt, self.system_prompt, temperature=0.4)
            
            # Extract JSON
            if "```json" in response:
                json_start = response.find("```json") + 7
                json_end = response.find("```", json_start)
                response = response[json_start:json_end].strip()
            elif "```" in response:
                json_start = response.find("```") + 3
                json_end = response.find("```", json_start)
                response = response[json_start:json_end].strip()
            
            suggestions = json.loads(response)
            return suggestions
            
        except Exception as e:
            self.log_action("Error suggesting delegation", {"error": str(e)})
            # Fallback: round-robin assignment
            suggestions = []
            for i, task in enumerate(unassigned_tasks[:len(team_members)]):
                member = team_members[i % len(team_members)]
                suggestions.append({
                    "task_id": task.get('id'),
                    "task_title": task.get('title'),
                    "suggested_assignee": member.get('name', 'Unknown'),
                    "assignee_id": member.get('id'),
                    "reasoning": "Round-robin assignment",
                    "priority": task.get('priority', 'medium')
                })
            return {"suggestions": suggestions}
    
    def process(self, action: str, **kwargs) -> Dict:
        """
        Main processing method for task prioritization agent.
        
        Args:
            action (str): Action to perform (prioritize, order, estimate, bottlenecks, delegation)
            **kwargs: Action-specific parameters
            
        Returns:
            dict: Processing results
        """
        self.log_action(f"Processing action: {action}", kwargs)
        
        try:
            if action == "prioritize":
                tasks = kwargs.get('tasks', [])
                prioritized = self.prioritize_tasks(tasks)
                return {"success": True, "tasks": prioritized}
            
            elif action == "order":
                tasks = kwargs.get('tasks', [])
                ordered = self.suggest_task_order(tasks)
                return {"success": True, "tasks": ordered}
            
            elif action == "estimate":
                task = kwargs.get('task', {})
                estimate = self.calculate_effort_estimate(task)
                return {"success": True, "estimate": estimate}
            
            elif action == "bottlenecks":
                tasks = kwargs.get('tasks', [])
                team_members = kwargs.get('team_members', [])
                analysis = self.identify_bottlenecks(tasks, team_members)
                return {"success": True, "analysis": analysis}
            
            elif action == "delegation":
                tasks = kwargs.get('tasks', [])
                team_members = kwargs.get('team_members', [])
                suggestions = self.suggest_delegation(tasks, team_members)
                return {"success": True, "suggestions": suggestions}
            
            else:
                return {"success": False, "error": f"Unknown action: {action}"}
                
        except Exception as e:
            self.log_action(f"Error processing {action}", {"error": str(e)})
            return {"success": False, "error": str(e)}

