import React, { useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  Calendar, Activity, FileText, Users, Timer, Workflow, CalendarDays, Bell,
  ChevronLeft,
} from 'lucide-react';
import DailyStandupAgent from './DailyStandupAgent';
import ProjectHealthDashboard from './ProjectHealthDashboard';
import MeetingNotesAgent from './MeetingNotesAgent';
import TeamPerformanceDashboard from './TeamPerformanceDashboard';
import TimeEstimationView from './TimeEstimationView';
import WorkflowSuggestionsView from './WorkflowSuggestionsView';
import CalendarScheduleView from './CalendarScheduleView';
import SmartNotifications from './SmartNotifications';

const TOOLS = [
  {
    key: 'daily-standup',
    title: 'Daily Standup',
    desc: 'Auto-generate daily and weekly standup reports for your team',
    icon: Calendar,
    color: '#f472b6',
    bgColor: 'rgba(244,114,182,0.15)',
    borderHover: 'rgba(244,114,182,0.4)',
    component: DailyStandupAgent,
  },
  {
    key: 'project-health',
    title: 'Project Health',
    desc: 'Get health scores, status reports, and risk analysis for projects',
    icon: Activity,
    color: '#fb923c',
    bgColor: 'rgba(251,146,60,0.15)',
    borderHover: 'rgba(251,146,60,0.4)',
    component: ProjectHealthDashboard,
  },
  {
    key: 'meeting-notes',
    title: 'Meeting Notes',
    desc: 'Paste meeting notes to extract action items, decisions, and summaries',
    icon: FileText,
    color: '#a3e635',
    bgColor: 'rgba(163,230,53,0.15)',
    borderHover: 'rgba(163,230,53,0.4)',
    component: MeetingNotesAgent,
  },
  {
    key: 'team-performance',
    title: 'Team Performance',
    desc: 'Analyze team member productivity, workload, and performance metrics',
    icon: Users,
    color: '#22d3ee',
    bgColor: 'rgba(34,211,238,0.15)',
    borderHover: 'rgba(34,211,238,0.4)',
    component: TeamPerformanceDashboard,
  },
  {
    key: 'time-estimation',
    title: 'Time Estimation',
    desc: 'AI-powered task duration estimates with complexity analysis',
    icon: Timer,
    color: '#c084fc',
    bgColor: 'rgba(192,132,252,0.15)',
    borderHover: 'rgba(192,132,252,0.4)',
    component: TimeEstimationView,
  },
  {
    key: 'workflow',
    title: 'Workflow & SOP',
    desc: 'Get workflow suggestions, checklists, and best practices for each phase',
    icon: Workflow,
    color: '#2dd4bf',
    bgColor: 'rgba(45,212,191,0.15)',
    borderHover: 'rgba(45,212,191,0.4)',
    component: WorkflowSuggestionsView,
  },
  {
    key: 'calendar-schedule',
    title: 'Calendar & Schedule',
    desc: 'AI-optimized day-by-day schedule planner with conflict detection',
    icon: CalendarDays,
    color: '#fbbf24',
    bgColor: 'rgba(251,191,36,0.15)',
    borderHover: 'rgba(251,191,36,0.4)',
    component: CalendarScheduleView,
  },
  {
    key: 'notifications',
    title: 'Smart Notifications',
    desc: 'Scan projects for overdue tasks, blockers, and workload issues',
    icon: Bell,
    color: '#f87171',
    bgColor: 'rgba(248,113,113,0.15)',
    borderHover: 'rgba(248,113,113,0.4)',
    component: SmartNotifications,
  },
];

export default function PMToolsHub() {
  const [activeTool, setActiveTool] = useState(null);

  const selected = TOOLS.find((t) => t.key === activeTool);

  if (selected) {
    const ToolComponent = selected.component;
    const ToolIcon = selected.icon;
    return (
      <div className="space-y-4">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setActiveTool(null)}
          className="text-gray-400 hover:text-white -ml-2"
        >
          <ChevronLeft className="w-4 h-4 mr-1" /> Back to AI Tools
        </Button>
        <div className="flex items-center gap-2 mb-2">
          <div className="rounded-lg p-2" style={{ backgroundColor: selected.bgColor }}>
            <ToolIcon className="h-5 w-5" style={{ color: selected.color }} />
          </div>
          <h3 className="text-lg font-semibold text-white">{selected.title}</h3>
        </div>
        <ToolComponent />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="mb-2">
        <h3 className="text-lg font-semibold text-white">AI Tools</h3>
        <p className="text-sm text-white/40 mt-1">Select a tool to get started</p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {TOOLS.map((tool) => {
          const Icon = tool.icon;
          return (
            <button
              key={tool.key}
              onClick={() => setActiveTool(tool.key)}
              className="group relative flex flex-col items-start gap-3 rounded-xl border border-white/[0.08] bg-white/[0.03] backdrop-blur-sm p-5 text-left transition-all duration-300 hover:bg-white/[0.06] cursor-pointer w-full min-w-0"
              onMouseEnter={(e) => (e.currentTarget.style.borderColor = tool.borderHover)}
              onMouseLeave={(e) => (e.currentTarget.style.borderColor = '')}
            >
              <div className="rounded-lg p-2.5" style={{ backgroundColor: tool.bgColor }}>
                <Icon className="h-5 w-5" style={{ color: tool.color }} />
              </div>
              <div>
                <p className="font-semibold text-sm text-white group-hover:text-white transition-colors">
                  {tool.title}
                </p>
                <p className="text-xs text-white/40 mt-1 leading-relaxed">{tool.desc}</p>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
