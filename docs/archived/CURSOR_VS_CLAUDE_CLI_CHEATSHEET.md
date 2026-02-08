# Cursor vs Claude CLI: Quick Reference Cheatsheet

## Field Comparison Matrix (One-Pager)

```
╔════════════════════════╦═════════════╦══════════════╦═══════════════════╗
║ Field                  ║ Cursor      ║ Claude CLI   ║ Notes             ║
╠════════════════════════╬═════════════╬══════════════╬═══════════════════╣
║ SYSTEM/INIT MESSAGE    ║             ║              ║                   ║
├────────────────────────┼─────────────┼──────────────┼───────────────────┤
║ type                   ║ ✓ "system"  ║ ✓ "system"   ║ Always present    ║
║ subtype                ║ ✓ "init"    ║ ✓ "init"     ║ Always "init"     ║
║ session_id             ║ ✓ UUID      ║ ✓ UUID       ║ Use for tracking  ║
║ cwd                    ║ ✓           ║ ✓            ║ Working directory ║
║ model                  ║ ✓ "Auto"    ║ ✓ Full ID    ║ Different meaning ║
║ permissionMode         ║ ✓           ║ ✓            ║ Usually "default" ║
║ apiKeySource           ║ ✓ "login"   ║ ✗            ║ Cursor-only       ║
║ tools                  ║ ✗           ║ ✓ Array      ║ Claude-only       ║
║ mcp_servers            ║ ✗           ║ ✓ Array      ║ Claude-only       ║
╠════════════════════════╬═════════════╬══════════════╬═══════════════════╣
║ USER MESSAGE           ║             ║              ║                   ║
├────────────────────────┼─────────────┼──────────────┼───────────────────┤
║ type                   ║ ✓ "user"    ║ ✗ (not sent) ║ Cursor echoes it  ║
║ message.role           ║ ✓ "user"    ║ ─            ║ ─                 ║
║ message.content        ║ ✓ Array     ║ ─            ║ ─                 ║
╠════════════════════════╬═════════════╬══════════════╬═══════════════════╣
║ ASSISTANT MESSAGE      ║             ║              ║                   ║
├────────────────────────┼─────────────┼──────────────┼───────────────────┤
║ message.role           ║ ✓ "asst."   ║ ✓ "asst."    ║ Always present    ║
║ message.content        ║ ✓ Array     ║ ✓ Array      ║ Text extraction   ║
║ message.model          ║ ✗           ║ ✓            ║ Which model       ║
║ message.id             ║ ✗           ║ ✓            ║ Anthropic ID      ║
║ message.stop_reason    ║ ✗           ║ ✓            ║ Why it stopped    ║
║ message.stop_sequence  ║ ✗           ║ ✓            ║ Stop token        ║
║ message.usage          ║ ✗           ║ ✓            ║ Token metrics     ║
╠════════════════════════╬═════════════╬══════════════╬═══════════════════╣
║ RESULT MESSAGE         ║             ║              ║                   ║
├────────────────────────┼─────────────┼──────────────┼───────────────────┤
║ type                   ║ ✓ "result"  ║ ✓ "result"   ║ Always present    ║
║ subtype                ║ ✓ "success" ║ ✓ "success"  ║ On success        ║
║ is_error               ║ ✓ bool      ║ ✓ bool       ║ Error indicator   ║
║ duration_ms            ║ ✓           ║ ✓            ║ Total time        ║
║ duration_api_ms        ║ ✓ ~equal    ║ ✓ varies     ║ API time only     ║
║ result                 ║ ✓ output    ║ ✓ output     ║ The response text ║
║ session_id             ║ ✓           ║ ✓            ║ Matches init      ║
║ request_id             ║ ✓ UUID      ║ ✗            ║ Cursor request ID ║
║ num_turns              ║ ✗           ║ ✓            ║ Conversation      ║
║ total_cost_usd         ║ ✗           ║ ✓            ║ Claude API cost   ║
║ usage.input_tokens     ║ ✗           ║ ✓            ║ Input token count ║
║ usage.output_tokens    ║ ✗           ║ ✓            ║ Output token cnt  ║
╚════════════════════════╩═════════════╩══════════════╩═══════════════════╝
```

---

## Source Detection One-Liner

```python
def detect(first_line):
    d = json.loads(first_line)
    return "cursor" if "apiKeySource" in d else "claude_cli"
```

