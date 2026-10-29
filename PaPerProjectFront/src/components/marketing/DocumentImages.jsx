import React, { useEffect, useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { useToast } from '@/components/ui/use-toast';
import { Download, ImagePlus, Loader2, Trash2 } from 'lucide-react';
import marketingAgentService from '@/services/marketingAgentService';
import { cn } from '@/lib/utils';

// Pictures for social posts and ad copy, made by OpenAI's image model from an idea
// and kept with the document; they also go into its PDF (the user's decision of
// 29 Oct 2026). Each social post ends with an image idea in italics: those are
// offered to start from.

const SHAPES = [['square', 'Square'], ['landscape', 'Landscape'], ['portrait', 'Portrait']];
const ASPECT = { square: 'aspect-square', landscape: 'aspect-[3/2]', portrait: 'aspect-[2/3]' };
const MAX_PICTURES = 8;

export function imageIdeas(content) {
  const ideas = [];
  for (const line of (content || '').split('\n')) {
    const found = line.trim().match(/^[*_]([^*_].*?)[*_]$/);
    if (!found) continue;
    const idea = found[1].replace(/^(image idea|image|visual|picture)\s*:\s*/i, '').trim();
    if (idea.length > 15 && !ideas.includes(idea)) ideas.push(idea);
  }
  return ideas.slice(0, 12);
}

function Picture({ documentId, picture, deleting, onDelete }) {
  const [url, setUrl] = useState(null);

  useEffect(() => {
    let made = null;
    let live = true;
    marketingAgentService.getDocumentImageBlob(documentId, picture.id)
      .then((blob) => {
        if (!live) return;
        made = URL.createObjectURL(blob);
        setUrl(made);
      })
      .catch(() => {});
    return () => {
      live = false;
      if (made) URL.revokeObjectURL(made);
    };
  }, [documentId, picture.id]);

  return (
    <figure data-testid="MKT-document-picture" className="rounded-lg border bg-background overflow-hidden">
      <div className={cn('bg-muted/40 flex items-center justify-center', ASPECT[picture.shape] || ASPECT.square)}>
        {url
          ? <img src={url} alt={picture.idea} className="h-full w-full object-cover" />
          : <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />}
      </div>
      <figcaption className="p-2 space-y-2">
        <p className="text-xs text-muted-foreground line-clamp-3">{picture.idea}</p>
        <div className="flex gap-2">
          {url ? (
            <Button asChild size="sm" variant="outline" className="h-7 px-2 text-xs">
              <a href={url} download={`picture-${picture.id}.jpg`}>
                <Download className="h-3.5 w-3.5 mr-1" /> Save
              </a>
            </Button>
          ) : null}
          <Button size="sm" variant="ghost" className="h-7 px-2 text-xs text-destructive hover:text-destructive"
            disabled={deleting} onClick={() => onDelete(picture)}>
            {deleting ? <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" /> : <Trash2 className="h-3.5 w-3.5 mr-1" />}
            Delete
          </Button>
        </div>
      </figcaption>
    </figure>
  );
}

export default function DocumentImages({ documentId, content, initialImages }) {
  const { toast } = useToast();
  const ideas = useMemo(() => imageIdeas(content), [content]);
  const [pictures, setPictures] = useState(initialImages || []);
  const [idea, setIdea] = useState(ideas[0] || '');
  const [shape, setShape] = useState('square');
  const [making, setMaking] = useState(false);
  const [deleting, setDeleting] = useState(null);
  const full = pictures.length >= MAX_PICTURES;

  const make = async () => {
    setMaking(true);
    try {
      const res = await marketingAgentService.makeDocumentImage(documentId, idea.trim(), shape);
      if (res?.status === 'success' && res.data) {
        setPictures((now) => [...now, res.data]);
        toast({ title: 'Picture made', description: 'It is kept with this document and goes into its PDF.' });
      } else {
        toast({ title: 'No picture', description: res?.message || 'Please try again.', variant: 'destructive' });
      }
    } catch (e) {
      toast({ title: 'No picture', description: e?.message || 'Please try again.', variant: 'destructive' });
    } finally {
      setMaking(false);
    }
  };

  const remove = async (picture) => {
    setDeleting(picture.id);
    try {
      await marketingAgentService.deleteDocumentImage(documentId, picture.id);
      setPictures((now) => now.filter((p) => p.id !== picture.id));
    } catch (e) {
      toast({ title: 'Not deleted', description: e?.message || 'Please try again.', variant: 'destructive' });
    } finally {
      setDeleting(null);
    }
  };

  return (
    <div data-testid="MKT-document-pictures" className="rounded-xl border bg-card p-6 space-y-4 mt-4">
      <div>
        <h3 className="text-base font-semibold flex items-center gap-2">
          <ImagePlus className="h-4 w-4 text-primary" /> Pictures
        </h3>
        <p className="text-xs text-muted-foreground mt-1">
          Describe a picture to post with these. AI makes it in about ten seconds; it is kept with this document
          and goes into its PDF.
        </p>
      </div>

      {ideas.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-xs font-medium text-muted-foreground">Ideas from the posts:</p>
          <div className="flex flex-wrap gap-2">
            {ideas.map((text) => (
              <button key={text} type="button" onClick={() => setIdea(text)} title={text}
                className={cn('rounded-full border px-3 py-1 text-xs text-left transition-colors hover:bg-primary/10',
                  idea === text ? 'border-primary text-primary' : 'border-border text-muted-foreground')}>
                {text.length > 70 ? `${text.slice(0, 70)}…` : text}
              </button>
            ))}
          </div>
        </div>
      )}

      <Textarea data-testid="MKT-picture-idea" value={idea} onChange={(e) => setIdea(e.target.value)} rows={3}
        maxLength={1000} placeholder="For example: a small team celebrating a product launch in a bright office" />

      <div className="flex flex-wrap items-center gap-2">
        {SHAPES.map(([code, name]) => (
          <Button key={code} size="sm" variant={shape === code ? 'default' : 'outline'} onClick={() => setShape(code)}>
            {name}
          </Button>
        ))}
        <Button data-testid="MKT-make-picture" size="sm" className="ml-auto" onClick={make}
          disabled={making || !idea.trim() || full}>
          {making
            ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Making the picture…</>
            : <><ImagePlus className="h-4 w-4 mr-2" /> Make picture</>}
        </Button>
      </div>
      {full && (
        <p className="text-xs text-amber-500">
          This document has {MAX_PICTURES} pictures, the most it keeps. Delete one to make another.
        </p>
      )}

      {pictures.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3 items-start">
          {pictures.map((p) => (
            <Picture key={p.id} documentId={documentId} picture={p} deleting={deleting === p.id} onDelete={remove} />
          ))}
        </div>
      )}
    </div>
  );
}
