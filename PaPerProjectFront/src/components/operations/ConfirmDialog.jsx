import React from 'react';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Loader2, AlertTriangle, HelpCircle } from 'lucide-react';

/**
 * ConfirmDialog — reusable confirmation modal (replaces window.confirm)
 *
 * Props:
 *   open         boolean
 *   onOpenChange (open: boolean) => void
 *   title        string
 *   description  string | ReactNode
 *   confirmLabel string                       — default "Confirm"
 *   cancelLabel  string                       — default "Cancel"
 *   variant      'default' | 'danger'         — styling for the confirm button
 *   onConfirm    () => void | Promise<void>
 *   loading      boolean                      — show spinner, disable buttons
 *   icon         ReactNode                    — optional custom icon
 */
const ConfirmDialog = ({
  open,
  onOpenChange,
  title = 'Are you sure?',
  description,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'default',
  onConfirm,
  loading = false,
  icon,
}) => {
  const isDanger = variant === 'danger';

  const DefaultIcon = isDanger ? AlertTriangle : HelpCircle;
  const iconTint = isDanger ? '#f87171' : '#f59e0b';
  const iconBg = isDanger ? 'rgba(248,113,113,0.12)' : 'rgba(245,158,11,0.12)';
  const iconBorder = isDanger ? 'rgba(248,113,113,0.28)' : 'rgba(245,158,11,0.28)';

  const confirmStyles = isDanger
    ? { backgroundColor: '#dc2626', color: '#fff', border: 'none' }
    : { backgroundColor: '#f59e0b', color: '#1a0e00', border: 'none' };

  const handleConfirm = async () => {
    if (loading) return;
    await onConfirm?.();
  };

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!loading) onOpenChange?.(next); }}>
      <DialogContent className="bg-[#1a1333] border border-white/10 text-white max-w-md">
        <DialogHeader>
          <div className="flex items-start gap-3">
            <div
              className="flex items-center justify-center w-10 h-10 rounded-xl shrink-0"
              style={{ backgroundColor: iconBg, border: `1px solid ${iconBorder}` }}
            >
              {icon || <DefaultIcon className="h-5 w-5" style={{ color: iconTint }} />}
            </div>
            <div className="flex-1 min-w-0">
              <DialogTitle className="text-white text-base">{title}</DialogTitle>
              {description && (
                <DialogDescription className="text-white/60 mt-1 text-sm leading-relaxed">
                  {description}
                </DialogDescription>
              )}
            </div>
          </div>
        </DialogHeader>

        <DialogFooter className="gap-2 mt-2">
          <Button
            variant="outline"
            onClick={() => onOpenChange?.(false)}
            disabled={loading}
            className="border-white/10 bg-transparent text-white/80 hover:bg-white/5"
          >
            {cancelLabel}
          </Button>
          <Button
            onClick={handleConfirm}
            disabled={loading}
            className="font-semibold"
            style={confirmStyles}
          >
            {loading ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" />
                Working...
              </>
            ) : (
              confirmLabel
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default ConfirmDialog;