---

## Message Flow

```
CURSOR:
1. system/init (apiKeySource present)
2. user (input echo)
3. assistant (response)
4. result (request_id, no cost)

CLAUDE CLI:
1. system/init (tools, mcp_servers present)
2. assistant (response with metadata)
3. result (cost_usd, tokens, num_turns)
```

---

## Text Extraction

**Both formats use same structure:**
```python
def extract_text(content: list) -> str:
    return "".join(item["text"] for item in content if item.get("type") == "text")
```

---

## Model Field Semantics

| Source | Value | Meaning | Example |
|--------|-------|---------|---------|
| Cursor | `"Auto"` | User's selection mode | In system/init |
| Claude CLI | `"claude-sonnet-4-5-20250929"` | Actual model used | In system/init & messages |

---

## Timing Breakdown

| Metric | Cursor | Claude CLI | Calculation |
|--------|--------|-----------|-------------|
| `duration_ms` | Total | Total | Wall-clock time |
| `duration_api_ms` | ~Total | API only | Network + processing |
| Overhead | ~0ms | Varies | `duration_ms - duration_api_ms` |

**Example:**
```
Cursor:   duration_ms=5182, duration_api_ms=5182, overhead≈0
Claude:   duration_ms=2805, duration_api_ms=2795, overhead=10ms
```

---

## Cost Tracking

| Source | Has Cost Info? | Field | Formula |
|--------|---------------|-------|---------|
| Cursor | ✗ | None | N/A |
| Claude CLI | ✓ | `total_cost_usd` | (input_tokens / 1M × rate) + (output_tokens / 1M × rate) |

---

## Common Parsing Patterns

### Pattern 1: Extract Entire Flow
```python
messages = []
for line in stream:
    msg = json.loads(line)
    if msg["type"] == "system":
        messages.append(("init", msg))
    elif msg["type"] == "assistant":
        messages.append(("response", extract_text(msg["message"]["content"])))
    elif msg["type"] == "result" and not msg.get("is_error"):
        messages.append(("success", msg.get("result")))
```

### Pattern 2: Track by Source
```python
source = detect(stream[0])
for line in stream[1:]:
    msg = json.loads(line)
    if source == "cursor" and msg["type"] == "result":
        req_id = msg["request_id"]  # Safe, always present
    elif source == "claude_cli" and msg["type"] == "result":
        cost = msg.get("total_cost_usd")  # Safe, may be None
```

### Pattern 3: Accumulate Tokens
```python
input_tokens = 0
output_tokens = 0

for line in stream:
    msg = json.loads(line)
    if msg["type"] == "assistant":
        usage = msg["message"].get("usage", {})
        input_tokens += usage.get("input_tokens", 0)
        output_tokens += usage.get("output_tokens", 0)
    elif msg["type"] == "result":
        usage = msg.get("usage", {})
        input_tokens += usage.get("input_tokens", 0)
        output_tokens += usage.get("output_tokens", 0)
```

---

## Minimal Parser (45 Lines)

```python
import json
from typing import Literal

def parse_ndjson(stream):
    source = None

    for line in stream:
        if not line.strip():
            continue

        msg = json.loads(line)
        msg_type = msg.get("type")

        # Detect source from first message
        if source is None and msg_type == "system":
            source = "cursor" if "apiKeySource" in msg else "claude_cli"

        # Route by message type
        if msg_type == "system":
            yield ("system", {
                "session": msg["session_id"],
                "cwd": msg["cwd"],
                "model": msg["model"],
            })

        elif msg_type == "user":
            text = "".join(
                item["text"] for item in msg["message"]["content"]
                if item.get("type") == "text"
            )
            yield ("user", text)

        elif msg_type == "assistant":
            text = "".join(
                item["text"] for item in msg["message"]["content"]
                if item.get("type") == "text"
            )
            tokens = msg["message"].get("usage", {})
            yield ("assistant", {
                "text": text,
                "input_tokens": tokens.get("input_tokens"),
                "output_tokens": tokens.get("output_tokens"),
            })

        elif msg_type == "result":
            yield ("result", {
                "success": not msg.get("is_error", False),
                "duration_ms": msg["duration_ms"],
                "cost_usd": msg.get("total_cost_usd"),
                "output": msg.get("result"),
            })

# Usage
with open("output.ndjson") as f:
    for msg_type, data in parse_ndjson(f):
        print(f"{msg_type}: {data}")
```

