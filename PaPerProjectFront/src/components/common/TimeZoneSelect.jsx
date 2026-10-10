import React, { useMemo } from 'react';
import { timeZones } from '@/utils/timeZones';

/**
 * Pick a time zone from the list of real ones.
 *
 * `emptyLabel`, when given, adds a first choice with an empty value: on an HR
 * record that means "the company's".
 */
export default function TimeZoneSelect({ value, onChange, emptyLabel, id, disabled, className = '' }) {
  const names = useMemo(() => timeZones([value]), [value]);
  return (
    <select
      id={id}
      value={value || ''}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
      className={`h-10 w-full rounded-md border border-white/10 bg-black/40 px-3 text-sm text-white
        focus:outline-none focus:ring-2 focus:ring-violet-500/40 disabled:opacity-50 ${className}`}
    >
      {emptyLabel !== undefined && <option value="">{emptyLabel}</option>}
      {names.map((name) => <option key={name} value={name}>{name}</option>)}
    </select>
  );
}
