import React from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Printer } from 'lucide-react';

const DECISION_COLOR = { INTERVIEW: '#16a34a', HOLD: '#ca8a04', REJECT: '#dc2626' };
const DECISION_LABEL = { INTERVIEW: 'Interview', HOLD: 'Hold', REJECT: 'Reject' };

const fmt = (val) => (val !== null && val !== undefined && val !== '' ? val : '—');
const fmtDate = (val) => {
  if (!val) return '—';
  try { return new Date(val).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }); }
  catch { return '—'; }
};
const fmtScore = (val) => (val !== null && val !== undefined ? `${val}%` : '—');

const buildPrintHTML = (records, jobs, jobFilter, decisionFilter, total) => {
  const selectedJob = jobs.find(j => j.id.toString() === jobFilter);

  const rows = records.map((record, idx) => {
    const p = record.parsed || {};
    const dColor = DECISION_COLOR[record.qualification_decision] || '#6b7280';
    const dLabel = DECISION_LABEL[record.qualification_decision] || fmt(record.qualification_decision);
    const score = fmtScore(record.qualification_confidence ?? record.role_fit_score);
    const date = fmtDate(record.created_at);
    const bg = idx % 2 === 0 ? '#ffffff' : '#f9f6ff';

    return `<tr style="background:${bg};border-bottom:1px solid #ede9fe;">
      <td style="padding:9px 10px;font-weight:700;color:#7c3aed;text-align:center;">${record.rank ?? idx + 1}</td>
      <td style="padding:9px 10px;">
        <div style="font-weight:600;color:#1a0a2e;">${fmt(p.name || record.file_name)}</div>
        ${p.email ? `<div style="font-size:10px;color:#6b7280;margin-top:2px;">${p.email}</div>` : ''}
      </td>
      <td style="padding:9px 10px;color:#374151;font-size:11px;">${fmt(p.phone || p.mobile || p.contact)}</td>
      <td style="padding:9px 10px;color:#374151;font-size:11px;">${fmt(record.job_description_title)}</td>
      <td style="padding:9px 10px;text-align:center;">
        <span style="display:inline-block;padding:3px 10px;border-radius:999px;font-size:10px;font-weight:700;color:#fff;background:${dColor};">${dLabel}</span>
      </td>
      <td style="padding:9px 10px;text-align:center;font-weight:700;color:#7c3aed;">${score}</td>
      <td style="padding:9px 10px;color:#6b7280;font-size:11px;">${date}</td>
    </tr>`;
  }).join('');

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Candidates Report</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:'Segoe UI',Arial,sans-serif;font-size:12px;color:#111;background:#fff;-webkit-print-color-adjust:exact;print-color-adjust:exact;}
    .wrapper{padding:30px 36px}
    .header{display:flex;justify-content:space-between;align-items:flex-start;padding-bottom:14px;border-bottom:3px solid #7c3aed;margin-bottom:18px}
    .header h1{font-size:22px;font-weight:700;color:#1a0a2e}
    .header .sub{font-size:11px;color:#6b7280;margin-top:3px}
    .badge-row{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}
    .badge{background:#f5f0ff;border:1px solid #ddd6fe;border-radius:6px;padding:3px 11px;font-size:11px;color:#4c1d95}
    .badge strong{color:#7c3aed}
    table{width:100%;border-collapse:collapse;font-size:11.5px}
    thead tr{background:#1a0a2e}
    thead th{padding:10px 10px;color:#fff;font-weight:600;text-align:left;white-space:nowrap}
    thead th.center{text-align:center}
    tfoot tr{background:#f5f0ff}
    tfoot td{padding:8px 10px;font-size:11px;color:#4c1d95;font-weight:600}
    .footer{margin-top:20px;padding-top:10px;border-top:1px solid #e5e7eb;display:flex;justify-content:space-between;font-size:10px;color:#9ca3af}
    @media print{
      body{margin:0}
      .wrapper{padding:16px 20px}
      .no-print{display:none}
    }
  </style>
</head>
<body>
<div class="wrapper">
  <div class="header">
    <div>
      <h1>Candidates Report</h1>
      <div class="sub">Generated: ${new Date().toLocaleString()}</div>
    </div>
    <div style="text-align:right">
      <div style="font-size:14px;font-weight:700;color:#7c3aed;">AI Recruitment System</div>
      <div style="font-size:11px;color:#6b7280;margin-top:3px;">Confidential Document</div>
    </div>
  </div>
  <div class="badge-row">
    <span class="badge">Job: <strong>${selectedJob?.title || 'All Jobs'}</strong></span>
    <span class="badge">Decision: <strong>${DECISION_LABEL[decisionFilter] || 'All'}</strong></span>
    <span class="badge">Records shown: <strong>${records.length}</strong></span>
    <span class="badge">Total: <strong>${total}</strong></span>
  </div>
  <table>
    <thead>
      <tr>
        <th class="center" style="width:40px">#</th>
        <th>Name / Email</th>
        <th>Phone</th>
        <th>Job Applied</th>
        <th class="center">Decision</th>
        <th class="center">Score</th>
        <th>Date</th>
      </tr>
    </thead>
    <tbody>${rows || '<tr><td colspan="7" style="text-align:center;padding:20px;color:#999;">No records found</td></tr>'}</tbody>
    <tfoot>
      <tr>
        <td colspan="7">Total records: ${records.length} &nbsp;|&nbsp; Printed: ${new Date().toLocaleString()}</td>
      </tr>
    </tfoot>
  </table>
  <div class="footer">
    <span>AI Recruitment System — For internal use only</span>
    <span>Page 1</span>
  </div>
</div>
</body>
</html>`;
};

const CandidatePrintView = ({ open, onClose, records, jobs, jobFilter, decisionFilter, total }) => {
  const selectedJob = jobs.find(j => j.id.toString() === jobFilter);

  const handlePrint = () => {
    const html = buildPrintHTML(records, jobs, jobFilter, decisionFilter, total);
    const win = window.open('', '_blank');
    win.document.open();
    win.document.write(html);
    win.document.close();
    win.onload = () => { win.focus(); win.print(); };
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-5xl w-full bg-[#0d0b1a] border border-white/10 text-white p-0 overflow-hidden">
        <DialogHeader className="px-6 pt-5 pb-4 border-b border-white/10 flex flex-row items-center justify-between">
          <div>
            <DialogTitle className="text-lg font-semibold text-white">Print Preview</DialogTitle>
            <p className="text-xs text-white/50 mt-0.5">
              {records.length} of {total} candidates
              {selectedJob ? ` · ${selectedJob.title}` : ' · All Jobs'}
              {decisionFilter ? ` · ${DECISION_LABEL[decisionFilter]}` : ''}
            </p>
          </div>
          <Button onClick={handlePrint} className="bg-violet-600 hover:bg-violet-700 gap-2 text-sm shrink-0">
            <Printer className="h-4 w-4" />
            Print / Save PDF
          </Button>
        </DialogHeader>

        {/* Preview table */}
        <div className="overflow-auto max-h-[72vh] p-5 custom-sidebar-scroll">
          <div className="bg-white rounded-lg overflow-hidden text-[#111] shadow-sm">

            {/* Header */}
            <div className="flex justify-between items-start px-6 py-5" style={{ borderBottom: '3px solid #7c3aed' }}>
              <div>
                <h2 className="text-xl font-bold text-[#1a0a2e]">Candidates Report</h2>
                <p className="text-xs text-gray-500 mt-1">Generated: {new Date().toLocaleString()}</p>
              </div>
              <div className="text-right">
                <div className="text-sm font-bold text-violet-600">AI Recruitment System</div>
                <div className="text-xs text-gray-500 mt-1">Confidential Document</div>
              </div>
            </div>

            {/* Filters */}
            <div className="flex flex-wrap gap-2 px-6 py-3" style={{ borderBottom: '1px solid #ede9fe', background: '#fdfbff' }}>
              <span className="px-3 py-1 rounded-full text-xs font-medium" style={{ background: '#f5f0ff', color: '#4c1d95', border: '1px solid #ddd6fe' }}>
                Job: <strong>{selectedJob?.title || 'All Jobs'}</strong>
              </span>
              <span className="px-3 py-1 rounded-full text-xs font-medium" style={{ background: '#f5f0ff', color: '#4c1d95', border: '1px solid #ddd6fe' }}>
                Decision: <strong>{DECISION_LABEL[decisionFilter] || 'All'}</strong>
              </span>
              <span className="px-3 py-1 rounded-full text-xs font-medium" style={{ background: '#f5f0ff', color: '#4c1d95', border: '1px solid #ddd6fe' }}>
                Showing: <strong>{records.length}</strong> of <strong>{total}</strong>
              </span>
            </div>

            {/* Table */}
            <table className="w-full" style={{ borderCollapse: 'collapse', fontSize: '12px' }}>
              <thead>
                <tr style={{ background: '#1a0a2e', color: '#fff' }}>
                  <th style={{ padding: '10px 10px', textAlign: 'center', width: 40 }}>#</th>
                  <th style={{ padding: '10px 10px', textAlign: 'left' }}>Name / Email</th>
                  <th style={{ padding: '10px 10px', textAlign: 'left' }}>Phone</th>
                  <th style={{ padding: '10px 10px', textAlign: 'left' }}>Job Applied</th>
                  <th style={{ padding: '10px 10px', textAlign: 'center' }}>Decision</th>
                  <th style={{ padding: '10px 10px', textAlign: 'center' }}>Score</th>
                  <th style={{ padding: '10px 10px', textAlign: 'left' }}>Date</th>
                </tr>
              </thead>
              <tbody>
                {records.length === 0 ? (
                  <tr><td colSpan={7} className="text-center py-8 text-gray-400">No records</td></tr>
                ) : records.map((record, idx) => {
                  const p = record.parsed || {};
                  const dColor = DECISION_COLOR[record.qualification_decision] || '#6b7280';
                  const dLabel = DECISION_LABEL[record.qualification_decision] || fmt(record.qualification_decision);
                  const score = fmtScore(record.qualification_confidence ?? record.role_fit_score);
                  const date = fmtDate(record.created_at);
                  return (
                    <tr key={record.id} style={{ background: idx % 2 === 0 ? '#fff' : '#f9f6ff', borderBottom: '1px solid #ede9fe' }}>
                      <td style={{ padding: '9px 10px', textAlign: 'center', fontWeight: 700, color: '#7c3aed' }}>{record.rank ?? idx + 1}</td>
                      <td style={{ padding: '9px 10px' }}>
                        <div style={{ fontWeight: 600, color: '#1a0a2e' }}>{fmt(p.name || record.file_name)}</div>
                        {p.email && <div style={{ fontSize: 10, color: '#6b7280', marginTop: 2 }}>{p.email}</div>}
                      </td>
                      <td style={{ padding: '9px 10px', color: '#374151', fontSize: 11 }}>{fmt(p.phone || p.mobile || p.contact)}</td>
                      <td style={{ padding: '9px 10px', color: '#374151', fontSize: 11 }}>{fmt(record.job_description_title)}</td>
                      <td style={{ padding: '9px 10px', textAlign: 'center' }}>
                        <span style={{ display: 'inline-block', padding: '3px 10px', borderRadius: 999, fontSize: 10, fontWeight: 700, color: '#fff', background: dColor }}>{dLabel}</span>
                      </td>
                      <td style={{ padding: '9px 10px', textAlign: 'center', fontWeight: 700, color: '#7c3aed' }}>{score}</td>
                      <td style={{ padding: '9px 10px', color: '#6b7280', fontSize: 11 }}>{date}</td>
                    </tr>
                  );
                })}
              </tbody>
              <tfoot>
                <tr style={{ background: '#f5f0ff' }}>
                  <td colSpan={7} style={{ padding: '8px 10px', fontSize: 11, color: '#4c1d95', fontWeight: 600 }}>
                    Total records: {records.length} &nbsp;·&nbsp; Printed: {new Date().toLocaleString()}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default CandidatePrintView;
