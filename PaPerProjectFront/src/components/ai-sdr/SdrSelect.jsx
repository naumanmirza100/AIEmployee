import React from 'react';
import * as SelectPrimitive from '@radix-ui/react-select';
import { Check, ChevronDown } from 'lucide-react';

// The AI SDR screens' dropdown, in place of the browser's own <select>: its open list was drawn by Windows (a
// washed-out mauve list with a grey highlight that no stylesheet reaches). Same props as a controlled <select>
// boiled down: `value`, `onChange(value)` with the value as a string, and `options` [{ value, label, disabled }].
// `style` styles the closed box, so a screen passes the same input style its text boxes use.
//
// Radix refuses an item whose value is '', and '' is how these screens say "none" or "the default", so it is
// swapped for a stand-in on the way in and back on the way out.
const EMPTY = '__sdr_empty__';
const toRadix = (v) => (v === '' || v === null || v === undefined ? EMPTY : String(v));
const fromRadix = (v) => (v === EMPTY ? '' : v);

const SdrSelect = ({ value, onChange, options, style, placeholder, disabled, title, ...rest }) => {
  const current = toRadix(value);
  const known = options.some(o => toRadix(o.value) === current);
  return (
    <SelectPrimitive.Root value={known ? current : undefined} onValueChange={v => onChange(fromRadix(v))}
      disabled={disabled}>
      <SelectPrimitive.Trigger title={title} {...rest}
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, cursor: 'pointer',
          textAlign: 'left', ...style,
        }}>
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0 }}>
          <SelectPrimitive.Value placeholder={<span style={{ color: '#6b7280' }}>{placeholder || 'Choose…'}</span>} />
        </span>
        <SelectPrimitive.Icon asChild>
          <ChevronDown size={15} style={{ flexShrink: 0, color: '#9ca3af' }} />
        </SelectPrimitive.Icon>
      </SelectPrimitive.Trigger>
      <SelectPrimitive.Portal>
        <SelectPrimitive.Content position="popper" sideOffset={4}
          style={{
            zIndex: 100, minWidth: 'var(--radix-select-trigger-width)', maxHeight: 'min(320px, var(--radix-select-content-available-height))',
            overflow: 'hidden', borderRadius: 10, border: '1px solid var(--line-1)',
            background: 'var(--sfc-14082a, #160d26)', color: 'var(--text-soft)',
            boxShadow: '0 12px 32px rgba(0,0,0,0.45)',
          }}>
          <SelectPrimitive.Viewport style={{ padding: 4 }}>
            {options.map(o => (
              <SelectPrimitive.Item key={toRadix(o.value)} value={toRadix(o.value)} disabled={o.disabled}
                className="sdr-select-item"
                style={{
                  position: 'relative', display: 'flex', alignItems: 'center', gap: 8, padding: '7px 10px 7px 28px',
                  borderRadius: 7, fontSize: 13, cursor: o.disabled ? 'default' : 'pointer', outline: 'none',
                  userSelect: 'none', color: o.disabled ? '#6b7280' : undefined,
                }}>
                <span style={{ position: 'absolute', left: 8, display: 'flex' }}>
                  <SelectPrimitive.ItemIndicator><Check size={13} color="#c084fc" /></SelectPrimitive.ItemIndicator>
                </span>
                <SelectPrimitive.ItemText>{o.label}</SelectPrimitive.ItemText>
              </SelectPrimitive.Item>
            ))}
          </SelectPrimitive.Viewport>
        </SelectPrimitive.Content>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  );
};

export default SdrSelect;
