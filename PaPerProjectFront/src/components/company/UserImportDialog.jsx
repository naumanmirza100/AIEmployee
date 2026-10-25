import React, { useRef, useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { useToast } from '@/components/ui/use-toast';
import { companyApi } from '@/services/companyAuthService';
import { Loader2, Download, Upload, Copy, CheckCircle2, AlertTriangle, FileSpreadsheet } from 'lucide-react';

// Adding people from an Excel sheet: download the template, fill one row per person, upload it. Each person gets
// a password made for them, shown here once (it is not stored readable), so the list can be copied or downloaded
// and handed out; people can change theirs after signing in.
export default function UserImportDialog({ open, onOpenChange, onAdded }) {
  const { toast } = useToast();
  const fileInput = useRef(null);
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  const reset = () => { setFile(null); setResult(null); if (fileInput.current) fileInput.current.value = ''; };
  const close = (next) => {
    if (!next && result?.added) onAdded?.();
    if (!next) reset();
    onOpenChange(next);
  };

  const downloadTemplate = async () => {
    try {
      const blob = await companyApi.get('/company/users/import-template', { responseType: 'blob' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'add-users-template.xlsx';
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast({ title: 'Template not downloaded', description: e.message, variant: 'destructive' });
    }
  };

  const upload = async () => {
    if (!file) {
      toast({ title: 'Choose the sheet first', description: 'Pick the filled-in template (.xlsx or .csv).', variant: 'destructive' });
      return;
    }
    const form = new FormData();
    form.append('file', file);
    setBusy(true);
    try {
      const res = await companyApi.post('/company/users/import', form);
      setResult(res.data);
      toast({ title: res.message || 'Done', description: res.data.refused ? 'Some rows were not added: see why below.' : 'Everyone on the sheet was added.' });
    } catch (e) {
      toast({ title: 'Sheet not imported', description: e.message, variant: 'destructive' });
    } finally {
      setBusy(false);
    }
  };

  const copyPasswords = async () => {
    const lines = result.rows.filter((r) => r.status === 'added').map((r) => `${r.full_name}\t${r.email}\t${r.password}`);
    try {
      await navigator.clipboard.writeText(['Name\tEmail\tPassword', ...lines].join('\n'));
      toast({ title: 'Copied', description: `${lines.length} sign-ins copied.` });
    } catch {
      toast({ title: 'Copy failed', description: 'Clipboard unavailable: download the list instead.', variant: 'destructive' });
    }
  };

  const downloadList = async () => {
    const XLSX = await import('xlsx');
    const rows = result.rows.map((r) => ({
      Row: r.row, Name: r.full_name, Email: r.email, Username: r.username || '', Role: r.role,
      Added: r.status === 'added' ? 'Yes' : 'No', Password: r.password || '',
      'Not added because': r.reason || '', Notes: (r.notes || []).join(' '),
    }));
    const book = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(book, XLSX.utils.json_to_sheet(rows), 'Sign-ins');
    XLSX.writeFile(book, 'new-users-with-passwords.xlsx');
  };

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto" data-testid="user-import-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><FileSpreadsheet className="h-5 w-5" />Add users from Excel</DialogTitle>
          <DialogDescription>
            One row per person: full name, email, phone number and role are required; joining date, job title,
            department and the rest are optional. A password is made for each person.
          </DialogDescription>
        </DialogHeader>

        {!result ? (
          <div className="space-y-5">
            <div className="rounded-lg border p-4">
              <p className="text-sm font-medium">1. Download the template and fill it in</p>
              <p className="mt-1 text-xs text-muted-foreground">Its second sheet, "How to fill", says what goes in each column.</p>
              <Button variant="outline" className="mt-3" onClick={downloadTemplate}>
                <Download className="h-4 w-4 mr-2" />Download template
              </Button>
            </div>
            <div className="rounded-lg border p-4">
              <p className="text-sm font-medium">2. Upload the filled-in sheet</p>
              <input
                ref={fileInput}
                type="file"
                accept=".xlsx,.csv"
                className="mt-3 block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-primary file:px-3 file:py-2 file:text-primary-foreground"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
                data-testid="user-import-file"
              />
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => close(false)}>Cancel</Button>
              <Button onClick={upload} disabled={busy || !file}>
                {busy ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Upload className="h-4 w-4 mr-2" />}
                Add people
              </Button>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <span className="inline-flex items-center gap-1.5 text-emerald-500"><CheckCircle2 className="h-4 w-4" />{result.added} added</span>
              {result.refused > 0 && (
                <span className="inline-flex items-center gap-1.5 text-amber-500"><AlertTriangle className="h-4 w-4" />{result.refused} not added</span>
              )}
            </div>
            {result.added > 0 && (
              <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
                The passwords are shown only now. Copy them or download the list before closing, and give each
                person theirs; they can change it after signing in.
              </div>
            )}
            <div className="overflow-x-auto rounded-lg border">
              <table className="w-full text-sm" data-testid="user-import-results">
                <thead className="bg-muted/50 text-left text-xs uppercase text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2">Row</th><th className="px-3 py-2">Name</th><th className="px-3 py-2">Email</th>
                    <th className="px-3 py-2">Role</th><th className="px-3 py-2">Password</th><th className="px-3 py-2">Result</th>
                  </tr>
                </thead>
                <tbody>
                  {result.rows.map((r) => (
                    <tr key={r.row} className="border-t align-top">
                      <td className="px-3 py-2 text-muted-foreground">{r.row}</td>
                      <td className="px-3 py-2">{r.full_name}</td>
                      <td className="px-3 py-2">{r.email}</td>
                      <td className="px-3 py-2">{r.role}</td>
                      <td className="px-3 py-2 font-mono">{r.password || '—'}</td>
                      <td className="px-3 py-2">
                        {r.status === 'added'
                          ? <span className="text-emerald-500">Added</span>
                          : <span className="text-amber-500">Not added: {r.reason}</span>}
                        {(r.notes || []).map((n) => <p key={n} className="mt-1 text-xs text-muted-foreground">{n}</p>)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex flex-wrap justify-end gap-2">
              {result.added > 0 && (
                <>
                  <Button variant="outline" onClick={copyPasswords}><Copy className="h-4 w-4 mr-2" />Copy sign-ins</Button>
                  <Button variant="outline" onClick={downloadList}><Download className="h-4 w-4 mr-2" />Download list</Button>
                </>
              )}
              <Button variant="outline" onClick={() => { if (result.added) onAdded?.(); reset(); }}>Upload another sheet</Button>
              <Button onClick={() => close(false)}>Done</Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
