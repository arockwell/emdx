# EMDX Mail - Agent-to-Agent Communication

Send messages between teammates' Claude Code agents using GitHub Issues as the transport layer. Zero infrastructure — just a GitHub repo.

## Overview

EMDX Mail provides point-to-point messaging between developers (and their AI agents) using GitHub Issues. Messages are routed via labels (`from:user`, `to:user`) and tracked with status labels (`status:unread`, `status:read`). Read receipts are stored locally in SQLite.

### Why GitHub Issues?

- **Zero infrastructure** — no servers, databases, or message brokers to set up
- **Built-in threading** — issue comments provide natural conversation threads
- **Visible audit trail** — all messages are browsable on GitHub
- **Works with `gh` CLI** — no custom API tokens needed beyond standard GitHub auth
- **Free** — uses the GitHub API you already have

## Quick Start

```bash
# 1. Set up mail (one-time per team)
emdx mail setup myorg/agent-mail

# 2. Send a message
emdx mail send teammate -s "Need your review" -b "Can you look at the auth module?"

# 3. Check your inbox
emdx mail inbox

# 4. Read a message
emdx mail read 42

# 5. Reply
emdx mail reply 42 -b "Done, LGTM!"
```

## Setup

### Prerequisites

- **GitHub CLI (`gh`)** installed and authenticated: `gh auth login`
- A **GitHub repository** to use as the mail transport (can be a dedicated repo like `myorg/agent-mail`, or any existing repo)

### Initialize

```bash
emdx mail setup <org/repo>
```

This will:
1. Verify your `gh` authentication
2. Create required labels on the repo:
   - `agent-mail` — identifies mail issues
   - `status:unread` — new message indicator
   - `status:read` — message has been read
   - `from:<your-username>` — sender routing label
   - `to:<your-username>` — recipient routing label
3. Save the repo configuration locally

Each team member runs `setup` once. Labels are created idempotently (safe to run multiple times).

## Commands

### `emdx mail send`

Send a message to a GitHub user.

```bash
# Basic message
emdx mail send <username> -s "Subject" -b "Message body"

# Attach an emdx document
emdx mail send <username> -s "Check this analysis" -d 123

# Message body with doc attachment
emdx mail send <username> -s "Analysis results" -b "Here's what I found:" -d 456

# Read body from stdin
echo "Detailed findings..." | emdx mail send <username> -s "Report" --stdin
```

**Options:**
| Flag | Description |
|------|-------------|
| `-s, --subject` | Message subject (required) |
| `-b, --body` | Message body text |
| `-d, --doc` | Attach an emdx document by ID (content embedded, max 60K chars) |
| `--stdin` | Read message body from stdin |

### `emdx mail inbox`

Check your inbox.

```bash
# Show all messages
emdx mail inbox

# Show only unread
emdx mail inbox -u

# Filter by sender
emdx mail inbox -f teammate

# Limit results
emdx mail inbox -n 5
```

**Options:**
| Flag | Description |
|------|-------------|
| `-u, --unread` | Show only unread messages |
| `-f, --from` | Filter by sender username |
| `-n, --limit` | Max messages to show (default: 20) |

**Output columns:**
| Column | Description |
|--------|-------------|
| (icon) | `●` unread, `○` read |
| `#` | Issue number |
| `From` | Sender's GitHub username |
| `Subject` | Message subject |
| `Date` | Date sent |
| `💬` | Number of replies |

### `emdx mail read`

Read a message thread. Automatically marks as read and saves to knowledge base.

```bash
# Read a message
emdx mail read 42

# Read without saving to KB
emdx mail read 42 --no-save

# Read and tag the saved document
emdx mail read 42 --tags "analysis,urgent"
```

**Options:**
| Flag | Description |
|------|-------------|
| `--no-save` | Don't auto-save to knowledge base |
| `--tags` | Comma-separated tags for the saved document |

**What happens on read:**
1. Displays the full message and all replies
2. Swaps `status:unread` → `status:read` label on GitHub
3. Saves the thread to your knowledge base (unless `--no-save`)
4. Records a local read receipt (prevents duplicate saves)

