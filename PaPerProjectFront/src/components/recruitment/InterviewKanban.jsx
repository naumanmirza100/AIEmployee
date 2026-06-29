import React, { useState } from 'react';
import {
  DndContext,
  DragOverlay,
  closestCenter,
  PointerSensor,
  TouchSensor,
  useSensor,
  useSensors,
  useDroppable,
  useDraggable,
} from '@dnd-kit/core';
import { format } from 'date-fns';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Clock, CalendarClock, CheckCircle2, XCircle, CalendarCheck,
  Mail, Briefcase, User, Star, MessageSquare, GripVertical,
  Building2, Trophy, ThumbsUp, HelpCircle, AlertCircle,
  MoreVertical, RefreshCw, Award, Lock,
} from 'lucide-react';

/* ─── Column definitions ─────────────────────────────────── */

const STATUS_COLUMNS = [
  { id: 'PENDING',     label: 'Pending',      icon: Clock,         color: 'yellow' },
  { id: 'SCHEDULED',   label: 'Scheduled',    icon: CalendarCheck, color: 'green'  },
  { id: 'COMPLETED',   label: 'Completed',    icon: CheckCircle2,  color: 'blue'   },
  { id: 'RESCHEDULED', label: 'Rescheduled',  icon: CalendarClock, color: 'purple' },
  { id: 'CANCELLED',   label: 'Cancelled',    icon: XCircle,       color: 'red'    },
];

const DECISION_COLUMNS = [
  { id: '',                 label: 'Not Decided',      icon: HelpCircle,  color: 'gray'    },
  { id: 'ONSITE_INTERVIEW', label: 'Onsite Interview', icon: Building2,   color: 'indigo'  },
  { id: 'PASSED',           label: 'Passed',           icon: ThumbsUp,    color: 'teal'    },
  { id: 'HIRED',            label: 'Hired',            icon: Trophy,      color: 'emerald' },
  { id: 'REJECTED',         label: 'Rejected',         icon: XCircle,     color: 'red'     },
];

