# EMDX Quick Reference

A concise cheat sheet for common EMDX commands and TUI keybindings.

## CLI Commands

### Document Operations

| Command | Description | Example |
|---------|-------------|---------|
| `emdx save <file>` | Save file to knowledge base | `emdx save notes.md` |
| `emdx save --title "X"` | Save stdin with title | `echo "text" \| emdx save --title "Note"` |
| `emdx find <query>` | Full-text search | `emdx find "docker compose"` |
| `emdx find --tags <t>` | Search by tags | `emdx find --tags "gameplan,active"` |
| `emdx view <id>` | View document content | `emdx view 42` |
| `emdx edit <id>` | Edit in default editor | `emdx edit 42` |
| `emdx delete <id>` | Soft delete document | `emdx delete 42` |

### Tag Management

| Command | Description | Example |
|---------|-------------|---------|
| `emdx tag <id> <tags...>` | Add tags | `emdx tag 42 gameplan active` |
| `emdx untag <id> <tags...>` | Remove tags | `emdx untag 42 urgent` |
| `emdx tags` | List all tags with counts | `emdx tags` |
| `emdx legend` | Show emoji aliases | `emdx legend` |
| `emdx retag <old> <new>` | Rename tag globally | `emdx retag "todo" "active"` |

### Common Tag Aliases

| Alias | Emoji | Purpose |
|-------|-------|---------|
| `gameplan` | `🎯` | Strategic plans |
| `active` | `🚀` | Currently working on |
| `done` | `✅` | Completed |
| `blocked` | `🚧` | Stuck/waiting |
| `bug` | `🐛` | Bug reports |
| `feature` | `✨` | New features |
| `urgent` | `🔥` | High priority |
| `analysis` | `🔍` | Investigation |
| `notes` | `📝` | General notes |
| `success` | `🎉` | Worked as intended |
| `failed` | `❌` | Didn't work |

### Browsing & Stats

| Command | Description |
|---------|-------------|
| `emdx list` | List documents by project |
| `emdx recent [n]` | Show n most recent (default: 10) |
| `emdx stats` | Knowledge base statistics |
| `emdx projects` | List all projects |
| `emdx trash` | View deleted documents |
| `emdx restore <id>` | Restore from trash |

### Execution Monitoring

| Command | Description |
|---------|-------------|
| `emdx exec list` | List recent executions |
| `emdx exec show <id>` | Show execution details |
| `emdx exec running` | Show running executions |
| `emdx exec health` | Health check running processes |
| `emdx exec monitor` | Real-time monitoring |
| `emdx exec kill <id>` | Terminate execution |
| `emdx exec killall` | Kill all running |

### AI Agents (see [AI Agents Guide](ai-agents.md))

| Command | Description |
|---------|-------------|
| `emdx agent list` | List available agents |
| `emdx agent run <name> --doc <id>` | Run agent on document |
| `emdx agent run <name> --background` | Run in background |
| `emdx agent create` | Create custom agent |
| `emdx agent info <name>` | View agent details |

### Maintenance

| Command | Description |
|---------|-------------|
| `emdx maintain cleanup` | Show cleanup preview |
| `emdx maintain cleanup --execute` | Perform cleanup |
| `emdx gc` | Garbage collection preview |
| `emdx gc --execute` | Perform garbage collection |

---

## TUI Keybindings (`emdx gui`)

### Global (All Modes)

| Key | Action |
|-----|--------|
| `q` | Quit / Back to documents |
| `?` | Help |
| `:` | Command mode |
| `Ctrl+C` | Force quit |

### Mode Switching

| Key | Mode |
|-----|------|
| `d` | Document browser (default) |
| `l` | Log browser |
| `f` | File browser |
| `a` | Agent browser |

### Document Browser

| Key | Action |
|-----|--------|
| `j` / `k` | Move down / up |
| `g` / `G` | Go to top / bottom |
| `/` | Search |
| `Enter` | View document |
| `e` | Edit document |
| `n` | New document |
| `t` / `T` | Add / remove tags |
| `s` | Selection mode |
| `x` | Execute document |
| `r` | Refresh |

### Log Browser

| Key | Action |
|-----|--------|
| `j` / `k` | Move down / up |
| `g` / `G` | Go to top / bottom |
| `l` | Toggle live mode |
| `s` | Selection mode |
| `r` | Refresh |
| `Space` | Toggle live streaming |
| `k` | Kill execution |

### File Browser

| Key | Action |
|-----|--------|
| `j` / `k` | Move down / up |
| `h` / `l` | Parent dir / enter dir |
| `g` / `G` | Go to top / bottom |
| `.` | Toggle hidden files |
| `/` | Search |
| `e` | Edit file |
| `s` | Selection mode |

### Agent Browser

| Key | Action |
|-----|--------|
| `j` / `k` | Move down / up |
| `g` / `G` | Go to top / bottom |
| `r` | Run selected agent |
| `n` | Create new agent |
| `e` | Edit agent |
| `d` | Delete agent |
| `h` | View execution history |
| `v` | Toggle active/inactive |

---

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `EMDX_DB_PATH` | Database location | `~/.emdx/emdx.db` |
| `GITHUB_TOKEN` | Gist integration | - |
| `EDITOR` | Default editor | System default |

---

## Common Workflows

### Quick Note Capture
```bash
echo "Remember: update API docs" | emdx save --title "Todo" --tags "notes,active"
```

### Track a Gameplan
```bash
# Create
emdx save plan.md --tags "gameplan,active"

# Mark blocked
emdx tag 123 blocked && emdx untag 123 active

# Mark complete with outcome
emdx tag 123 done success && emdx untag 123 blocked
```

### Monitor Background Task
```bash
emdx agent run doc-generator --doc 456 --background
emdx log --live  # Watch progress
```

### Find Active Work
```bash
emdx find --tags "active"
emdx find --tags "blocked"  # Needs attention
```

---

**Full Documentation:** [docs/README.md](README.md) | **CLI Details:** [cli-api.md](cli-api.md) | **AI Agents:** [ai-agents.md](ai-agents.md)
