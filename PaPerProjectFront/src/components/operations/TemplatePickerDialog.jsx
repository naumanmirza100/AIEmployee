import React, { useState, useEffect } from 'react';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Check } from 'lucide-react';
import {
  TEMPLATES, AUTHORING_ACCENT, AUTHORING_ACCENT_SOFT, AUTHORING_ACCENT_BORDER,
} from './authoringConstants';

/**
 * TemplatePickerDialog
 * Modal for picking which template the AI should use.
 *
 * Props:
 *   open     boolean
 *   value    string            — currently selected template value
 *   onChange (value) => void   — fires when the user confirms a selection
 *   onOpenChange (open) => void
 */
const TemplatePickerDialog = ({ open, value, onChange, onOpenChange }) => {
  const [selected, setSelected] = useState(value || TEMPLATES[0].value);

  useEffect(() => {
    if (open) setSelected(value || TEMPLATES[0].value);
  }, [open, value]);

  const confirm = () => {
    onChange?.(selected);
    onOpenChange?.(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-[#1a1333] border border-white/10 text-white max-w-2xl">
        <DialogHeader>
          <DialogTitle className="text-white">Select a template</DialogTitle>
          <DialogDescription className="text-white/55">
            Pick the structure that best fits the document you want to create.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-2 max-h-[55vh] overflow-y-auto pr-1">
          {TEMPLATES.map((t) => {
            const Icon = t.icon;
            const active = selected === t.value;
            return (
              <button
                key={t.value}
                type="button"
                onClick={() => setSelected(t.value)}
                className={`relative text-left rounded-xl border px-3 py-3 transition-all ${
                  active
                    ? 'border-amber-500/50 bg-amber-500/10 shadow-[0_0_0_3px_rgba(245,158,11,0.08)]'
                    : 'border-white/10 bg-white/[0.02] hover:bg-white/[0.05] hover:border-white/20'
                }`}
              >
                {active && (
                  <span
                    className="absolute top-2 right-2 h-5 w-5 rounded-full flex items-center justify-center"
                    style={{ backgroundColor: AUTHORING_ACCENT }}
                  >
                    <Check className="h-3 w-3 text-black" />
                  </span>
                )}
                <div className="flex items-center gap-2 mb-1.5">
                  <div
                    className="w-7 h-7 rounded-md flex items-center justify-center"
                    style={{ backgroundColor: active ? AUTHORING_ACCENT_SOFT : 'rgba(255,255,255,0.04)' }}
                  >
                    <Icon className="h-3.5 w-3.5" style={{ color: active ? AUTHORING_ACCENT : 'rgba(255,255,255,0.7)' }} />
                  </div>
                  <span className={`text-sm font-semibold ${active ? 'text-amber-200' : 'text-white/90'}`}>
                    {t.label}
                  </span>
                </div>
                <div className="text-[11px] text-white/55 leading-relaxed pr-5">
                  {t.description}
                </div>
              </button>
            );
          })}
        </div>

        <DialogFooter className="mt-3 gap-2">
          <Button
            variant="outline"
            onClick={() => onOpenChange?.(false)}
            className="border-white/10 bg-transparent text-white/80 hover:bg-white/5"
          >
            Cancel
          </Button>
          <Button
            onClick={confirm}
            className="font-semibold"
            style={{ backgroundColor: AUTHORING_ACCENT, color: '#1a0e00', border: 'none' }}
          >
            Use this template
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default TemplatePickerDialog;
