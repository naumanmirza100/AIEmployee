import React, { useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ChevronDown, ChevronUp, Download } from 'lucide-react';

// Schema reference for leads-upload modals. Mirrors the parser in
// api/views/marketing_agent.py:_upload_leads_from_file — column names
// here MUST stay aligned with the keys that helper looks up. Headers
// match case-insensitively and a single space is interchangeable with
// an underscore (so "First Name" and "first_name" both resolve to the
// first_name field).
export const LEAD_UPLOAD_COLUMNS = {
  required: [
    {
      key: 'email',
      label: 'email',
      example: 'lead@example.com',
      hint: 'The lead\'s email address. Rows without this are skipped.',
    },
    {
      key: 'first_name',
      label: 'first_name',
      altLabel: 'first name',
      example: 'John',
      hint: 'Used for personalization tokens like {{first_name}}. Rows with neither first nor last name (and no "name" fallback) are skipped.',
    },
    {
      key: 'last_name',
      label: 'last_name',
      altLabel: 'last name',
      example: 'Doe',
      hint: 'Used for personalization tokens like {{last_name}}. Rows with neither first nor last name (and no "name" fallback) are skipped.',
    },
  ],
  optional: [
    {
      key: 'name',
      label: 'name',
      example: 'John Doe',
      hint: 'Single-name fallback. Used only when first_name and last_name are both blank — split on the first space to satisfy the name requirement.',
    },
    {
      key: 'phone',
      label: 'phone',
      example: '+1 555 010 0100',
      hint: 'Optional contact number; not used for sending.',
    },
    {
      key: 'company',
      label: 'company',
      example: 'Acme Inc.',
      hint: 'Available as {{company}} in templates.',
    },
    {
      key: 'job_title',
      label: 'job_title',
      altLabel: 'job title',
      example: 'Sales Manager',
      hint: 'Available as {{job_title}} in templates.',
    },
    {
      key: 'source',
      label: 'source',
      example: 'LinkedIn',
      hint: 'Free-form attribution label (where the lead came from).',
    },
  ],
};

// Build a downloadable CSV template with a header row + one example
// row. Lets the user open it in Excel, fill in their data, and upload
// without guessing the column names. Stays in sync with
// LEAD_UPLOAD_COLUMNS so the template never drifts from the docs.
export const buildLeadsTemplateCsv = () => {
  const cols = [
    ...LEAD_UPLOAD_COLUMNS.required,
    ...LEAD_UPLOAD_COLUMNS.optional.filter((c) => c.key !== 'name'), // 'name' is a fallback, not a primary header
  ];
  const headers = cols.map((c) => c.label).join(',');
  // Single example row so a fresh file isn't a confusing one-line CSV.
  // CSV-quote anything containing a comma; example values here don't, but
  // future additions might — quoting unconditionally is the safe rule.
  const exampleRow = cols
    .map((c) => `"${(c.example || '').replace(/"/g, '""')}"`)
    .join(',');
  return `${headers}\n${exampleRow}\n`;
};

export const downloadLeadsTemplateCsv = () => {
  const csv = buildLeadsTemplateCsv();
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'campaign_leads_template.csv';
  a.click();
  URL.revokeObjectURL(a.href);
};

/**
 * Collapsible required/optional column reference tables + a "Template CSV"
 * download button, for use inside any "Upload leads" modal. Both column
 * sections toggle independently.
 */
const LeadsUploadFields = () => {
  const [requiredColumnsOpen, setRequiredColumnsOpen] = useState(true);
  const [optionalColumnsOpen, setOptionalColumnsOpen] = useState(true);

  return (
    <>
      {/* Column reference — required */}
      <div className="rounded-lg border border-border overflow-hidden">
        <button
          type="button"
          onClick={() => setRequiredColumnsOpen((v) => !v)}
          className="w-full bg-destructive/10 border-b border-border px-3 py-2 flex items-center justify-between hover:bg-destructive/15 transition-colors"
        >
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-destructive">Required column</span>
            <Badge variant="destructive" className="h-5 text-[10px]">Must include</Badge>
          </div>
          {requiredColumnsOpen ? <ChevronUp className="h-4 w-4 text-destructive" /> : <ChevronDown className="h-4 w-4 text-destructive" />}
        </button>
        {requiredColumnsOpen && (
          <div className="divide-y divide-border">
            {LEAD_UPLOAD_COLUMNS.required.map((col) => (
              <div key={col.key} className="px-3 py-2 grid grid-cols-12 gap-3 items-start">
                <div className="col-span-4 sm:col-span-3">
                  <code className="font-mono text-xs bg-muted px-1.5 py-0.5 rounded">
                    {col.label}
                  </code>
                </div>
                <div className="col-span-4 sm:col-span-3 text-xs text-muted-foreground font-mono truncate">
                  {col.example}
                </div>
                <div className="col-span-12 sm:col-span-6 text-xs text-muted-foreground">
                  {col.hint}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Column reference — optional */}
      <div className="rounded-lg border border-border overflow-hidden">
        <button
          type="button"
          onClick={() => setOptionalColumnsOpen((v) => !v)}
          className="w-full bg-muted border-b border-border px-3 py-2 flex items-center justify-between hover:bg-muted/70 transition-colors"
        >
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold">Optional columns</span>
            <Badge variant="secondary" className="h-5 text-[10px]">Skip any you don't need</Badge>
          </div>
          {optionalColumnsOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </button>
        {optionalColumnsOpen && (
          <div className="divide-y divide-border max-h-64 overflow-y-auto no-scrollbar">
            {LEAD_UPLOAD_COLUMNS.optional.map((col) => (
              <div key={col.key} className="px-3 py-2 grid grid-cols-12 gap-3 items-start">
                <div className="col-span-4 sm:col-span-3">
                  <code className="font-mono text-xs bg-muted px-1.5 py-0.5 rounded">
                    {col.label}
                  </code>
                  {col.altLabel && (
                    <div className="mt-0.5 text-[10px] text-muted-foreground">
                      or <code className="font-mono">{col.altLabel}</code>
                    </div>
                  )}
                </div>
                <div className="col-span-4 sm:col-span-3 text-xs text-muted-foreground font-mono truncate">
                  {col.example}
                </div>
                <div className="col-span-12 sm:col-span-6 text-xs text-muted-foreground">
                  {col.hint}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Download template — gets the user a working starter file
          so they don't have to type the headers manually. */}
      <div className="flex items-center justify-between rounded-lg border border-dashed border-border bg-muted/30 px-3 py-2">
        <div className="text-xs text-muted-foreground">
          Not sure where to start? Grab a CSV with all the headers pre-filled.
        </div>
        <Button type="button" variant="outline" size="sm" onClick={downloadLeadsTemplateCsv}>
          <Download className="h-4 w-4 mr-1.5" />
          Template CSV
        </Button>
      </div>
    </>
  );
};

export default LeadsUploadFields;
