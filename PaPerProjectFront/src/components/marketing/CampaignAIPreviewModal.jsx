// Post-"Generate with AI" preview + edit modal for a drafted campaign.
//
// Two modes inside one wide dialog:
//   • Preview — an attractive, read-only summary of what the AI generated.
//   • Edit    — the same fields as editable inputs, right inside the modal.
//
// It edits the SAME state the parent's inline form uses (values in, setters
// in), so anything changed here is instantly reflected in the page's inline
// form too, and vice-versa — nothing gets out of sync. The page keeps its own
// inline editing section; this modal is an additional, optional surface.

import React from 'react';
import {
  Dialog, DialogContent, DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { DatePicker } from '@/components/ui/date-picker';
import { parseDateLocal, formatDateLocal } from '@/lib/utils';
import { Sparkles, CheckCircle, Loader2, Pencil, Eye, RefreshCw } from 'lucide-react';

export const CampaignAIPreviewModal = ({
  open,
  onOpenChange,
  mode,            // 'preview' | 'edit'
  onModeChange,    // (mode) => void
  onCreate,        // () => void
  creating = false,
  onRegenerate,    // () => void — from preview: switch to edit mode
  onRegenerateAI,  // () => void — from edit: re-run the AI draft
  regenerating = false,
  instructions = '',       // free-text steer for the AI on regenerate
  setInstructions,
  // Shared campaign state (values + setters) — same ones the inline form uses.
  name, setName,
  description, setDescription,
  targetLeads, setTargetLeads,
  targetConversions, setTargetConversions,
  ageRange, setAgeRange,
  location, setLocation,
  industry, setIndustry,
  companySize, setCompanySize,
  interests, setInterests,
  language, setLanguage,
  startDate, setStartDate,
  endDate, setEndDate,
}) => {
  const isEdit = mode === 'edit';

  const audienceChips = [
    ageRange && `Age: ${ageRange}`,
    location && `Location: ${location}`,
    industry && `Industry: ${industry}`,
    companySize && companySize !== '__any__' && `Company size: ${companySize}`,
    interests && `Interests: ${interests}`,
    language && `Language: ${language}`,
  ].filter(Boolean);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {/* [&>button] targets the built-in close ✕ — drop its border and make it
          white so it sits cleanly in the top-right corner over the gradient. */}
      <DialogContent className="sm:max-w-3xl p-0 overflow-hidden [&>button]:border-0 [&>button]:text-white/80  [&>button]:right-1 [&>button]:top-1">
        {/* Gradient header — pr-12 keeps the Preview/Edit toggle clear of the
            dialog's own close ✕ in the top-right corner. */}
        <div className="px-6 py-5 pr-12 bg-gradient-to-r from-violet-600/90 to-fuchsia-600/90 text-white">
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-white/80">
                <Sparkles className="h-4 w-4" />
                AI-generated campaign
              </div>
              <h3 className="mt-1 text-xl font-bold leading-tight truncate">{name || 'Untitled campaign'}</h3>
            </div>
            {/* Preview ⇄ Edit toggle */}
            <div className="inline-flex rounded-lg bg-white/15 p-0.5 text-xs font-medium shrink-0">
              <button
                type="button"
                onClick={() => onModeChange('preview')}
                className={`px-3 py-1.5 rounded-md flex items-center gap-1.5 transition ${!isEdit ? 'bg-white text-violet-700' : 'text-white/90 hover:bg-white/10'}`}
              >
                <Eye className="h-3.5 w-3.5" /> Preview
              </button>
              <button
                type="button"
                onClick={() => onModeChange('edit')}
                className={`px-3 py-1.5 rounded-md flex items-center gap-1.5 transition ${isEdit ? 'bg-white text-violet-700' : 'text-white/90 hover:bg-white/10'}`}
              >
                <Pencil className="h-3.5 w-3.5" /> Edit
              </button>
            </div>
          </div>
        </div>

        <div className="px-6 py-5 max-h-[60vh] overflow-y-auto no-scrollbar">
          {isEdit ? (
            /* ── EDIT MODE — editable fields ─────────────────────────────── */
            <div className="space-y-4">
              
              {/* Regenerate box — tell the AI what to change, then regenerate. */}
              {onRegenerateAI && (
                <div className="rounded-lg border border-fuchsia-400/30 bg-fuchsia-500/5 p-3 space-y-2">
                  <Label className="text-xs flex items-center gap-1.5 text-fuchsia-300">
                    <Sparkles className="h-3.5 w-3.5" />
                    Regenerate with AI
                  </Label>
                  <Textarea
                    value={instructions}
                    onChange={(e) => setInstructions && setInstructions(e.target.value)}
                    rows={2}
                    placeholder="Optional: tell the AI what to change — e.g. “focus on Pakistan finance sector, aim for more leads, target 30-50 age”."
                    className="text-sm"
                  />
                  <div className="flex justify-end">
                    <Button
                      type="button"
                      onClick={onRegenerateAI}
                      disabled={regenerating}
                      className="gap-1.5 bg-fuchsia-600 hover:bg-fuchsia-700 text-white border-0"
                    >
                      {regenerating ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                      {regenerating ? 'Regenerating…' : 'Regenerate with AI'}
                    </Button>
                  </div>
                </div>
              )}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-1 sm:col-span-2">
                  <Label className="text-xs">Campaign name</Label>
                  <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Campaign name" />
                </div>
                <div className="space-y-1 sm:col-span-2">
                  <Label className="text-xs">Description</Label>
                  <Textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2} placeholder="Short description" />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Target leads</Label>
                  <Input type="number" min="0" value={targetLeads} onChange={(e) => setTargetLeads(e.target.value)} />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Target conversions</Label>
                  <Input type="number" min="0" value={targetConversions} onChange={(e) => setTargetConversions(e.target.value)} />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Age range</Label>
                  <Input value={ageRange} onChange={(e) => setAgeRange(e.target.value)} placeholder="e.g. 25-45" />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Location</Label>
                  <Input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="e.g. United States" />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Industry</Label>
                  <Input value={industry} onChange={(e) => setIndustry(e.target.value)} placeholder="e.g. SaaS" />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Company size</Label>
                  <Input
                    value={companySize === '__any__' ? '' : companySize}
                    onChange={(e) => setCompanySize(e.target.value || '__any__')}
                    placeholder="e.g. 11-50"
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Interests</Label>
                  <Input value={interests} onChange={(e) => setInterests(e.target.value)} placeholder="e.g. automation, AI" />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">Language</Label>
                  <Input value={language} onChange={(e) => setLanguage(e.target.value)} placeholder="e.g. English" />
                </div>
                {/* Campaign schedule */}
                {setStartDate && (
                  <div className="space-y-1">
                    <Label className="text-xs">Start date</Label>
                    <DatePicker
                      date={startDate ? parseDateLocal(startDate) : undefined}
                      setDate={(d) => setStartDate(d ? formatDateLocal(d) : '')}
                      placeholder="Select start date"
                    />
                  </div>
                )}
                {setEndDate && (
                  <div className="space-y-1">
                    <Label className="text-xs">End date</Label>
                    <DatePicker
                      date={endDate ? parseDateLocal(endDate) : undefined}
                      setDate={(d) => setEndDate(d ? formatDateLocal(d) : '')}
                      placeholder="Select end date"
                    />
                  </div>
                )}
              </div>
              <p className="text-[11px] text-muted-foreground">
                Changes here also update the form on the page.
              </p>

            </div>
          ) : (
            /* ── PREVIEW MODE — read-only summary ────────────────────────── */
            <div className="space-y-4">
              {description && <p className="text-sm text-muted-foreground">{description}</p>}

              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-lg border bg-muted/40 p-3">
                  <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Target leads</div>
                  <div className="text-lg font-bold">{targetLeads || '—'}</div>
                </div>
                <div className="rounded-lg border bg-muted/40 p-3">
                  <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Target conversions</div>
                  <div className="text-lg font-bold">{targetConversions || '—'}</div>
                </div>
              </div>

              <div>
                <div className="text-xs font-semibold text-muted-foreground mb-2">Target audience</div>
                <div className="flex flex-wrap gap-2">
                  {audienceChips.length > 0 ? (
                    audienceChips.map((chip, i) => (
                      <span key={i} className="inline-flex items-center rounded-full border border-violet-400/30 bg-violet-500/10 px-3 py-1 text-xs text-violet-300">
                        {chip}
                      </span>
                    ))
                  ) : (
                    <span className="text-xs text-muted-foreground">No specific audience — broad targeting.</span>
                  )}
                </div>
              </div>

              {(startDate || endDate) && (
                <div className="text-xs text-muted-foreground">
                  <span className="font-semibold text-foreground">Runs:</span>{' '}
                  {startDate || '—'} → {endDate || '—'}
                </div>
              )}
            </div>
          )}
        </div>

        <DialogFooter className="px-6 py-4 border-t flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          {/* Left (preview only): jump into edit mode to tweak + regenerate.
              In edit mode the "Regenerate with AI" button lives inline above. */}
          <div className="sm:mr-auto">
            {!isEdit && onRegenerate && (
              <Button
                onClick={onRegenerate}
                disabled={creating}
                className="gap-1.5 bg-fuchsia-600 hover:bg-fuchsia-700 text-white border-0"
                title="Edit the details here, then regenerate"
              >
                <RefreshCw className="h-4 w-4 mr-2" />
                Regenerate
              </Button>
            )}
          </div>
          {/* Right: edit/preview toggle + create. */}
          <div className="flex gap-2">
            {isEdit ? (
              <Button variant="outline" onClick={() => onModeChange('preview')}>
                <Eye className="h-4 w-4 mr-2" /> Back to preview
              </Button>
            ) : (
              <Button variant="outline" onClick={() => onModeChange('edit')}>
                <Pencil className="h-4 w-4 mr-2" /> Edit details
              </Button>
            )}
            <Button
              onClick={onCreate}
              disabled={creating || regenerating}
              className="bg-violet-600 hover:bg-violet-700 text-white border-0"
            >
              {creating ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <CheckCircle className="h-4 w-4 mr-2" />}
              Create campaign
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default CampaignAIPreviewModal;