const COLUMN_STYLES = {
  yellow:  { header: 'border-yellow-500/40 bg-yellow-500/10',  icon: 'text-yellow-400',  badge: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30'   },
  green:   { header: 'border-green-500/40 bg-green-500/10',    icon: 'text-green-400',   badge: 'bg-green-500/20 text-green-300 border-green-500/30'     },
  blue:    { header: 'border-blue-500/40 bg-blue-500/10',      icon: 'text-blue-400',    badge: 'bg-blue-500/20 text-blue-300 border-blue-500/30'       },
  purple:  { header: 'border-purple-500/40 bg-purple-500/10',  icon: 'text-purple-400',  badge: 'bg-purple-500/20 text-purple-300 border-purple-500/30'   },
  red:     { header: 'border-red-500/40 bg-red-500/10',        icon: 'text-red-400',     badge: 'bg-red-500/20 text-red-300 border-red-500/30'          },
  gray:    { header: 'border-white/20 bg-white/5',             icon: 'text-white/40',    badge: 'bg-white/10 text-white/50 border-white/20'             },
  indigo:  { header: 'border-indigo-500/40 bg-indigo-500/10',  icon: 'text-indigo-400',  badge: 'bg-indigo-500/20 text-indigo-300 border-indigo-500/30'   },
  teal:    { header: 'border-teal-500/40 bg-teal-500/10',      icon: 'text-teal-400',    badge: 'bg-teal-500/20 text-teal-300 border-teal-500/30'       },
  emerald: { header: 'border-emerald-500/40 bg-emerald-500/10',icon: 'text-emerald-400', badge: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30' },
};

/* ─── Mini badge helpers ─────────────────────────────────── */

function StatusBadge({ status }) {
  const map = {
    PENDING: 'bg-yellow-500/80', SCHEDULED: 'bg-green-500/80',
    COMPLETED: 'bg-blue-500/80', CANCELLED: 'bg-red-500/80', RESCHEDULED: 'bg-purple-500/80',
  };
  return (
    <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded text-white ${map[status] || 'bg-gray-500/80'}`}>
      {status}
    </span>
  );
}

function OutcomeBadge({ outcome }) {
  const map = {
    ONSITE_INTERVIEW: ['bg-indigo-500/80', 'Onsite'],
    HIRED:            ['bg-emerald-600/80', 'Hired'],
    PASSED:           ['bg-teal-500/80',    'Passed'],
    REJECTED:         ['bg-red-600/80',     'Rejected'],
  };
  const [cls, label] = map[outcome] || ['bg-gray-500/80', outcome];
  return (
    <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded text-white ${cls}`}>
      {label}
    </span>
  );
}

/* ─── Three-dot menu ─────────────────────────────────────── */

function CardMenu({ interview, onStatusChange, onOutcomeChange, onReschedule, onFeedback }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          className="p-1 rounded text-white/30 hover:text-white/70 hover:bg-white/10 transition-colors focus:outline-none"
          onClick={(e) => e.stopPropagation()}
        >
          <MoreVertical className="h-3.5 w-3.5" />
        </button>
      </DropdownMenuTrigger>

      <DropdownMenuContent
        className="w-52 bg-[#0d0d1a] border-white/15 text-white z-50"
        align="end"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Change Status submenu */}
        <DropdownMenuSub>
          <DropdownMenuSubTrigger className="gap-2 focus:bg-white/10 data-[state=open]:bg-white/10 cursor-pointer">
            <RefreshCw className="h-3.5 w-3.5 text-white/50" />
            <span className="text-sm">Change Status</span>
          </DropdownMenuSubTrigger>
          <DropdownMenuSubContent className="bg-[#0d0d1a] border-white/15 text-white w-44">
            {STATUS_COLUMNS.map((col) => {
              const Icon = col.icon;
              const active = interview.status === col.id;
              return (
                <DropdownMenuItem
                  key={col.id}
                  className={`gap-2 cursor-pointer focus:bg-white/10 ${active ? 'text-white' : 'text-white/60'}`}
                  onClick={() => !active && onStatusChange(interview, col.id)}
                >
                  <Icon className={`h-3.5 w-3.5 shrink-0 ${active ? 'text-violet-400' : 'text-white/40'}`} />
                  <span className="text-sm">{col.label}</span>
                  {active && <span className="ml-auto text-[10px] text-violet-400">current</span>}
                </DropdownMenuItem>
              );
            })}
          </DropdownMenuSubContent>
        </DropdownMenuSub>

        {/* Change Decision submenu */}
        <DropdownMenuSub>
          <DropdownMenuSubTrigger className="gap-2 focus:bg-white/10 data-[state=open]:bg-white/10 cursor-pointer">
            <Award className="h-3.5 w-3.5 text-white/50" />
            <span className="text-sm">Change Decision</span>
            {interview.status !== 'COMPLETED' && <Lock className="h-3 w-3 text-white/30 ml-auto" />}
          </DropdownMenuSubTrigger>
          <DropdownMenuSubContent className="bg-[#0d0d1a] border-white/15 text-white w-52">
            {interview.status !== 'COMPLETED' ? (
              <div className="px-3 py-2.5 space-y-1">
                <div className="flex items-center gap-1.5 text-amber-400/80">
                  <Lock className="h-3.5 w-3.5 shrink-0" />
                  <span className="text-xs font-medium">Decision Locked</span>
                </div>
                <p className="text-[11px] text-white/40 leading-snug">
                  Decision can only be set after interview status is <span className="text-white/60 font-medium">Completed</span>.
                </p>
              </div>
            ) : (
              DECISION_COLUMNS.map((col) => {
                const Icon = col.icon;
                const active = (interview.outcome || '') === col.id;
                return (
                  <DropdownMenuItem
                    key={col.id || 'none'}
                    className={`gap-2 cursor-pointer focus:bg-white/10 ${active ? 'text-white' : 'text-white/60'}`}
                    onClick={() => !active && onOutcomeChange(interview, col.id)}
                  >
                    <Icon className={`h-3.5 w-3.5 shrink-0 ${active ? 'text-violet-400' : 'text-white/40'}`} />
                    <span className="text-sm">{col.label}</span>
                    {active && <span className="ml-auto text-[10px] text-violet-400">current</span>}
                  </DropdownMenuItem>
                );
              })
            )}
          </DropdownMenuSubContent>
        </DropdownMenuSub>

        <DropdownMenuSeparator className="bg-white/10" />

        {/* Reschedule */}
        {(interview.status === 'PENDING' || interview.status === 'SCHEDULED') && (
          <DropdownMenuItem
            className="gap-2 cursor-pointer text-amber-300/80 focus:bg-white/10 focus:text-amber-300"
            onClick={() => onReschedule(interview)}
          >
            <CalendarClock className="h-3.5 w-3.5" />
            <span className="text-sm">Reschedule</span>
          </DropdownMenuItem>
        )}

        {/* Feedback */}
        {interview.status === 'COMPLETED' && (
          <DropdownMenuItem
            className="gap-2 cursor-pointer text-blue-300/80 focus:bg-white/10 focus:text-blue-300"
            onClick={() => onFeedback(interview)}
          >
            <MessageSquare className="h-3.5 w-3.5" />
            <span className="text-sm">
              {interview.feedback_submitted_at ? 'View Feedback' : 'Add Feedback'}
            </span>
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/* ─── Kanban Card ────────────────────────────────────────── */

function KanbanCard({ interview, isDragOverlay, onStatusChange, onOutcomeChange, onReschedule, onFeedback }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: String(interview.id),
    disabled: isDragOverlay,
  });

  const style = transform
    ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` }
    : undefined;

  return (
    <div ref={isDragOverlay ? undefined : setNodeRef} style={style}>
      <div
        className={`
          rounded-xl border bg-black/40 backdrop-blur-sm p-3 space-y-2 select-none
          transition-shadow duration-150
          ${isDragging    ? 'opacity-30 shadow-none border-white/5' : 'border-white/10 hover:border-white/25 hover:shadow-lg hover:shadow-black/40'}
          ${isDragOverlay ? 'shadow-2xl shadow-black/60 rotate-1 border-white/30 scale-105' : ''}
        `}
      >
        {/* Top row: drag handle + name + three-dot menu */}
        <div className="flex items-start gap-2">
          <div
            {...(isDragOverlay ? {} : { ...listeners, ...attributes })}
            className="mt-0.5 cursor-grab active:cursor-grabbing text-white/20 hover:text-white/50 shrink-0 transition-colors"
          >
            <GripVertical className="h-4 w-4" />
          </div>

          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              <User className="h-3 w-3 text-white/40 shrink-0" />
              <span className="text-sm font-semibold text-white truncate leading-tight">
                {interview.candidate_name}
              </span>
            </div>
            <div className="flex items-center gap-1.5 mt-0.5">
              <Briefcase className="h-3 w-3 text-white/30 shrink-0" />
              <span className="text-xs text-white/50 truncate">
                {interview.job_title || interview.job_role || '—'}
              </span>
            </div>
          </div>

          {/* Three-dot menu — hidden while in drag overlay */}
          {!isDragOverlay && (
            <div className="shrink-0 -mt-0.5">
              <CardMenu
                interview={interview}
                onStatusChange={onStatusChange}
                onOutcomeChange={onOutcomeChange}
                onReschedule={onReschedule}
                onFeedback={onFeedback}
              />
            </div>
          )}
        </div>

        {/* Email */}
        <div className="flex items-center gap-1.5 text-xs text-white/40 pl-6">
          <Mail className="h-3 w-3 shrink-0" />
          <span className="truncate">{interview.candidate_email}</span>
        </div>

        {/* Scheduled time */}
        {interview.scheduled_datetime && (
          <div className="flex items-center gap-1.5 text-xs text-white/50 bg-white/5 rounded-md px-2 py-1.5 pl-6">
            <Clock className="h-3 w-3 text-white/30 shrink-0" />
            <span>{format(new Date(interview.scheduled_datetime), 'MMM d, yyyy · h:mm a')}</span>
          </div>
        )}

        {/* Badges */}
        <div className="flex gap-1.5 flex-wrap pl-6">
          <StatusBadge status={interview.status} />
          {interview.outcome && <OutcomeBadge outcome={interview.outcome} />}
          {interview.interview_type && (
            <span className="text-[10px] px-1.5 py-0.5 rounded border border-white/10 text-white/40">
              {interview.interview_type}
            </span>
          )}
        </div>

        {/* Quick feedback stars — shown for completed with feedback */}
        {!isDragOverlay && interview.feedback_submitted_at && interview.feedback_rating > 0 && (
          <div className="flex items-center gap-0.5 pl-6">
            {[1,2,3,4,5].map(s => (
              <Star key={s} className={`h-2.5 w-2.5 ${s <= interview.feedback_rating ? 'text-amber-400 fill-amber-400' : 'text-white/15'}`} />
            ))}
            <span className="text-[10px] text-white/30 ml-1">
              {['','Poor','Below Average','Average','Good','Excellent'][interview.feedback_rating]}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

/* ─── Kanban Column ──────────────────────────────────────── */

function KanbanColumn({ column, interviews, onStatusChange, onOutcomeChange, onReschedule, onFeedback }) {
  const { isOver, setNodeRef } = useDroppable({ id: column.id });
  const style = COLUMN_STYLES[column.color] || COLUMN_STYLES.gray;
  const Icon = column.icon;

  return (
    <div className="flex flex-col min-w-[260px] w-[260px] xl:w-[280px] shrink-0">
      {/* Column header */}
      <div className={`flex items-center justify-between rounded-t-xl border px-3 py-2.5 ${style.header}`}>
        <div className="flex items-center gap-2">
          <Icon className={`h-4 w-4 ${style.icon}`} />
          <span className="text-sm font-semibold text-white">{column.label}</span>
        </div>
        <span className={`text-xs font-bold px-2 py-0.5 rounded-full border ${style.badge}`}>
          {interviews.length}
        </span>
      </div>

      {/* Drop zone */}
      <div
        ref={setNodeRef}
        className={`
          flex-1 min-h-[400px] rounded-b-xl border-x border-b p-2 space-y-2 overflow-y-auto
          transition-colors duration-150
          ${isOver
            ? 'bg-white/8 border-white/30 border-dashed'
            : 'bg-black/20 border-white/10'
          }
        `}
      >
        {interviews.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-24 text-white/20 text-xs gap-1.5">
            <AlertCircle className="h-5 w-5" />
            <span>Drop here</span>
          </div>
        ) : (
          interviews.map((iv) => (
            <KanbanCard
              key={iv.id}
              interview={iv}
              onStatusChange={onStatusChange}
              onOutcomeChange={onOutcomeChange}
              onReschedule={onReschedule}
              onFeedback={onFeedback}
            />
          ))
        )}
      </div>
    </div>
  );
}

/* ─── Main InterviewKanban ───────────────────────────────── */

export default function InterviewKanban({
  interviews,
  groupBy,          // 'status' | 'decision' — controlled by parent via URL param
  onGroupByChange,  // (v) => void
  onStatusChange,
  onOutcomeChange,
  onReschedule,
  onFeedback,
}) {
  const [activeId, setActiveId] = useState(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(TouchSensor,   { activationConstraint: { delay: 200, tolerance: 8 } }),
  );

  const columns = groupBy === 'status' ? STATUS_COLUMNS : DECISION_COLUMNS;

  const grouped = columns.reduce((acc, col) => {
    acc[col.id] = interviews.filter((iv) =>
      groupBy === 'status'
        ? iv.status === col.id
        : (iv.outcome || '') === col.id
    );
    return acc;
  }, {});

  const activeInterview = activeId
    ? interviews.find((iv) => String(iv.id) === activeId)
    : null;

  const handleDragStart = ({ active }) => setActiveId(String(active.id));

  const handleDragEnd = ({ active, over }) => {
    setActiveId(null);
    if (!over) return;

    const interview = interviews.find((iv) => String(iv.id) === String(active.id));
    if (!interview) return;

    const targetCol = over.id;

    if (groupBy === 'status') {
      if (interview.status !== targetCol) onStatusChange(interview, targetCol);
    } else {
      if ((interview.outcome || '') !== targetCol) onOutcomeChange(interview, targetCol);
    }
  };

  const handleDragCancel = () => setActiveId(null);

  return (
    <div className="space-y-4">
      {/* Toggle */}
      <div className="flex items-center gap-3">
        <span className="text-xs text-white/40 font-medium uppercase tracking-wider">View by</span>
        <div className="flex rounded-lg border border-white/15 overflow-hidden">
          <button
            onClick={() => onGroupByChange('status')}
            className={`px-4 py-1.5 text-xs font-medium transition-colors ${
              groupBy === 'status'
                ? 'bg-white/15 text-white'
                : 'text-white/40 hover:text-white/70 hover:bg-white/5'
            }`}
          >
            Status
          </button>
          <button
            onClick={() => onGroupByChange('decision')}
            className={`px-4 py-1.5 text-xs font-medium border-l border-white/15 transition-colors ${
              groupBy === 'decision'
                ? 'bg-white/15 text-white'
                : 'text-white/40 hover:text-white/70 hover:bg-white/5'
            }`}
          >
            Decision
          </button>
        </div>
        <span className="text-xs text-white/25 ml-1 hidden sm:inline">
          — drag to move · ⋯ to change status or decision
        </span>
      </div>

      {/* Board */}
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragStart={handleDragStart}
        onDragEnd={handleDragEnd}
        onDragCancel={handleDragCancel}
      >
        <div className="flex gap-3 overflow-x-auto pb-4 -mx-1 px-1">
          {columns.map((col) => (
            <KanbanColumn
              key={col.id}
              column={col}
              interviews={grouped[col.id] || []}
              onStatusChange={onStatusChange}
              onOutcomeChange={onOutcomeChange}
              onReschedule={onReschedule}
              onFeedback={onFeedback}
            />
          ))}
        </div>

        {/* Floating card while dragging */}
        <DragOverlay dropAnimation={{ duration: 150, easing: 'ease' }}>
          {activeInterview ? (
            <KanbanCard
              interview={activeInterview}
              isDragOverlay
              onStatusChange={() => {}}
              onOutcomeChange={() => {}}
              onReschedule={() => {}}
              onFeedback={() => {}}
            />
          ) : null}
        </DragOverlay>
      </DndContext>
    </div>
  );
}
