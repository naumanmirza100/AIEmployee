import React from 'react';
import { Loader2 } from 'lucide-react';

/**
 * HRUiKit — small shared UI primitives used across HR tab components.
 * Hoisted from HRDashboard.jsx so the 3 extracted tab components
 * (HRDocumentsTab, HREmployeesTab, HRWorkflowsTab) don't need to
 * duplicate them or import from the parent (which would create a
 * circular import).
 */

export const Spinner = () => (
  <div className="flex justify-center py-8">
    <Loader2 className="h-5 w-5 animate-spin text-white/40" />
  </div>
);

export const EmptyState = ({ icon: Icon, title, sub }) => (
  <div className="flex flex-col items-center justify-center py-14 text-center">
    <div className="h-14 w-14 rounded-2xl bg-violet-500/10 border border-violet-400/20 flex items-center justify-center mb-3">
      <Icon className="h-7 w-7 text-violet-400" />
    </div>
    <div className="font-medium text-white/90 mb-1">{title}</div>
    {sub && <div className="text-sm text-white/50 max-w-sm">{sub}</div>}
  </div>
);
