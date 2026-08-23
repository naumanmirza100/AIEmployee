import React from 'react';
import { initialsOf, paletteFor } from './replyDraftHelpers';

export const Avatar = ({ name, email, size = 'md' }) => {
  const dim = size === 'lg' ? 'h-11 w-11 text-sm' : size === 'sm' ? 'h-8 w-8 text-[11px]' : 'h-10 w-10 text-xs';
  const palette = paletteFor(email || name || '');
  return (
    <div className={`${dim} shrink-0 rounded-full bg-gradient-to-br ${palette} flex items-center justify-center font-bold text-white shadow-md ring-1 ring-white/10`}>
      {initialsOf(name, email)}
    </div>
  );
};

export const EmptyState = ({ icon: Icon, title, subtitle }) => (
  <div className="flex flex-col items-center justify-center text-center py-16 px-6">
    <div className="h-14 w-14 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center mb-4">
      <Icon className="h-7 w-7 text-gray-400" />
    </div>
    <div className="text-sm font-semibold text-white">{title}</div>
    {subtitle && <div className="text-xs text-gray-400 mt-1 max-w-xs">{subtitle}</div>}
  </div>
);

// Compact Prev / Next pager shown under each list. `page` is 1-based.
// Renders nothing when there's only a single page so short lists stay clean.
export const Paginator = ({ page, totalItems, pageSize, onPage }) => {
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
  if (totalPages <= 1) return null;
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(totalItems, page * pageSize);
  return (
    <div className="flex items-center justify-between gap-2 px-3 py-2 border-t border-white/10 bg-black/20">
      <span className="text-[11px] text-gray-500">
        {from}–{to} of {totalItems}
      </span>
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => onPage(page - 1)}
          disabled={page <= 1}
          className="px-2 py-1 rounded-md text-xs text-gray-300 border border-white/10 hover:bg-white/10 disabled:opacity-40 disabled:cursor-not-allowed transition"
        >
          Prev
        </button>
        <span className="text-[11px] text-gray-400 px-1 tabular-nums">
          {page} / {totalPages}
        </span>
        <button
          type="button"
          onClick={() => onPage(page + 1)}
          disabled={page >= totalPages}
          className="px-2 py-1 rounded-md text-xs text-gray-300 border border-white/10 hover:bg-white/10 disabled:opacity-40 disabled:cursor-not-allowed transition"
        >
          Next
        </button>
      </div>
    </div>
  );
};

// `onClick` is optional — when supplied the card becomes a button so the
// dashboard's counters can deep-link into the matching Emails folder.
export const StatCard = ({ icon: Icon, label, value, tint, iconTint, onClick }) => {
  const Tag = onClick ? 'button' : 'div';
  return (
    <Tag
      type={onClick ? 'button' : undefined}
      onClick={onClick}
      className={`w-full text-left rounded-xl bg-gradient-to-br ${tint} border border-white/10 p-4 flex items-center gap-3 backdrop-blur-sm ${
        onClick ? 'hover:border-white/25 hover:brightness-110 transition cursor-pointer' : ''
      }`}
    >
      <div className="h-10 w-10 rounded-lg bg-black/30 border border-white/10 flex items-center justify-center shrink-0">
        <Icon className={`h-5 w-5 ${iconTint}`} />
      </div>
      <div className="min-w-0">
        <div className="text-xs text-gray-400 font-medium truncate">{label}</div>
        <div className="text-xl font-bold text-white leading-tight">{value}</div>
      </div>
    </Tag>
  );
};

// Large mail-folder tile for the dashboard — Inbox / Drafts / Sent.
const FOLDER_ACCENTS = {
  cyan:     { ring: 'hover:border-cyan-500/40',    icon: 'text-cyan-300',    glow: 'from-cyan-500/15 to-blue-500/5' },
  fuchsia:  { ring: 'hover:border-fuchsia-500/40', icon: 'text-fuchsia-300', glow: 'from-fuchsia-500/15 to-purple-500/5' },
  emerald:  { ring: 'hover:border-emerald-500/40', icon: 'text-emerald-300', glow: 'from-emerald-500/15 to-teal-500/5' },
};

export const FolderTile = ({ icon: Icon, label, count, subtitle, accent = 'cyan', onClick }) => {
  const a = FOLDER_ACCENTS[accent] || FOLDER_ACCENTS.cyan;
  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full text-left rounded-2xl bg-gradient-to-br ${a.glow} bg-black/40 border border-white/10 backdrop-blur-sm p-5 flex items-start gap-4 transition ${a.ring} hover:bg-white/[0.04]`}
    >
      <div className="h-12 w-12 rounded-xl bg-black/40 border border-white/10 flex items-center justify-center shrink-0">
        <Icon className={`h-6 w-6 ${a.icon}`} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className="text-base font-semibold text-white">{label}</span>
          <span className={`text-sm font-bold ${a.icon} tabular-nums`}>{count}</span>
        </div>
        {subtitle && <div className="text-xs text-gray-400 mt-1">{subtitle}</div>}
      </div>
    </button>
  );
};
