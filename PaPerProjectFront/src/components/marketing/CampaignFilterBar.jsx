// Reusable search + status + date filter row for campaign lists. Used by both
// the Campaigns tab and the dashboard "Your Campaigns" table so they filter
// identically. Purely presentational — the parent owns the filter state and
// re-fetches (server-side) when a value changes.

import React from 'react';
import { format } from 'date-fns';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { Calendar } from '@/components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Search, X, Calendar as CalendarIcon, Loader2 } from 'lucide-react';

export const CAMPAIGN_STATUS_OPTIONS = [
  { value: 'draft', label: 'Draft' },
  { value: 'scheduled', label: 'Scheduled' },
  { value: 'active', label: 'Active' },
  { value: 'paused', label: 'Paused' },
  { value: 'completed', label: 'Completed' },
  { value: 'cancelled', label: 'Cancelled' },
];

export const CampaignFilterBar = ({
  search, onSearchChange,
  status, onStatusChange,
  date, onDateChange,
  onClear,
  loading = false,
  className = '',
  dataTour,
}) => {
  const [dateOpen, setDateOpen] = React.useState(false);
  const selectedDate = date ? new Date(date + 'T00:00:00') : null;
  const active = !!(search || status || date);

  const pickDate = (d) => {
    setDateOpen(false);
    if (!d) { onDateChange(''); return; }
    const pad = (n) => String(n).padStart(2, '0');
    onDateChange(`${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`);
  };

  return (
    <div data-tour-mkt={dataTour} className={`flex flex-wrap items-center gap-2 ${className}`}>
      <div className="relative flex-1 min-w-[180px]">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
        <Input
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Search campaigns…"
          className="h-9 pl-8 pr-8"
        />
        {loading ? (
          <Loader2 className="absolute right-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 animate-spin text-muted-foreground" />
        ) : search ? (
          <button
            type="button"
            onClick={() => onSearchChange('')}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        ) : null}
      </div>

      <Select value={status || 'all'} onValueChange={(v) => onStatusChange(v === 'all' ? '' : v)}>
        <SelectTrigger className="h-9 w-auto min-w-[140px]">
          <SelectValue placeholder="All statuses" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All statuses</SelectItem>
          {CAMPAIGN_STATUS_OPTIONS.map((o) => (
            <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
          ))}
        </SelectContent>
      </Select>

      <div className="relative">
        <Popover open={dateOpen} onOpenChange={setDateOpen}>
          <PopoverTrigger asChild>
            <Button variant="outline" size="sm" className={`h-9 justify-start font-normal ${date ? 'pr-7' : 'text-muted-foreground'}`}>
              <CalendarIcon className="mr-2 h-3.5 w-3.5" />
              {selectedDate && !isNaN(selectedDate) ? format(selectedDate, 'dd MMM yyyy') : 'Start date'}
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-auto p-0" align="start">
            <Calendar
              mode="single"
              selected={selectedDate && !isNaN(selectedDate) ? selectedDate : undefined}
              onSelect={pickDate}
              initialFocus
            />
          </PopoverContent>
        </Popover>
        {date && (
          <button
            type="button"
            onClick={() => onDateChange('')}
            title="Clear date"
            className="absolute right-1.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {active && onClear && (
        <Button variant="ghost" size="sm" onClick={onClear} className="h-9 px-2.5 gap-1 text-muted-foreground">
          <X className="h-3.5 w-3.5" /> Clear
        </Button>
      )}
    </div>
  );
};

export default CampaignFilterBar;
