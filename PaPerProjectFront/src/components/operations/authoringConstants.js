/**
 * Shared constants for the Document Authoring module.
 * Kept separate so dialogs / main form / sidebar all stay in sync.
 */

import {
  FileCheck, BookOpen, Briefcase, MessageSquare, ScrollText, PenTool,
} from 'lucide-react';

export const AUTHORING_ACCENT = '#f59e0b';
export const AUTHORING_ACCENT_SOFT = 'rgba(245,158,11,0.12)';
export const AUTHORING_ACCENT_BORDER = 'rgba(245,158,11,0.28)';

export const TEMPLATES = [
  {
    value: 'weekly_report',
    label: 'Weekly Report',
    description: 'Summarise the week: wins, risks, metrics, next steps.',
    icon: FileCheck,
  },
  {
    value: 'monthly_analysis',
    label: 'Monthly Analysis',
    description: 'Deep-dive analysis with trends, insights, and recommendations.',
    icon: BookOpen,
  },
  {
    value: 'executive_summary',
    label: 'Executive Summary',
    description: 'Concise, decision-focused brief for leadership.',
    icon: Briefcase,
  },
  {
    value: 'memo',
    label: 'Memo',
    description: 'Formal memorandum with purpose, discussion, and action.',
    icon: MessageSquare,
  },
  {
    value: 'proposal',
    label: 'Proposal',
    description: 'Persuasive proposal: problem, solution, scope, timeline, budget.',
    icon: ScrollText,
  },
  {
    value: 'custom',
    label: 'Custom',
    description: 'Free-form document following your instructions exactly.',
    icon: PenTool,
  },
];

export const TONES = [
  { value: 'formal',    label: 'Formal',    hint: 'Polished corporate' },
  { value: 'concise',   label: 'Concise',   hint: 'Short & punchy' },
  { value: 'detailed',  label: 'Detailed',  hint: 'Thorough & evidence-based' },
  { value: 'technical', label: 'Technical', hint: 'Precise terminology' },
];

export const getTemplate = (value) =>
  TEMPLATES.find((t) => t.value === value) || TEMPLATES[0];

export const getTone = (value) =>
  TONES.find((t) => t.value === value) || TONES[0];
