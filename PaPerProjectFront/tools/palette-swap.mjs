// Bulk palette-swap helper: maps off-palette Tailwind tokens used in the
// HR and PM dashboards to the Operations Agent palette (amber / violet /
// emerald / rose + translucent white surfaces).
//
// Mappings are ordered most-specific-first so things like `bg-gray-900/50`
// match before the bare `bg-gray-900` rule. Each rule replaces ALL exact
// matches inside the target files.
//
// Run from PaPerProjectFront/:
//   node tools/palette-swap.mjs
//
// Targets are passed on the command line:
//   node tools/palette-swap.mjs src/components/hr src/components/pm-agent
import { readdir, readFile, writeFile, stat } from 'node:fs/promises';
import { join, extname } from 'node:path';

const SWAPS = [
  // ─── Gray neutrals → translucent white surfaces ───
  ['bg-gray-900/50',  'bg-black/30'],
  ['bg-gray-900',     'bg-black/30'],
  ['bg-gray-800/60',  'bg-white/[0.03]'],
  ['bg-gray-800',     'bg-white/[0.02]'],
  ['bg-gray-700',     'bg-white/[0.05]'],
  ['bg-slate-800/70', 'bg-black/30'],

  ['border-gray-700/50', 'border-white/[0.04]'],
  ['border-gray-700',    'border-white/[0.06]'],
  ['border-gray-600',    'border-white/[0.08]'],

  ['text-gray-600', 'text-white/35'],
  ['text-gray-500', 'text-white/40'],
  ['text-gray-400', 'text-white/55'],
  ['text-gray-300', 'text-white/65'],
  ['text-gray-200', 'text-white/80'],
  ['text-gray-100', 'text-white/90'],

  // ─── Yellow / orange → amber (ops primary) ───
  ['text-yellow-700', 'text-amber-700'],
  ['text-yellow-600', 'text-amber-600'],
  ['text-yellow-400', 'text-amber-400'],
  ['text-yellow-300', 'text-amber-300'],
  ['bg-yellow-900/30', 'bg-amber-900/30'],
  ['bg-yellow-500/20', 'bg-amber-500/20'],
  ['bg-yellow-500/10', 'bg-amber-500/10'],
  ['border-yellow-700',   'border-amber-700'],
  ['border-yellow-500/30','border-amber-500/30'],

  ['text-orange-400',     'text-amber-400'],
  ['text-orange-300',     'text-amber-300'],
  ['bg-orange-500/15',    'bg-amber-500/15'],
  ['bg-orange-500/10',    'bg-amber-500/10'],
  ['border-orange-500/30','border-amber-500/30'],

  // ─── Green / lime → emerald (ops success) ───
  ['text-green-600', 'text-emerald-600'],
  ['text-green-400', 'text-emerald-400'],
  ['text-green-300', 'text-emerald-300'],
  ['bg-green-500',   'bg-emerald-500'],
  ['bg-green-500/15','bg-emerald-500/15'],
  ['bg-green-500/10','bg-emerald-500/10'],
  ['border-green-500/30','border-emerald-500/30'],
  ['border-green-200',   'border-emerald-200/40'],

  // ─── Blue / sky / cyan → violet (ops secondary) ───
  ['text-blue-400',    'text-violet-400'],
  ['text-blue-300',    'text-violet-300'],
  ['bg-blue-500/15',   'bg-violet-500/15'],
  ['bg-blue-500/10',   'bg-violet-500/10'],
  ['border-blue-500/30','border-violet-500/30'],

  ['text-sky-400',     'text-violet-400'],
  ['text-sky-300/80',  'text-violet-300/80'],
  ['text-sky-300',     'text-violet-300'],
  ['text-sky-200',     'text-violet-200'],
  ['bg-sky-500/15',    'bg-violet-500/15'],
  ['bg-sky-500/10',    'bg-violet-500/10'],
  ['bg-sky-400',       'bg-violet-400'],
  ['border-sky-400/30','border-violet-400/30'],

  ['text-cyan-400',    'text-violet-400'],
  ['bg-cyan-500/15',   'bg-violet-500/15'],

  // ─── Slate → translucent white (matches ops surface) ───
  ['text-slate-300',    'text-white/65'],
  ['text-slate-400',    'text-white/55'],
  ['bg-slate-500/15',   'bg-white/[0.05]'],
  ['bg-slate-500/10',   'bg-white/[0.03]'],
  ['bg-slate-400',      'bg-white/40'],
  ['border-slate-400/30','border-white/[0.08]'],

  // ─── Pink / fuchsia / indigo → amber/violet ───
  ['text-pink-400',     'text-amber-400'],
  ['bg-pink-500/15',    'bg-amber-500/15'],
  ['text-indigo-400',   'text-violet-400'],

  // ─── Round 2: stragglers (numeric variants not covered above) ───
  // Solid yellows / oranges / gray-500
  ['bg-yellow-600/20', 'bg-amber-600/20'],
  ['bg-yellow-500/15', 'bg-amber-500/15'],
  ['bg-yellow-500',    'bg-amber-500'],
  ['bg-yellow-900/50', 'bg-amber-900/50'],
  ['bg-yellow-900/20', 'bg-amber-900/20'],
  ['border-yellow-600/50', 'border-amber-600/50'],
  ['border-yellow-600',    'border-amber-600'],
  ['border-yellow-200',    'border-amber-200/40'],

  ['bg-orange-900/30',  'bg-amber-900/30'],
  ['border-orange-700', 'border-amber-700'],

  ['bg-gray-500/20',  'bg-white/[0.05]'],

  // Solid blues across the spectrum → violet variants
  ['text-blue-800',   'text-violet-800'],
  ['text-blue-600',   'text-violet-600'],
  ['text-blue-200',   'text-violet-200'],
  ['text-blue-100',   'text-violet-100'],
  ['bg-blue-950',     'bg-violet-950'],
  ['bg-blue-900/30',  'bg-violet-900/30'],
  ['bg-blue-800/80',  'bg-violet-800/80'],
  ['bg-blue-700',     'bg-violet-700'],
  ['bg-blue-600/20',  'bg-violet-600/20'],
  ['bg-blue-600',     'bg-violet-600'],
  ['bg-blue-500/20',  'bg-violet-500/20'],
  ['bg-blue-500',     'bg-violet-500'],
  ['bg-blue-50',      'bg-violet-50'],
  ['border-blue-800', 'border-violet-800'],
  ['border-blue-700', 'border-violet-700'],
  ['border-blue-600', 'border-violet-600'],
  ['border-blue-200', 'border-violet-200/40'],

  // Solid greens → emerald
  ['text-green-800',  'text-emerald-800'],
  ['text-green-700',  'text-emerald-700'],
  ['text-green-200',  'text-emerald-200'],
  ['bg-green-950/50', 'bg-emerald-950/50'],
  ['bg-green-950',    'bg-emerald-950'],
  ['bg-green-900/30', 'bg-emerald-900/30'],
  ['bg-green-900/10', 'bg-emerald-900/10'],
  ['bg-green-700',    'bg-emerald-700'],
  ['bg-green-600',    'bg-emerald-600'],
  ['bg-green-50',     'bg-emerald-50'],
  ['border-green-900/30', 'border-emerald-900/30'],
  ['border-green-800',    'border-emerald-800'],
  ['border-green-700',    'border-emerald-700'],
  ['border-green-500/20', 'border-emerald-500/20'],

  // Remaining slate / purple
  ['text-slate-200',     'text-white/80'],
  ['text-slate-100',     'text-white/85'],
  ['bg-slate-700',       'bg-white/[0.05]'],
  ['bg-slate-600',       'bg-white/[0.07]'],

  ['text-purple-400',    'text-violet-400'],
  ['text-purple-300',    'text-violet-300'],
  ['text-purple-200',    'text-violet-200'],
  ['bg-purple-500',      'bg-violet-500'],
  ['border-purple-500/30','border-violet-500/30'],

  // ─── Tab active-state inline style: purple gradient → amber gradient ───
  // This is the most visible difference from Operations on the agent
  // dashboards: PM / HR / Frontline tab lists pop purple when active,
  // Operations pops amber. Swap the exact strings used in TabsTrigger
  // style props so each agent picks up the ops amber gradient.
  ['linear-gradient(90deg, #a259ff 0%, #7c3aed 100%)',
   'linear-gradient(90deg, #f59e0b 0%, #f97316 100%)'],
  ["border: '1.5px solid #a259ff'",
   "border: '1.5px solid #f59e0b'"],
  ['border: "1.5px solid #a259ff"',
   'border: "1.5px solid #f59e0b"'],
  ['#a259ff55', '#f59e0b55'],
];

