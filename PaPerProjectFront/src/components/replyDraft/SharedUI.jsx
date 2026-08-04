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

export const StatCard = ({ icon: Icon, label, value, tint, iconTint }) => (
  <div className={`rounded-xl bg-gradient-to-br ${tint} border border-white/10 p-4 flex items-center gap-3 backdrop-blur-sm`}>
    <div className="h-10 w-10 rounded-lg bg-black/30 border border-white/10 flex items-center justify-center">
      <Icon className={`h-5 w-5 ${iconTint}`} />
    </div>
    <div className="min-w-0">
      <div className="text-xs text-gray-400 font-medium truncate">{label}</div>
      <div className="text-xl font-bold text-white leading-tight">{value}</div>
    </div>
  </div>
);
