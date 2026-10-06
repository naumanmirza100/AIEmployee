import { useCallback, useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useToast } from '@/components/ui/use-toast';
import { companyApi } from '@/services/companyAuthService';

const day = (iso) => new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, {
  day: 'numeric', month: 'short', year: 'numeric',
});

const when = (entry) => {
  if (entry.on) {
    return entry.until && entry.until !== entry.on ? `${day(entry.on)} to ${day(entry.until)}` : day(entry.on);
  }
  if (entry.starts_at) {
    return new Date(entry.starts_at).toLocaleString(undefined, {
      day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit',
    });
  }
  return '';
};

// The server says how each entry is removed (core/leftovers.py); this only sends it.
const send = ({ method, path, body }) => {
  const verb = method.toLowerCase();
  return verb === 'delete' ? companyApi.delete(path) : companyApi[verb](path, body);
};

/**
 * What an agent the company no longer has still holds for everyone else:
 * approved leave, holidays, meetings, interviews, running campaigns. Its own
 * screens are locked, so this is the one place left to remove a wrong entry.
 * Shows nothing when there is nothing left.
 */
const LapsedLeftovers = ({ moduleKey }) => {
  const { toast } = useToast();
  const [found, setFound] = useState(null);
  const [asking, setAsking] = useState(null);   // the entry waiting for "are you sure"
  const [busy, setBusy] = useState(null);

  const load = useCallback(async () => {
    try {
      const response = await companyApi.get(`/modules/${moduleKey}/leftovers`);
      setFound(response?.status === 'success' ? response : null);
    } catch {
      setFound(null);   // the lock screen works without the list
    }
  }, [moduleKey]);

  useEffect(() => { load(); }, [load]);

  const remove = async (entry, key) => {
    setBusy(key);
    try {
      await send(entry.call);
      toast({ title: 'Removed', description: `${entry.label}: ${entry.title}` });
    } catch (error) {
      toast({
        title: 'Not removed',
        description: error?.data?.message || error?.message || 'Please try again.',
        variant: 'destructive',
      });
    } finally {
      setBusy(null);
      setAsking(null);
      load();
    }
  };

  const items = found?.items || [];
  const hidden = (found?.others || 0) + (found?.more || 0);
  if (!items.length && !hidden) return null;

  return (
    <div className="border-t border-border pt-4 text-left" data-testid="lapsed-leftovers">
      <h3 className="text-sm font-semibold text-foreground">Still in place</h3>
      {found.note && <p className="mt-1 text-xs text-muted-foreground">{found.note}</p>}
      <ul className="mt-3 space-y-2">
        {items.map((entry) => {
          const key = `${entry.kind}-${entry.id}`;
          return (
            <li key={key} className="rounded-md border border-border p-3" data-entry={key}>
              <p className="text-sm text-foreground break-words">
                <span className="font-medium">{entry.label}:</span> {entry.title}
              </p>
              {when(entry) && <p className="text-xs text-muted-foreground">{when(entry)}</p>}
              <div className="mt-2 flex flex-wrap gap-2">
                {asking === key ? (
                  <>
                    <Button size="sm" variant="destructive" disabled={busy === key} onClick={() => remove(entry, key)}>
                      {busy === key && <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />}
                      Yes, {entry.button.toLowerCase()}
                    </Button>
                    <Button size="sm" variant="outline" disabled={busy === key} onClick={() => setAsking(null)}>
                      Keep it
                    </Button>
                  </>
                ) : (
                  <Button size="sm" variant="outline" onClick={() => setAsking(key)}>{entry.button}</Button>
                )}
              </div>
            </li>
          );
        })}
      </ul>
      {found.others > 0 && (
        <p className="mt-3 text-xs text-muted-foreground" data-testid="lapsed-others">
          {found.others} more {found.others === 1 ? 'belongs' : 'belong'} to other people, who can remove
          {found.others === 1 ? ' it' : ' them'} from this screen.
        </p>
      )}
      {found.more > 0 && (
        <p className="mt-3 text-xs text-muted-foreground">And {found.more} more, shown as these are removed.</p>
      )}
    </div>
  );
};

export default LapsedLeftovers;
