# Old Commands to Remove

This document lists the old commands that have been consolidated into the new `analyze` and `maintain` commands.

## Commands Consolidated into `emdx analyze`

These can be safely removed as their functionality is now in `emdx analyze`:

1. **emdx/commands/analyze.py** (old analyze command) - replaced by analyze_new.py
2. **emdx health** commands - now `emdx analyze --health`
3. **emdx clean stats** - now part of `emdx analyze`
4. **emdx merge find/detect** - now `emdx analyze --similar`

## Commands Consolidated into `emdx maintain`

These can be safely removed as their functionality is now in `emdx maintain`:

1. **emdx clean empty/duplicates/all** - now `emdx maintain --clean`
2. **emdx health fix** - now `emdx maintain --auto`
3. **emdx merge apply/interactive** - now `emdx maintain --merge`
4. **emdx gc** (standalone) - now `emdx maintain --gc`
5. **emdx tag batch** - now `emdx maintain --tags`

## Commands to Keep As-Is

These commands remain unchanged:

1. **Core CRUD**: save, find, view, edit, delete, trash, restore, purge
2. **Browse**: list, recent, projects, gui, stats, project-stats
3. **Tags**: tag, untag, tags, retag, merge-tags, legend
4. **Lifecycle**: All lifecycle subcommands (status, transition, analyze, auto-detect, flow)
5. **External**: gist, claude, exec commands

## Migration Summary

Old Command | New Command
------------|------------
`emdx analyze` | `emdx analyze` (enhanced)
`emdx health` | `emdx analyze --health`
`emdx clean duplicates` | `emdx maintain --clean`
`emdx clean empty` | `emdx maintain --clean`
`emdx clean stats` | `emdx analyze`
`emdx merge find` | `emdx analyze --similar`
`emdx merge apply` | `emdx maintain --merge`
`emdx gc` | `emdx maintain --gc`
`emdx health fix` | `emdx maintain --auto`
`emdx tag batch` | `emdx maintain --tags`

## Files to Remove

After confirming everything works:

1. `/emdx/commands/clean.py`
2. `/emdx/commands/health.py`
3. `/emdx/commands/merge.py`
4. `/emdx/commands/gc.py`
5. `/emdx/commands/analyze.py` (rename analyze_new.py to analyze.py)