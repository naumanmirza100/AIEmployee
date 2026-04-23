/**
 * documentExporters
 *
 * Pure utilities for downloading a document in different formats.
 * Framework-agnostic (no React) so they can be reused anywhere.
 *
 *  • downloadAsMarkdown({ title, content })  → saves a .md file (client-side)
 *  • downloadAsPdf({ docId, title, fetchPdfBlob }) → fetches backend-generated PDF
 *                                                    and triggers a direct download
 */

const sanitizeFilename = (name) =>
  String(name || 'document').replace(/[^a-z0-9-_\s]/gi, '_').trim().slice(0, 80) || 'document';

const triggerBlobDownload = (blob, filename) => {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.rel = 'noopener';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  // Revoke on the next tick so the browser has a chance to start the download.
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};

// ──────────────────────────────────────────────
// Markdown download (client-side, zero deps)
// ──────────────────────────────────────────────
export function downloadAsMarkdown({ title, content }) {
  const blob = new Blob([content || ''], { type: 'text/markdown;charset=utf-8' });
  triggerBlobDownload(blob, `${sanitizeFilename(title)}.md`);
}

// ──────────────────────────────────────────────
// PDF download (server-generated, true vector PDF)
// ──────────────────────────────────────────────
/**
 * @param {object} opts
 * @param {number|string} opts.docId
 * @param {string} opts.title
 * @param {() => Promise<Blob>} opts.fetchPdfBlob  Injected so this util stays
 *                                                 agnostic of how the blob is fetched.
 */
export async function downloadAsPdf({ docId, title, fetchPdfBlob }) {
  if (!docId) throw new Error('docId is required');
  if (typeof fetchPdfBlob !== 'function') throw new Error('fetchPdfBlob function is required');

  const blob = await fetchPdfBlob(docId);
  triggerBlobDownload(blob, `${sanitizeFilename(title)}.pdf`);
}

export default { downloadAsMarkdown, downloadAsPdf };
