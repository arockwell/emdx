# EMDX Troubleshooting Guide

Common issues and their solutions when using EMDX.

## Installation Issues

### Poetry Install Fails

**Symptom:** `poetry install` fails with dependency errors.

**Solutions:**
1. Ensure Python 3.13+ is installed:
   ```bash
   python3 --version  # Should be 3.13+
   ```

2. Try clearing Poetry cache:
   ```bash
   poetry cache clear pypi --all
   poetry install
   ```

3. Update Poetry itself:
   ```bash
   pipx upgrade poetry
   ```

### Command Not Found: `emdx`

**Symptom:** After installation, `emdx` command is not found.

**Solutions:**
1. Use Poetry to run commands in development:
   ```bash
   poetry run emdx --help
   ```

2. If installed globally, ensure pip bin directory is in PATH:
   ```bash
   export PATH="$HOME/.local/bin:$PATH"
   ```

3. Activate the virtual environment:
   ```bash
   source .venv/bin/activate
   emdx --help
   ```

---

## Database Issues

### Database Locked

**Symptom:** `sqlite3.OperationalError: database is locked`

**Causes:**
- Another EMDX process is accessing the database
- A TUI session is open while running CLI commands

**Solutions:**
1. Close any open TUI sessions (`emdx gui`)
2. Check for running EMDX processes:
   ```bash
   ps aux | grep emdx
   ```
3. Kill stale processes if necessary

### Database Corruption

**Symptom:** SQLite errors, missing data, or application crashes.

**Solutions:**
1. Run integrity check:
   ```bash
   sqlite3 ~/.emdx/emdx.db "PRAGMA integrity_check;"
   ```

2. If corrupted, restore from backup (if available):
   ```bash
   cp ~/.emdx/emdx.db.backup ~/.emdx/emdx.db
   ```

3. As a last resort, export what you can and recreate:
   ```bash
   # Export documents (if readable)
   sqlite3 ~/.emdx/emdx.db ".dump documents" > backup.sql
   ```

### Migration Errors

**Symptom:** Schema migration fails on startup.

**Solutions:**
1. Check current migration version:
   ```bash
   sqlite3 ~/.emdx/emdx.db "SELECT * FROM migrations;"
   ```

2. Try running migrations manually (development only):
   ```bash
   poetry run python -c "from emdx.database.migrations import run_migrations; run_migrations()"
   ```

3. Backup and recreate database if migrations are broken.

---

## TUI Issues

### TUI Display Problems

**Symptom:** Characters display incorrectly, layout is broken, or colors are wrong.

**Solutions:**
1. Ensure terminal supports Unicode:
   ```bash
   echo $LANG  # Should include UTF-8, e.g., en_US.UTF-8
   ```

2. Try a different terminal emulator (iTerm2, Alacritty, Windows Terminal)

3. Check terminal color support:
   ```bash
   echo $TERM  # Should be xterm-256color or similar
   ```

4. Set proper locale:
   ```bash
   export LANG=en_US.UTF-8
   export LC_ALL=en_US.UTF-8
   ```

### TUI Hangs or Freezes

**Symptom:** The TUI becomes unresponsive.

**Solutions:**
1. Press `Ctrl+C` to attempt graceful exit
2. If unresponsive, kill the process:
   ```bash
   pkill -f "emdx gui"
   ```

3. Check for resource issues (memory, CPU)

4. Try running with debug output:
   ```bash
   TEXTUAL_CONSOLE=1 poetry run emdx gui
   ```

### Keybindings Not Working

**Symptom:** Pressing keys doesn't trigger expected actions.

**Causes:**
- Wrong browser mode
- Terminal intercepting keys
- Modal editing mode active

**Solutions:**
1. Check current mode - press `?` for help
2. Press `Esc` twice to exit any modal/editing mode
3. Use `q` to return to document browser
4. Check if terminal is intercepting keys (common with tmux/screen)

---

## Search Issues

### Search Returns No Results

**Symptom:** `emdx find` returns nothing even when documents exist.

**Solutions:**
1. Verify documents exist:
   ```bash
   emdx list
   emdx stats
   ```

2. Check FTS index health:
   ```bash
   sqlite3 ~/.emdx/emdx.db "SELECT * FROM documents_fts LIMIT 5;"
   ```

3. Try simpler search terms or use tag search:
   ```bash
   emdx find --tags "active"
   ```

4. Rebuild FTS index (if available):
   ```bash
   emdx maintain cleanup --execute
   ```

