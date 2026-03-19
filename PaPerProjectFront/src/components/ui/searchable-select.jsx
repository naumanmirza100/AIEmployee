import React, { useState, useRef, useEffect } from 'react';
import { ChevronDown, Search, Check } from 'lucide-react';
import { Popover, PopoverTrigger, PopoverContent } from '@/components/ui/popover';
import { cn } from '@/lib/utils';

/**
 * SearchableSelect
 * Props:
 *   value        - current value (string)
 *   onValueChange - (value) => void
 *   options       - [{ value, label }]
 *   placeholder   - string shown when nothing selected
 *   triggerClassName - extra classes for the trigger button
 *   displayLength - max chars to show in trigger before truncating (default 18)
 */
const SearchableSelect = ({
  value,
  onValueChange,
  options = [],
  placeholder = 'Select...',
  triggerClassName,
  displayLength = 18,
}) => {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const inputRef = useRef(null);

  const selectedLabel = options.find(o => o.value === value)?.label || '';
  const displayLabel = selectedLabel
    ? (selectedLabel.length > displayLength ? selectedLabel.slice(0, displayLength) + '…' : selectedLabel)
    : placeholder;

  const filtered = options.filter(o =>
    o.label.toLowerCase().includes(search.toLowerCase())
  );

  useEffect(() => {
    if (open) {
      setSearch('');
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          className={cn(
            'flex h-10 items-center justify-between rounded-md border border-white/20 bg-transparent px-3 py-2 text-sm text-white/80 hover:bg-white/5 focus:outline-none',
            triggerClassName
          )}
        >
          <span className="truncate text-left">{displayLabel}</span>
          <ChevronDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        className="w-[240px] p-0 border border-white/15 bg-[#0f0c1a] text-white shadow-xl"
      >
        {/* Search input */}
        <div className="flex items-center border-b border-white/10 px-3 py-2 gap-2">
          <Search className="h-3.5 w-3.5 shrink-0 text-white/40" />
          <input
            ref={inputRef}
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search..."
            className="flex-1 bg-transparent text-sm text-white placeholder:text-white/30 outline-none"
          />
        </div>
        {/* Options list */}
        <div className="max-h-[220px] overflow-y-auto py-1 custom-sidebar-scroll">
          {filtered.length === 0 ? (
            <p className="py-3 text-center text-xs text-white/40">No results</p>
          ) : (
            filtered.map(opt => (
              <button
                key={opt.value}
                onClick={() => { onValueChange(opt.value); setOpen(false); }}
                className="flex w-full items-center gap-2 px-3 py-2 text-sm text-white/80 hover:bg-white/10 text-left"
              >
                <Check className={cn('h-3.5 w-3.5 shrink-0', value === opt.value ? 'opacity-100 text-violet-400' : 'opacity-0')} />
                <span>{opt.label}</span>
              </button>
            ))
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
};

export default SearchableSelect;
