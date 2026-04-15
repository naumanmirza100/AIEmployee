import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs) {
	return twMerge(clsx(inputs));
}

/** Format a Date as YYYY-MM-DD in local time (for API/inputs). */
export function formatDateLocal(date) {
	if (!date) return '';
	const d = date instanceof Date ? date : new Date(date);
	const year = d.getFullYear();
	const month = String(d.getMonth() + 1).padStart(2, '0');
	const day = String(d.getDate()).padStart(2, '0');
	return `${year}-${month}-${day}`;
}

/** Parse a YYYY-MM-DD string to a Date in local time (for DatePicker). */
export function parseDateLocal(dateString) {
	if (!dateString) return null;
	const str = typeof dateString === 'string' ? dateString : String(dateString);
	const [year, month, day] = str.split('-').map(Number);
	if (Number.isNaN(year) || Number.isNaN(month) || Number.isNaN(day)) return null;
	return new Date(year, month - 1, day);
}