### Tag Search Not Working

**Symptom:** `--tags` filter doesn't find expected documents.

**Solutions:**
1. Check exact tag names:
   ```bash
   emdx tags  # List all tags
   ```

2. Verify document has expected tags:
   ```bash
   emdx view <id>  # Shows document with tags
   ```

3. Use correct tag aliases (not emoji directly):
   ```bash
   emdx find --tags "gameplan"  # Not --tags "🎯"
   ```

---

## Execution Issues

### Execution Stays Running Forever

**Symptom:** An execution shows as "running" but never completes.

**Solutions:**
1. Check execution health:
   ```bash
   emdx exec health
   ```

2. View execution logs for errors:
   ```bash
   emdx exec show <id> --full
   ```

3. Kill the stuck execution:
   ```bash
   emdx exec kill <id>
   ```

4. Kill all running executions:
   ```bash
   emdx exec killall
   ```

### Log Streaming Not Updating

**Symptom:** Live log view (`emdx log --live`) doesn't show new content.

**Solutions:**
1. Verify execution is still running:
   ```bash
   emdx exec running
   ```

2. Check if log file exists:
   ```bash
   ls -la ~/.emdx/logs/
   ```

3. Try refreshing with `r` key in TUI

4. Check file watcher is working:
   ```bash
   # Create test file and verify watching works
   touch ~/.emdx/logs/test.log
   ```

---

## Agent Issues

### Agent Not Found

**Symptom:** `emdx agent run <name>` says agent doesn't exist.

**Solutions:**
1. List all agents (including inactive):
   ```bash
   emdx agent list --all
   ```

2. Check exact agent name spelling

3. Verify agent is active:
   ```bash
   emdx agent info <name>
   ```

### Agent Execution Fails

**Symptom:** Agent starts but fails to complete.

**Solutions:**
1. Check execution logs:
   ```bash
   emdx exec list --limit 5
   emdx exec show <execution_id>
   ```

2. Verify required tools are available to agent

3. Check agent configuration:
   ```bash
   emdx agent info <name>
   ```

4. Try with verbose output:
   ```bash
   emdx agent run <name> --doc <id> --verbose
   ```

---

## Integration Issues

### GitHub Gist Integration Fails

**Symptom:** `emdx gist create` fails with authentication errors.

**Solutions:**
1. Verify GITHUB_TOKEN is set:
   ```bash
   echo $GITHUB_TOKEN
   ```

2. Check token has `gist` scope

3. Test token directly:
   ```bash
   curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/gists
   ```

4. Create a new token at https://github.com/settings/tokens

### Git Project Detection Fails

**Symptom:** Documents not auto-assigned to correct project.

**Solutions:**
1. Verify you're in a git repository:
   ```bash
   git rev-parse --show-toplevel
   ```

2. Check `.git` directory exists

3. Manually specify project:
   ```bash
   emdx save file.md --project "my-project"
   ```

---

## Performance Issues

### Slow Searches

**Symptom:** `emdx find` takes a long time with many documents.

**Solutions:**
1. Limit results:
   ```bash
   emdx find "query" --limit 10
   ```

2. Use more specific queries

3. Check database size:
   ```bash
   ls -lh ~/.emdx/emdx.db
   ```

4. Run database optimization:
   ```bash
   sqlite3 ~/.emdx/emdx.db "VACUUM;"
   sqlite3 ~/.emdx/emdx.db "ANALYZE;"
   ```

### TUI Slow or Laggy

**Symptom:** Interface is sluggish, especially with many documents.

**Solutions:**
1. Reduce visible documents with filters
2. Close other resource-intensive applications
3. Try simpler terminal emulator
4. Check system resources (memory, CPU)

---

## Getting More Help

### Debug Information

Collect diagnostic information for bug reports:

```bash
# Version info
poetry run emdx --version
python --version
poetry --version

# Database info
sqlite3 ~/.emdx/emdx.db "SELECT COUNT(*) FROM documents;"
ls -la ~/.emdx/

# Environment
echo $TERM
echo $LANG
```

### Reporting Issues

When reporting issues:
1. Include the debug information above
2. Describe steps to reproduce
3. Include error messages (full traceback if available)
4. Specify operating system and terminal emulator

**Report issues at:** https://github.com/your-org/emdx/issues

---

**Related Documentation:**
- [Development Setup](development-setup.md) - Development environment configuration
- [Database Design](database-design.md) - Database internals and migrations
- [Testing Guide](testing.md) - Running and writing tests
