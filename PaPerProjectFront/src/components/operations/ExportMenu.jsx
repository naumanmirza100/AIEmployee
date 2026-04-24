import React, { useState } from 'react';
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu';
import { useToast } from '@/components/ui/use-toast';
import { Download, FileCode, FileText, Loader2 } from 'lucide-react';
import { downloadAsMarkdown, downloadAsPdf } from '@/utils/documentExporters';

/**
 * ExportMenu — reusable dropdown to export a document as .md or .pdf
 *
 * Props
 *   docId          number|string        — required for PDF (server-generated)
 *   title          string               — filename
 *   content        string               — markdown content (for .md export)
 *   fetchPdfBlob   (id) => Promise<Blob> — how to fetch the PDF from the server
 *   onExported?    (format) => void
 *   trigger?       ReactElement         — custom trigger; defaults to an icon button
 *   disabled?      boolean
 */
const ExportMenu = ({
  docId,
  title,
  content,
  fetchPdfBlob,
  onExported,
  trigger,
  disabled = false,
}) => {
  const { toast } = useToast();
  const [downloading, setDownloading] = useState(false);

  const handleMd = () => {
    try {
      downloadAsMarkdown({ title, content });
      onExported?.('md');
    } catch (err) {
      toast({ title: 'Download failed', description: err?.message, variant: 'destructive' });
    }
  };

  const handlePdf = async () => {
    if (downloading) return;
    if (!docId) {
      toast({ title: 'Save first', description: 'Please save the document before exporting.', variant: 'destructive' });
      return;
    }
    try {
      setDownloading(true);
      await downloadAsPdf({ docId, title, fetchPdfBlob });
      onExported?.('pdf');
    } catch (err) {
      toast({
        title: 'PDF download failed',
        description: err?.message || 'Please try again.',
        variant: 'destructive',
      });
    } finally {
      setDownloading(false);
    }
  };

  const defaultTrigger = (
    <button
      type="button"
      title="Download"
      disabled={disabled || downloading}
      className="h-8 w-8 flex items-center justify-center rounded-md border border-white/10 bg-black/30 text-white/75 hover:text-amber-200 hover:bg-amber-500/10 hover:border-amber-500/30 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
    >
      {downloading
        ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
        : <Download className="h-3.5 w-3.5" />}
    </button>
  );

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild disabled={disabled || downloading}>
        {trigger || defaultTrigger}
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        className="bg-[#1a1333] border border-white/10 text-white/90 min-w-[200px]"
      >
        <DropdownMenuLabel className="text-[10px] uppercase tracking-wider text-white/50 font-semibold">
          Download as
        </DropdownMenuLabel>
        <DropdownMenuSeparator className="bg-white/5" />
        <DropdownMenuItem
          onClick={handleMd}
          className="cursor-pointer text-sm focus:bg-amber-500/10 focus:text-amber-200"
        >
          <FileCode className="h-4 w-4 mr-2 text-amber-300" />
          <div className="flex flex-col items-start">
            <span className="font-medium">Markdown (.md)</span>
            <span className="text-[10px] text-white/50">Raw source, editable</span>
          </div>
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={handlePdf}
          disabled={downloading}
          className="cursor-pointer text-sm focus:bg-amber-500/10 focus:text-amber-200"
        >
          {downloading
            ? <Loader2 className="h-4 w-4 mr-2 text-amber-300 animate-spin" />
            : <FileText className="h-4 w-4 mr-2 text-amber-300" />}
          <div className="flex flex-col items-start">
            <span className="font-medium">PDF (.pdf)</span>
            <span className="text-[10px] text-white/50">
              {downloading ? 'Generating…' : 'Formatted, print-ready'}
            </span>
          </div>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
};

export default ExportMenu;