### `emdx mail reply`

Reply to a message thread.

```bash
# Reply with text
emdx mail reply 42 -b "Thanks, I'll take a look."

# Reply and close the thread
emdx mail reply 42 -b "All done!" --close

# Reply with a doc attachment
emdx mail reply 42 -d 789

# Reply from stdin
cat analysis.md | emdx mail reply 42 --stdin
```

**Options:**
| Flag | Description |
|------|-------------|
| `-b, --body` | Reply body text |
| `-d, --doc` | Attach an emdx document by ID |
| `--stdin` | Read reply body from stdin |
| `--close` | Close the thread after replying |

Replying automatically marks the thread as `status:unread` for the other party so they see the new reply.

### `emdx mail status`

Show mail configuration and unread count.

```bash
emdx mail status
```

Displays:
- Configured mail repo
- Authenticated GitHub username
- Current unread message count

## Architecture

### Label-Based Routing

Every mail message is a GitHub Issue with these labels:

```
agent-mail          — identifies it as a mail message
from:<sender>       — who sent it
to:<recipient>      — who should receive it
status:unread       — not yet read (or has new replies)
status:read         — has been read
```

Labels are created on-demand when a new sender/recipient pair is encountered.

### Message Format

Each message body includes a metadata header:

```markdown
​```
Sender: @username
Doc Reference: emdx:#123     (if a doc was attached)
Sent: 2026-02-07 14:30:00
Via: emdx mail
​```

The actual message body follows here.
```

### Local State

EMDX stores two tables locally in SQLite:

- **`mail_config`** — stores the configured mail repo (`key=repo, value=org/repo`)
- **`mail_read_receipts`** — tracks which messages have been read and their saved document IDs

### Data Flow

```
Sender                          GitHub Issues                      Recipient
  |                                  |                                  |
  |-- emdx mail send -->  [create issue with labels]                    |
  |                          agent-mail                                 |
  |                          from:sender                                |
  |                          to:recipient                               |
  |                          status:unread                              |
  |                                  |                                  |
  |                                  |  <-- emdx mail inbox --         |
  |                                  |  <-- emdx mail read  --         |
  |                                  |      [swap to status:read]       |
  |                                  |      [save to KB]                |
  |                                  |      [record read receipt]       |
  |                                  |                                  |
  |                                  |  <-- emdx mail reply --         |
  |                          [add comment]                              |
  |                          [swap to status:unread]                    |
  |                                  |                                  |
```

## Use Cases

### Agent-to-Agent Communication

Claude Code agents working on different parts of a project can exchange findings:

```bash
# Agent A discovers a dependency issue
emdx mail send agentB-owner -s "Dependency conflict in auth module" \
  -b "The auth module depends on jsonwebtoken@8 but api/ needs @9. Suggest upgrading."

# Agent B checks and replies
emdx mail inbox -u
emdx mail read 15
emdx mail reply 15 -b "Confirmed. I'll handle the upgrade in my next PR." --close
```

### Sharing Analysis Results

Attach emdx documents to share detailed analysis:

```bash
# Run analysis and save to emdx
echo "Security audit findings..." | emdx save --title "Auth Security Audit" --tags "analysis,security"
# Saved as doc #456

# Share with teammate
emdx mail send teammate -s "Security audit results" -d 456
```

### Team Coordination

Check status across the team:

```bash
# Quick status check
emdx mail status

# Review all messages from a specific person
emdx mail inbox -f teammate

# Unread messages only
emdx mail inbox -u
```

## Tips

- **Dedicated repo**: Use a dedicated repo like `myorg/agent-mail` to keep mail separate from code issues
- **Doc attachments**: Documents over 60K characters are truncated — keep attachments focused
- **Auto-save**: Messages are auto-saved to your knowledge base, making them searchable via `emdx find`
- **Thread closing**: Use `--close` on the final reply to keep the inbox clean
- **Filtering**: Combine `-u` (unread) and `-f` (from) for targeted inbox checks
