/* =========================================================
   icons.js — single source of truth for glyph characters used
   by JS-rendered UI (file tree, debt view, bookkeeping cards,
   wizard status, …).

   Design intent (Lane B Task #7):
   - Keep icon choices discoverable in ONE file so swapping the
     visual language is a single-file edit, not a grep safari.
   - HTML templates keep their literal characters inline — they
     change rarely, and abstracting them yields little benefit.
     This file only governs JS render paths.

   Categories:
   - Structural glyphs for file types shown in the left tree
   - Action glyphs for buttons rendered in JS (currently none,
     but reserved so future additions stay consistent)
   - Status glyphs for loading / success / failure markers
   ========================================================= */

export const ICONS = {
  // ---- brand / identity ----
  brand:    '◐',

  // ---- nav / project switcher ----
  project:  '◎',   // active project / switcher
  genre:    '❖',   // genre library (was ◎, now distinct)
  novels:   '📚',  // novels / source materials library
  ledger:   '◉',   // read-only banner mark, also bookkeeping tab
  run:      '▶',   // start run
  stop:     '⏹',   // abort
  reload:   '⟳',   // page reload
  override: '⎇',   // extract-genre override
  settings: '⚙',   // .env editor
  edit:     '✎',   // edit file
  close:    '✕',   // dismiss
  success:  '✓',   // success mark
  fail:     '✕',   // failure mark
  hook:     '⚑',   // pending hooks (pennant)
  weigh:    '⚖',   // resource ledger, verdict
  status:   '❂',   // current status card (sunburst)
  section:  '§',   // rules sections

  // ---- tree glyphs (state files, chapters, summaries) ----
  setting:  '◆',   // "fact pack" files (era, writing-style-extra, …)
  meta:     '•',   // runtime meta files (progress, outline, timeline)
  plan:     '◇',   // planner output
  summary:  '≡',   // chapter summary
  slop:     '△',   // AI-slop patch
  charGuard:'☗',   // character-guard patch
  chapter:  '✎',   // chapter.md (same glyph as edit — file IS edited)
  caret:    '▶',   // tree-group collapsed indicator
  pinned:   '★',   // project root pinned doc (AGENTS.md)
};
