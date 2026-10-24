import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

// Chat-friendly styling map for ReactMarkdown. Kept minimal (~10 tags) so
// assistant responses render with bold, lists, headings, and paragraph
// spacing without requiring the @tailwindcss/typography plugin. Reused by
// HR + Frontline knowledge Q&A + floating chats so their look stays uniform.
const chatMarkdownComponents = {
  p: ({ children }) => <p className="my-2 leading-relaxed">{children}</p>,
  strong: ({ children }) => <strong className="font-semibold text-white">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  ul: ({ children }) => <ul className="list-disc pl-5 my-2 space-y-1">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal pl-5 my-2 space-y-1">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  h1: ({ children }) => <h1 className="text-base font-bold mt-3 mb-2">{children}</h1>,
  h2: ({ children }) => <h2 className="text-base font-semibold mt-3 mb-2">{children}</h2>,
  h3: ({ children }) => <h3 className="text-sm font-semibold mt-3 mb-1.5">{children}</h3>,
  code: ({ children }) => (
    <code className="px-1.5 py-0.5 rounded bg-white/10 text-[0.85em] font-mono">{children}</code>
  ),
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer" className="underline text-violet-300 hover:text-violet-200">
      {children}
    </a>
  ),
};

// Documents also carry tables (Marketing's reports and briefs), which need the GFM plugin. Chat answers leave it off
// so they render exactly as before.
const GFM = [remarkGfm];
const documentMarkdownComponents = {
  ...chatMarkdownComponents,
  h4: ({ children }) => <h4 className="text-sm font-semibold mt-2 mb-1">{children}</h4>,
  hr: () => <hr className="my-4 border-border" />,
  table: ({ children }) => (
    <div className="my-3 overflow-x-auto">
      <table className="w-full border-collapse text-sm">{children}</table>
    </div>
  ),
  th: ({ children }) => <th className="border border-border bg-muted px-3 py-1.5 text-left font-semibold">{children}</th>,
  td: ({ children }) => <td className="border border-border px-3 py-1.5 align-top">{children}</td>,
};

export default function ChatMarkdown({ children, className = '', tables = false }) {
  return (
    <div className={`break-words ${className}`}>
      <ReactMarkdown
        components={tables ? documentMarkdownComponents : chatMarkdownComponents}
        remarkPlugins={tables ? GFM : undefined}
      >
        {children || ''}
      </ReactMarkdown>
    </div>
  );
}
