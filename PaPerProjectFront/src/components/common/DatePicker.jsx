import React from 'react';
import { format, isValid, parse } from 'date-fns';
import { Calendar as CalendarIcon, Clock } from 'lucide-react';
import { Calendar } from '@/components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

/**
 * Shared date + datetime pickers used by every PM form.
 *
 * Replaces the bare `<input type="date">` and `<input type="datetime-local">`
 * the project was shipping with — those gave no calendar/clock UI on most
 * browsers and looked inconsistent with the rest of the dashboard.
 *
 * Both components keep the SAME storage format as before
 *   - DatePicker   → value is a YYYY-MM-DD string
 *   - DateTimePicker → value is a YYYY-MM-DDTHH:mm string
 * so they're drop-in replacements for the native inputs and the form submit
 * handlers don't need to change.
 */

const DATE_FMT = 'yyyy-MM-dd';
const DT_FMT = "yyyy-MM-dd'T'HH:mm";

const parseDateOnly = (str) => {
  if (!str) return undefined;
  const d = parse(str, DATE_FMT, new Date());
  return isValid(d) ? d : undefined;
};

const parseDateTime = (str) => {
  if (!str) return undefined;
  const d = parse(str, DT_FMT, new Date());
  return isValid(d) ? d : undefined;
};

const fmtDate = (d) => (d && isValid(d) ? format(d, DATE_FMT) : '');
const fmtDateTime = (d) => (d && isValid(d) ? format(d, DT_FMT) : '');

/**
 * DatePicker — drop-in replacement for `<input type="date">`.
 *
 * Props:
 *   value         string  — current YYYY-MM-DD value (or '' for none)
 *   onChange      (str)   — fires with the new YYYY-MM-DD string (or '' on clear)
 *   minDate       string  — earliest selectable YYYY-MM-DD (e.g. today)
 *   placeholder   string
 *   id            string  — used by <Label htmlFor=> wrappers in the existing forms
 *   className     string
 *   disabled      boolean
 */
export const DatePicker = ({
  value,
  onChange,
  minDate,
  placeholder = 'Pick a date',
  id,
  className,
  disabled,
}) => {
  const selected = parseDateOnly(value);
  const minD = parseDateOnly(minDate);

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          id={id}
          type="button"
          variant="outline"
          disabled={disabled}
          className={cn(
            'w-full justify-start text-left font-normal',
            !value && 'text-muted-foreground',
            className,
          )}
        >
          <CalendarIcon className="mr-2 h-4 w-4 opacity-70" />
          {value
            ? format(selected || new Date(), 'EEE, MMM d, yyyy')
            : <span>{placeholder}</span>}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0 bg-[#1a1333] border border-white/10" align="start">
        <Calendar
          mode="single"
          selected={selected}
          onSelect={(d) => onChange?.(fmtDate(d))}
          disabled={minD ? { before: minD } : undefined}
          initialFocus
        />
      </PopoverContent>
    </Popover>
  );
};

/**
 * DateTimePicker — drop-in replacement for `<input type="datetime-local">`.
 *
 * Calendar for the date, plus a native `<input type="time">` for HH:mm
 * (so we get the browser's time-spinner without bringing in a heavier
 * time-picker dependency).
 *
 * Props:
 *   value      string  — YYYY-MM-DDTHH:mm value (or '' for none)
 *   onChange   (str)   — fires with the new YYYY-MM-DDTHH:mm (or '')
 *   minValue   string  — earliest selectable YYYY-MM-DDTHH:mm
 *   placeholder string
 *   id         string
 *   className  string
 *   disabled   boolean
 */
export const DateTimePicker = ({
  value,
  onChange,
  minValue,
  placeholder = 'Pick a date & time',
  id,
  className,
  disabled,
}) => {
  const selected = parseDateTime(value);
  const minD = parseDateTime(minValue);
  const minDateOnly = minD || undefined;

  // Time portion ("HH:mm") parsed out of the current value so the <input type="time">
  // stays in sync with the picker.
  const timePart = value && value.includes('T') ? value.split('T')[1].slice(0, 5) : '';
  const datePart = value && value.includes('T') ? value.split('T')[0] : '';

  const onDayChosen = (d) => {
    if (!d) {
      onChange?.('');
      return;
    }
    const day = format(d, DATE_FMT);
    const time = timePart || '09:00';
    onChange?.(`${day}T${time}`);
  };

  const onTimeChanged = (newTime) => {
    if (!newTime) {
      // Clearing the time portion shouldn't drop the date.
      if (datePart) onChange?.(`${datePart}T00:00`);
      return;
    }
    const day = datePart || format(new Date(), DATE_FMT);
    onChange?.(`${day}T${newTime}`);
  };

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          id={id}
          type="button"
          variant="outline"
          disabled={disabled}
          className={cn(
            'w-full justify-start text-left font-normal',
            !value && 'text-muted-foreground',
            className,
          )}
        >
          <CalendarIcon className="mr-2 h-4 w-4 opacity-70" />
          {value
            ? format(selected || new Date(), 'EEE, MMM d, yyyy h:mm a')
            : <span>{placeholder}</span>}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0 bg-[#1a1333] border border-white/10" align="start">
        <Calendar
          mode="single"
          selected={selected}
          onSelect={onDayChosen}
          disabled={minDateOnly ? { before: minDateOnly } : undefined}
          initialFocus
        />
        <div className="border-t border-white/10 p-3 flex items-center gap-2">
          <Clock className="h-4 w-4 opacity-60 text-white/65" />
          <input
            type="time"
            value={timePart}
            onChange={(e) => onTimeChanged(e.target.value)}
            className="bg-transparent border border-white/10 rounded px-2 py-1 text-sm text-white focus:outline-none focus:ring-1 focus:ring-amber-500/50 [color-scheme:dark]"
          />
        </div>
      </PopoverContent>
    </Popover>
  );
};

export default DatePicker;
