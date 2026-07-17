// Calendar / AI Weekly Planner panel — extracted from ExecMeetingDashboard.jsx.
// Stateless: receives all state + handlers via props.

import React from 'react';
import { Button } from '@/components/ui/button';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
  Loader2, CalendarDays, CalendarClock, Clock, CheckCircle2, Download, RefreshCw, ChevronRight,
} from 'lucide-react';
import { CARD_STYLE } from '../shared';
import execMeetingService from '@/services/execMeetingService';

const WORKLOAD_COLORS = {
  light:    'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
  moderate: 'bg-amber-500/20 text-amber-300 border-amber-500/30',
  heavy:    'bg-red-500/20 text-red-400 border-red-500/30',
};

export const CalendarPanel = ({
  weekPlan, weekPlanLoading, includePastTasks,
  setWeekPlanLoading, setWeekPlan, setIncludePastTasks, setShowPastTasksConfirm,
  workStartHour, setWorkStartHour, workEndHour, setWorkEndHour, toast,
}) => (
    <div className="space-y-5">
      {/* Generate button + settings */}
      <div className="rounded-2xl p-5 space-y-4" style={CARD_STYLE}>
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-white font-semibold flex items-center gap-2">
              <CalendarDays className="h-4 w-4 text-violet-400" /> AI Weekly Planner
            </h3>
            <p className="text-white/50 text-xs mt-1">
              AI analyses your meetings and tasks and builds an optimized schedule for the week.
            </p>
          </div>
          <div className="flex items-center gap-2">
            {weekPlan && (
              <Button size="sm" variant="ghost" onClick={async () => {
                setWeekPlanLoading(true);
                try {
                  const today = new Date();
                  const weekStart = `${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}-${String(today.getDate()).padStart(2,'0')}`;
                  const res = await execMeetingService.planWeek({ include_past_tasks: includePastTasks, week_start: weekStart, work_start_hour: workStartHour, work_end_hour: workEndHour });
                  setWeekPlan(res.plan || res);
                  toast({ title: 'Plan refreshed!' });
                } catch (err) {
                  toast({ title: 'Refresh failed', description: err.message, variant: 'destructive' });
                } finally { setWeekPlanLoading(false); }
              }} disabled={weekPlanLoading} className="text-white/40 hover:text-white">
                <RefreshCw className={`h-3.5 w-3.5 ${weekPlanLoading ? 'animate-spin' : ''}`} />
              </Button>
            )}
            <Button onClick={async () => {
              setWeekPlanLoading(true);
              try {
                const today = new Date();
                const weekStart = `${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}-${String(today.getDate()).padStart(2,'0')}`;
                const res = await execMeetingService.planWeek({ include_past_tasks: includePastTasks, week_start: weekStart, work_start_hour: workStartHour, work_end_hour: workEndHour });
                console.log('[WeekPlan] response:', res);
                const plan = res.plan || res;
                setWeekPlan(plan);
                if (!plan || (!plan.daily_plans?.length && !plan.weekly_summary)) {
                  toast({ title: 'Plan generated but empty', description: 'No meetings or tasks found for this week. Add some first!', variant: 'destructive' });
                } else {
                  toast({ title: 'Week plan ready!' });
                }
              } catch (err) {
                console.error('[WeekPlan] error:', err);
                toast({ title: 'Planning failed', description: err?.data?.message || err.message || 'Unknown error', variant: 'destructive' });
              } finally {
                setWeekPlanLoading(false);
              }
            }} disabled={weekPlanLoading} style={{ background: 'linear-gradient(90deg, #a259ff 0%, #7c3aed 100%)' }} className="text-white border-0 hover:opacity-90">
              {weekPlanLoading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <CalendarDays className="h-4 w-4 mr-2" />}
              {weekPlanLoading ? 'Planning…' : 'Plan This Week'}
            </Button>
          </div>
        </div>

        {/* Work-hours row — the window tasks get scheduled within */}
        <div className="flex items-center justify-between rounded-xl px-4 py-3 bg-white/5 border border-white/10">
          <div>
            <p className="text-white/80 text-sm font-medium">Working hours</p>
            <p className="text-white/40 text-xs mt-0.5">Tasks are scheduled into hourly slots within this window (12 PM lunch skipped).</p>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <Select value={String(workStartHour)} onValueChange={v => setWorkStartHour(Number(v))}>
              <SelectTrigger className="h-8 w-[84px] bg-violet-500/10 border-violet-400/30 text-violet-100 text-xs hover:bg-violet-500/20 focus:ring-violet-500">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-[#1a1030] border-violet-400/30 text-violet-100 max-h-56 [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]">
                {Array.from({ length: 24 }, (_, h) => (
                  <SelectItem key={h} value={String(h)} disabled={h >= workEndHour}
                    className="text-xs text-violet-100 focus:bg-violet-500/30 focus:text-white">
                    {String(h).padStart(2, '0')}:00
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <span className="text-white/30 text-xs">to</span>
            <Select value={String(workEndHour)} onValueChange={v => setWorkEndHour(Number(v))}>
              <SelectTrigger className="h-8 w-[84px] bg-violet-500/10 border-violet-400/30 text-violet-100 text-xs hover:bg-violet-500/20 focus:ring-violet-500">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-[#1a1030] border-violet-400/30 text-violet-100 max-h-56 [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]">
                {Array.from({ length: 25 }, (_, h) => (
                  <SelectItem key={h} value={String(h)} disabled={h <= workStartHour}
                    className="text-xs text-violet-100 focus:bg-violet-500/30 focus:text-white">
                    {String(h).padStart(2, '0')}:00
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        {/* Settings row */}
        <div className="flex items-center justify-between rounded-xl px-4 py-3 bg-white/5 border border-white/10">
          <div>
            <p className="text-white/80 text-sm font-medium">Include overdue / older tasks</p>
            <p className="text-white/40 text-xs mt-0.5">
              {includePastTasks
                ? 'All todo & in-progress tasks included regardless of due date'
                : 'Only tasks due this week or later are included'}
            </p>
          </div>
          <button
            type="button"
            onClick={() => {
              if (!includePastTasks) {
                setShowPastTasksConfirm(true);
              } else {
                setIncludePastTasks(false);
              }
            }}
            className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none ${
              includePastTasks ? 'bg-violet-600' : 'bg-white/20'
            }`}
          >
            <span className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform duration-200 ${
              includePastTasks ? 'translate-x-5' : 'translate-x-0'
            }`} />
          </button>
        </div>
      </div>

      {/* Plan results */}
      {weekPlan && !weekPlan.daily_plans?.length && !weekPlan.weekly_summary && (
        <div className="rounded-2xl p-8 text-center" style={CARD_STYLE}>
          <CalendarDays className="h-10 w-10 text-white/20 mx-auto mb-3" />
          <p className="text-white/50 text-sm">No meetings or tasks found for this week.</p>
          <p className="text-white/30 text-xs mt-1">Schedule some meetings or add tasks first, then try again.</p>
        </div>
      )}
      {weekPlan && (weekPlan.daily_plans?.length > 0 || weekPlan.weekly_summary) && (
        <div className="space-y-4">
          {/* Download button */}
          <div className="flex justify-end">
            <Button
              size="sm"
              variant="outline"
              className="border-violet-500/40 text-violet-300 hover:bg-violet-500/10 gap-2"
              onClick={async () => {
                try {
                  const { default: jsPDF } = await import('jspdf');
                  const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });
                  const pageW = pdf.internal.pageSize.getWidth();
                  const pageH = pdf.internal.pageSize.getHeight();
                  const margin = 18;
                  const contentW = pageW - margin * 2;
                  const weekLabel = weekPlan.week_start || '';

                  const checkPage = (y, needed = 8) => {
                    if (y > pageH - needed) { pdf.addPage(); return 18; }
                    return y;
                  };

                  // jsPDF's core fonts only cover Latin-1 — Unicode punctuation
                  // (arrows, em-dashes, smart quotes) renders as garbage with
                  // broken letter-spacing. Map them to plain ASCII before drawing.
                  const pdfSafe = (t) => String(t ?? '')
                    .replace(/\s*→\s*/g, ' > ')
                    .replace(/[–—]/g, '-')
                    .replace(/[‘’]/g, "'")
                    .replace(/[“”]/g, '"')
                    .replace(/…/g, '...')
                    .replace(/[•·]/g, '-');

                  // Purple header bar
                  pdf.setFillColor(109, 40, 217);
                  pdf.rect(0, 0, pageW, 12, 'F');

                  // Title
                  pdf.setFont('helvetica', 'bold');
                  pdf.setFontSize(18);
                  pdf.setTextColor(30, 10, 60);
                  const titleText = pdfSafe(`AI Weekly Plan${weekLabel ? ' — ' + weekLabel : ''}`);
                  const titleLines = pdf.splitTextToSize(titleText, contentW);
                  pdf.text(titleLines, margin, 24);
                  let y = 24 + titleLines.length * 7;

                  // Meta line
                  pdf.setFont('helvetica', 'normal');
                  pdf.setFontSize(8.5);
                  pdf.setTextColor(120, 100, 160);
                  pdf.text('Generated by AI Executive Meeting Assistant', margin, y);
                  y += 5;

                  // Divider
                  pdf.setDrawColor(109, 40, 217);
                  pdf.setLineWidth(0.4);
                  pdf.line(margin, y, pageW - margin, y);
                  y += 6;

                  // Summary
                  if (weekPlan.weekly_summary) {
                    y = checkPage(y, 14);
                    pdf.setFont('helvetica', 'bold');
                    pdf.setFontSize(10);
                    pdf.setTextColor(76, 29, 149);
                    pdf.text('SUMMARY', margin, y);
                    y += 5;
                    pdf.setFont('helvetica', 'normal');
                    pdf.setFontSize(10);
                    pdf.setTextColor(40, 30, 60);
                    const sumLines = pdf.splitTextToSize(pdfSafe(weekPlan.weekly_summary), contentW);
                    sumLines.forEach(l => { y = checkPage(y); pdf.text(l, margin, y); y += 5.5; });
                    y += 3;
                  }

                  // Conflicts
                  if (weekPlan.conflicts_detected?.length) {
                    y = checkPage(y, 14);
                    pdf.setFont('helvetica', 'bold');
                    pdf.setFontSize(10);
                    pdf.setTextColor(185, 28, 28);
                    pdf.text('CONFLICTS DETECTED', margin, y);
                    y += 5;
                    pdf.setFont('helvetica', 'normal');
                    pdf.setFontSize(10);
                    pdf.setTextColor(40, 30, 60);
                    weekPlan.conflicts_detected.forEach(c => {
                      y = checkPage(y);
                      const wrapped = pdf.splitTextToSize(`- ${pdfSafe(c)}`, contentW - 4);
                      pdf.text(wrapped, margin + 3, y); y += wrapped.length * 5.5 + 1;
                    });
                    y += 3;
                  }

                  // Recommendations
                  if (weekPlan.recommendations?.length) {
                    y = checkPage(y, 14);
                    pdf.setFont('helvetica', 'bold');
                    pdf.setFontSize(10);
                    pdf.setTextColor(76, 29, 149);
                    pdf.text('RECOMMENDATIONS', margin, y);
                    y += 5;
                    pdf.setFont('helvetica', 'normal');
                    pdf.setFontSize(10);
                    pdf.setTextColor(40, 30, 60);
                    weekPlan.recommendations.forEach(r => {
                      y = checkPage(y);
                      const wrapped = pdf.splitTextToSize(`> ${pdfSafe(r)}`, contentW - 4);
                      pdf.text(wrapped, margin + 3, y); y += wrapped.length * 5.5 + 1;
                    });
                    y += 4;
                  }

                  // Day cards
                  (weekPlan.daily_plans || []).forEach(day => {
                    const hasMeetings = day.scheduled_meetings?.length > 0;
                    const hasTasks = day.suggested_task_slots?.length > 0;
                    const hasFocus = day.focus_blocks?.length > 0;
                    if (!hasMeetings && !hasTasks && !hasFocus) return;

                    y = checkPage(y, 20);

                    // Day header bar (light purple)
                    pdf.setFillColor(237, 233, 254);
                    pdf.rect(margin, y - 4, contentW, 9, 'F');
                    pdf.setFont('helvetica', 'bold');
                    pdf.setFontSize(11);
                    pdf.setTextColor(45, 27, 105);
                    pdf.text(`${day.day_name}  ${day.date}`, margin + 2, y + 2);
                    if (day.workload_level) {
                      const wlText = day.workload_level.toUpperCase();
                      pdf.setFontSize(8);
                      pdf.setTextColor(109, 40, 217);
                      pdf.text(wlText, pageW - margin - pdf.getTextWidth(wlText), y + 2);
                    }
                    y += 8;

                    if (hasMeetings) {
                      y = checkPage(y, 8);
                      pdf.setFont('helvetica', 'bold'); pdf.setFontSize(8.5); pdf.setTextColor(109, 40, 217);
                      pdf.text('MEETINGS', margin + 2, y); y += 4.5;
                      pdf.setFont('helvetica', 'normal'); pdf.setFontSize(10); pdf.setTextColor(40, 30, 60);
                      day.scheduled_meetings.forEach(m => {
                        y = checkPage(y);
                        const title = pdfSafe(typeof m === 'string' ? m : m.title);
                        const timePart = m.time ? `  ${m.time}` : '';
                        const durPart = m.duration_minutes ? `  (${m.duration_minutes}min)` : '';
                        const wrapped = pdf.splitTextToSize(`- ${title}${timePart}${durPart}`, contentW - 6);
                        pdf.text(wrapped, margin + 4, y); y += wrapped.length * 5.5 + 1;
                      });
                      y += 2;
                    }

                    if (hasTasks) {
                      y = checkPage(y, 8);
                      pdf.setFont('helvetica', 'bold'); pdf.setFontSize(8.5); pdf.setTextColor(109, 40, 217);
                      pdf.text('TASK SLOTS', margin + 2, y); y += 4.5;
                      pdf.setFont('helvetica', 'normal'); pdf.setFontSize(10); pdf.setTextColor(40, 30, 60);
                      day.suggested_task_slots.forEach(s => {
                        y = checkPage(y);
                        const taskLabel = pdfSafe(s.task);
                        const durPart = s.duration_minutes ? `  (${s.duration_minutes}min)` : '';
                        const wrapped = pdf.splitTextToSize(`${s.time}  ${taskLabel}${durPart}`, contentW - 6);
                        pdf.setTextColor(109, 40, 217);
                        pdf.text(s.time, margin + 4, y);
                        pdf.setTextColor(40, 30, 60);
                        const taskW = pdf.splitTextToSize(`${taskLabel}${durPart}`, contentW - 6 - 14);
                        pdf.text(taskW, margin + 18, y); y += Math.max(wrapped.length, taskW.length) * 5.5 + 1;
                        if (s.adjusted) {
                          y = checkPage(y);
                          pdf.setFont('helvetica', 'italic'); pdf.setFontSize(8); pdf.setTextColor(180, 120, 20);
                          const note = `slot adjusted due to capacity${s.due_date ? ` (was due ${s.due_date})` : ''}`;
                          const noteW = pdf.splitTextToSize(note, contentW - 6 - 14);
                          pdf.text(noteW, margin + 18, y); y += noteW.length * 4.5 + 1;
                          pdf.setFont('helvetica', 'normal'); pdf.setFontSize(10); pdf.setTextColor(40, 30, 60);
                        }
                      });
                      y += 2;
                    }

                    if (hasFocus) {
                      y = checkPage(y, 8);
                      pdf.setFont('helvetica', 'bold'); pdf.setFontSize(8.5); pdf.setTextColor(109, 40, 217);
                      pdf.text('FOCUS BLOCKS', margin + 2, y); y += 4.5;
                      pdf.setFont('helvetica', 'normal'); pdf.setFontSize(10); pdf.setTextColor(40, 30, 60);
                      day.focus_blocks.forEach(b => {
                        y = checkPage(y);
                        pdf.setTextColor(109, 40, 217);
                        pdf.text(`${b.start}-${b.end}`, margin + 4, y);
                        pdf.setTextColor(40, 30, 60);
                        pdf.text(pdfSafe(b.label || 'Deep Work'), margin + 28, y);
                        y += 6;
                      });
                      y += 2;
                    }

                    // Thin divider between days
                    pdf.setDrawColor(200, 190, 220); pdf.setLineWidth(0.2);
                    pdf.line(margin, y, pageW - margin, y); y += 5;
                  });

                  // Page numbers
                  const totalPages = pdf.internal.getNumberOfPages();
                  for (let i = 1; i <= totalPages; i++) {
                    pdf.setPage(i);
                    pdf.setFontSize(7.5); pdf.setTextColor(160, 140, 190);
                    pdf.text(`Page ${i} of ${totalPages}  ·  AI Executive Meeting Assistant`, margin, pageH - 7);
                  }

                  pdf.save(`weekly-plan${weekLabel ? '-' + weekLabel : ''}.pdf`);
                } catch (err) {
                  toast({ title: 'PDF download failed', description: err?.message || 'Please try again.', variant: 'destructive' });
                }
              }}
            >
              <Download className="h-4 w-4" /> Download PDF
            </Button>
          </div>

          {/* Summary + recommendations */}
          {(weekPlan.weekly_summary || weekPlan.recommendations?.length > 0 || weekPlan.unscheduled_tasks?.length > 0) && (
            <div className="rounded-2xl p-5 space-y-3" style={CARD_STYLE}>
              {weekPlan.weekly_summary && (
                <p className="text-white/80 text-sm">{weekPlan.weekly_summary}</p>
              )}
              {Array.isArray(weekPlan.unscheduled_tasks) && weekPlan.unscheduled_tasks.length > 0 && (
                <div className="rounded-xl p-3 bg-amber-500/10 border border-amber-500/20">
                  <p className="text-amber-400 text-xs font-semibold mb-1">
                    Couldn't fit this week ({weekPlan.unscheduled_tasks.length}) — the week is full
                  </p>
                  {weekPlan.unscheduled_tasks.map((t, i) => (
                    <p key={i} className="text-amber-300/80 text-xs">• {t}</p>
                  ))}
                </div>
              )}
              {Array.isArray(weekPlan.conflicts_detected) && weekPlan.conflicts_detected.length > 0 && (
                <div className="rounded-xl p-3 bg-red-500/10 border border-red-500/20">
                  <p className="text-red-400 text-xs font-semibold mb-1">Conflicts Detected</p>
                  {weekPlan.conflicts_detected.map((c, i) => (
                    <p key={i} className="text-red-300/80 text-xs">• {c}</p>
                  ))}
                </div>
              )}
              {Array.isArray(weekPlan.recommendations) && weekPlan.recommendations.length > 0 && (
                <div>
                  <p className="text-white/50 text-xs uppercase tracking-wide mb-1">Recommendations</p>
                  {weekPlan.recommendations.map((r, i) => (
                    <p key={i} className="text-violet-300 text-xs flex gap-1.5"><ChevronRight className="h-3 w-3 mt-0.5 flex-shrink-0" />{r}</p>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Daily plan cards */}
          {Array.isArray(weekPlan.daily_plans) && weekPlan.daily_plans.filter(day =>
            day.scheduled_meetings?.length > 0 ||
            day.suggested_task_slots?.length > 0 ||
            day.focus_blocks?.length > 0
          ).map((day, i) => (
            <div key={i} className="rounded-2xl overflow-hidden" style={CARD_STYLE}>
              <div className="flex items-center justify-between px-5 py-3 border-b border-white/10">
                <div className="flex items-center gap-3">
                  <div className="rounded-lg p-2 bg-violet-500/20">
                    <CalendarDays className="h-4 w-4 text-violet-400" />
                  </div>
                  <div>
                    <p className="text-white font-semibold text-sm">{day.day_name}</p>
                    <p className="text-white/40 text-xs">{day.date}</p>
                  </div>
                </div>
                {day.workload_level && (
                  <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs border ${WORKLOAD_COLORS[day.workload_level] || WORKLOAD_COLORS.moderate}`}>
                    {day.workload_level}
                  </span>
                )}
              </div>
              <div className="p-5 space-y-4">
                {/* Meetings */}
                {Array.isArray(day.scheduled_meetings) && day.scheduled_meetings.length > 0 && (
                  <div>
                    <p className="text-white/40 text-xs uppercase tracking-wide mb-2">Meetings</p>
                    <div className="space-y-1">
                      {day.scheduled_meetings.map((m, j) => (
                        <div key={j} className="flex items-center gap-2 text-sm">
                          <CalendarClock className="h-3.5 w-3.5 text-sky-400 flex-shrink-0" />
                          <span className="text-white/80">{typeof m === 'string' ? m : m.title}</span>
                          {typeof m !== 'string' && m.time && (
                            <span className="text-sky-400/70 font-mono text-xs ml-1">{m.time}</span>
                          )}
                          {typeof m !== 'string' && m.duration_minutes > 0 && (
                            <span className="text-white/30 text-xs ml-auto">{m.duration_minutes}min</span>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {/* Task slots */}
                {Array.isArray(day.suggested_task_slots) && day.suggested_task_slots.length > 0 && (
                  <div>
                    <p className="text-white/40 text-xs uppercase tracking-wide mb-2">Suggested Task Slots</p>
                    <div className="space-y-1">
                      {day.suggested_task_slots.map((slot, j) => (
                        <div key={j} className="flex items-center gap-2 text-sm flex-wrap">
                          <Clock className="h-3.5 w-3.5 text-violet-400 flex-shrink-0" />
                          <span className="text-violet-300 font-mono text-xs">{slot.time}</span>
                          <span className="text-white/80">{slot.task}</span>
                          {slot.duration_minutes && <span className="text-white/30 text-xs ml-auto">{slot.duration_minutes}min</span>}
                          {slot.adjusted && (
                            <span className="basis-full pl-6 text-[10px] text-amber-400/80">
                              ⚠ slot adjusted due to capacity{slot.due_date ? ` (was due ${slot.due_date})` : ''}
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {/* Focus blocks */}
                {Array.isArray(day.focus_blocks) && day.focus_blocks.length > 0 && (
                  <div>
                    <p className="text-white/40 text-xs uppercase tracking-wide mb-2">Focus Blocks</p>
                    <div className="space-y-1">
                      {day.focus_blocks.map((block, j) => (
                        <div key={j} className="flex items-center gap-2 text-sm">
                          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 flex-shrink-0" />
                          <span className="text-emerald-300 font-mono text-xs">{block.start}–{block.end}</span>
                          <span className="text-white/80">{block.label}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
);