const EXTS = new Set(['.jsx', '.js', '.tsx', '.ts']);

async function walk(dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  const files = [];
  for (const e of entries) {
    const p = join(dir, e.name);
    if (e.isDirectory()) {
      files.push(...await walk(p));
    } else if (EXTS.has(extname(e.name))) {
      files.push(p);
    }
  }
  return files;
}

async function processFile(path) {
  const orig = await readFile(path, 'utf8');
  let out = orig;
  for (const [from, to] of SWAPS) {
    if (out.includes(from)) {
      out = out.split(from).join(to);
    }
  }
  if (out !== orig) {
    await writeFile(path, out, 'utf8');
    return true;
  }
  return false;
}

async function main() {
  const targets = process.argv.slice(2);
  if (!targets.length) {
    console.error('Usage: node palette-swap.mjs <dir1> [dir2 ...] | <file1> ...');
    process.exit(1);
  }
  let touchedCount = 0;
  let scannedCount = 0;
  for (const t of targets) {
    const s = await stat(t);
    const files = s.isDirectory() ? await walk(t) : [t];
    for (const f of files) {
      scannedCount++;
      const changed = await processFile(f);
      if (changed) {
        touchedCount++;
        console.log(`  updated  ${f}`);
      }
    }
  }
  console.log(`\nDone. ${touchedCount} of ${scannedCount} files updated.`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