---

## Common ✗ Mistakes & ✓ Fixes

### Mistake 1: Assuming User Messages Always Present
```python
# ✗ WRONG
for msg in stream:
    if msg["type"] == "user":
        user_input = extract_text(msg["message"]["content"])
        # Empty for Claude CLI!

# ✓ CORRECT
if source == "cursor":
    # Process user messages
elif source == "claude_cli":
    # Skip user messages (not sent)
```

### Mistake 2: Comparing Model Strings
```python
# ✗ WRONG
if msg["model"] == "claude-sonnet":
    # Fails for Cursor where model="Auto"

# ✓ CORRECT
if source == "claude_cli":
    actual_model = msg["model"]  # "claude-sonnet-4-5-20250929"
elif source == "cursor":
    selection = msg["model"]  # "Auto"
```

### Mistake 3: KeyError on Optional Fields
```python
# ✗ WRONG
cost = msg["total_cost_usd"]  # KeyError for Cursor

# ✓ CORRECT
cost = msg.get("total_cost_usd")  # None for Cursor
```

### Mistake 4: Assuming Equal Timing
```python
# ✗ WRONG
overhead = msg["duration_ms"] - msg["duration_api_ms"]  # Always ~0 for Cursor

# ✓ CORRECT
api = msg.get("duration_api_ms", msg["duration_ms"])
overhead = msg["duration_ms"] - api
```

---

## Test Data

### Cursor Minimal Test
```json
{"type":"system","apiKeySource":"login","session_id":"s1","cwd":"/tmp","model":"Auto","permissionMode":"default"}
{"type":"user","message":{"role":"user","content":[{"type":"text","text":"hi"}]},"session_id":"s1"}
{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"hello"}]},"session_id":"s1"}
{"type":"result","is_error":false,"duration_ms":1000,"duration_api_ms":1000,"result":"hello","session_id":"s1","request_id":"r1"}
```

### Claude CLI Minimal Test
```json
{"type":"system","tools":[],"mcp_servers":[],"session_id":"s2","cwd":"/tmp","model":"claude-sonnet","permissionMode":"default"}
{"type":"assistant","message":{"model":"claude-sonnet","id":"m1","role":"assistant","content":[{"type":"text","text":"hello"}],"usage":{"input_tokens":10,"output_tokens":5}}}
{"type":"result","is_error":false,"duration_ms":2000,"duration_api_ms":1900,"result":"hello","session_id":"s2","total_cost_usd":0.001,"usage":{"input_tokens":10,"output_tokens":5}}
```

---

## Integration Checklist

- [ ] Detect source on first message
- [ ] Handle Cursor's user messages (skip for Claude)
- [ ] Use `.get()` for optional fields
- [ ] Calculate overhead (total - api)
- [ ] Handle None for Cursor's missing cost/tokens
- [ ] Log source for debugging
- [ ] Test with both formats
- [ ] Handle parsing errors gracefully

---

## Documentation Links

| Document | Purpose | Read Time |
|----------|---------|-----------|
| CURSOR_VS_CLAUDE_CLI_README.md | Navigation guide | 5 min |
| cursor-vs-claude-cli-json.md | Structural analysis | 10 min |
| cursor-vs-claude-cli-examples.md | Concrete examples | 15 min |
| cursor-vs-claude-cli-parser.md | Implementation | 20 min |
| CURSOR_VS_CLAUDE_CLI_CHEATSHEET.md | This document | 3 min |

---

## Emergency Quick Fixes

### "Parser failing on JSON"
```bash
jq . < output.ndjson > /dev/null  # Validate JSON
head -1 output.ndjson | jq .      # Check first message
```

### "Source detection failing"
```python
data = json.loads(line)
print(f"Has apiKeySource: {'apiKeySource' in data}")
print(f"Has tools: {'tools' in data}")
```

### "Text not extracting"
```python
content = msg["message"]["content"]
print(json.dumps(content, indent=2))  # See structure
```

### "Cost is None but shouldn't be"
```python
# Claude CLI includes cost in result only
if msg["type"] == "result" and not msg.get("is_error"):
    cost = msg.get("total_cost_usd")  # Check in result, not assistant
```

---

**Print this page for quick reference while coding!**
