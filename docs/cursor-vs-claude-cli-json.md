# Cursor vs Claude CLI: JSON Output Format Analysis

## Executive Summary

Cursor and Claude CLI output JSON in NDJSON format (newline-delimited JSON). While they share core structural elements, they diverge significantly in:
- **Metadata richness**: Claude CLI includes extensive usage/cost tracking; Cursor focuses on API source
- **Message structure**: Claude CLI uses Anthropic's native message format; Cursor uses a simplified wrapper
- **Timing data**: Both track duration, but Claude CLI separates API time from total time
- **Parser compatibility**: A robust parser must handle both formats with conditional logic

---

## Detailed Comparison Table

### 1. Common Fields (Work Identically)

| Field | Both Contain | Example Value | Purpose |
|-------|--------------|---------------|---------|
| `type` | Yes | `"system"`, `"user"`, `"assistant"`, `"result"` | Message classification |
| `session_id` | Yes | UUID string | Session tracking |
| `cwd` | Yes (in `init`) | `/path/to/project` | Working directory |
| `is_error` | Yes (in `result`) | `false` | Success indicator |
| `duration_ms` | Yes (in `result`) | `5182` | Total elapsed time |

---

### 2. Fields Unique to Claude CLI

| Field | Type | Example | Purpose | Requirement |
|-------|------|---------|---------|-------------|
| `tools` | Array (omitted) | `[...]` | Available tool definitions | Optional, extensive |
| `mcp_servers` | Array (omitted) | `[...]` | MCP server configs | Optional, extensive |
| `model` | String | `"claude-sonnet-4-5-20250929"` | Exact model identifier | Required in result |
| `duration_api_ms` | Number | `2795` | API call duration only | In result |
| `num_turns` | Number | `1` | Conversation turn count | In result |
| `total_cost_usd` | Number | `0.07933785` | Token cost calculation | In result |
| `usage` | Object | `{"input_tokens": ..., "output_tokens": ...}` | Token breakdown | In result |
| `modelUsage` | Object | `{...}` | Model-specific metrics | In result (omitted in example) |
| `id` (in assistant msg) | String | `"msg_01SK5Tg5fgiQKQgQg8xCC2UE"` | Anthropic message ID | In message |
| `stop_reason` | String/Null | `null` | Why model stopped generating | In message |
| `stop_sequence` | String/Null | `null` | Stop sequence matched | In message |

---

### 3. Fields Unique to Cursor

| Field | Type | Example | Purpose | Requirement |
|-------|------|---------|---------|-------------|
| `subtype` | String | `"init"`, `"success"` | Event classification | In `system` and `result` |
| `apiKeySource` | String | `"login"` | Auth method used | In `system/init` only |
| `model` | String | `"Auto"` | Model selection mode | In `system/init` |
| `permissionMode` | String | `"default"` | Permission level | In `system/init` |
| `request_id` | String | UUID | Request correlation ID | In `result` |
| `result` | Any | `"hello"` | Output value | In `result` only |

---

### 4. Same Field Name, Different Structure

#### A. `model` Field

**Cursor (system/init):**
```json
"model": "Auto"
```
- Represents user's model selection mode
- Values: `"Auto"`, specific model name, or provider
- Set once at session init

**Claude CLI (system/init and result):**
```json
"model": "claude-sonnet-4-5-20250929"
```
- Represents actual model being used
- Specific Anthropic model ID with timestamp
- Can appear in multiple message types

**Parser Impact:** Different semantic meaning despite same field name. Use context (`type`/`subtype`) to disambiguate.

---

#### B. `duration_api_ms` Field

**Cursor (result only):**
```json
"duration_api_ms": 5182
```
- Equal to `duration_ms` (no distinction)
- Entire operation is API-bound

**Claude CLI (result only):**
```json
"duration_ms": 2805,
"duration_api_ms": 2795
```
- Shows network/API latency separately
- Total time includes I/O overhead, parsing, etc.
- `duration_ms - duration_api_ms` = local processing time (10ms)

**Parser Impact:** Claude CLI provides more granular timing. Cursor conflates them.

---

#### C. `message` Field Structure

**Cursor (user/assistant):**
```json
{
  "type": "user",
  "message": {
    "role": "user",
    "content": [{"type": "text", "text": "..."}]
  }
}
```

**Claude CLI (assistant only):**
```json
{
  "type": "assistant",
  "message": {
    "model": "claude-sonnet-4-5-20250929",
    "id": "msg_01SK5Tg5fgiQKQgQg8xCC2UE",
    "type": "message",
    "role": "assistant",
    "content": [...],
    "stop_reason": null,
    "stop_sequence": null,
    "usage": {...}
  }
}
```

**Differences:**
| Sub-field | Cursor | Claude CLI | Purpose |
|-----------|--------|-----------|---------|
| `role` | Yes | Yes | Common field |
| `content` | Yes | Yes | Message body |
| `model` | No | Yes | Which model responded |
| `id` | No | Yes | Message ID (for tracing) |
| `type` | No (redundant) | Yes | Message type indicator |
| `stop_reason` | No | Yes | Why generation stopped |
| `stop_sequence` | No | Yes | Sequence that triggered stop |
| `usage` | No | Yes | Token metrics |

**Parser Impact:** Claude CLI's message object is richer. Parser must handle optional fields.

---

## Parser Compatibility Matrix

### Message Flow Differences

```
CURSOR                          CLAUDE CLI
┌──────────────────┐            ┌──────────────────┐
│ system/init      │            │ system/init      │
│ (apiKeySource)   │            │ (tools, servers) │
└──────────────────┘            └──────────────────┘
         ↓                                ↓
┌──────────────────┐            (no user message output)
│ user             │
│ (input echo)     │
└──────────────────┘
         ↓                                ↓
┌──────────────────┐            ┌──────────────────┐
│ assistant        │            │ assistant        │
│ (simple content) │            │ (full metadata)  │
└──────────────────┘            └──────────────────┘
         ↓                                ↓
┌──────────────────┐            ┌──────────────────┐
│ result           │            │ result           │
│ (request_id)     │            │ (total_cost_usd) │
└──────────────────┘            └──────────────────┘
```

---

## Compatibility Implications

### Challenge 1: Model Field Ambiguity

**Problem:**
- Cursor: `"model": "Auto"` (user selection)
- Claude CLI: `"model": "claude-sonnet-4-5-20250929"` (actual model)

**Solution:**
```python
def parse_model(msg, source):
    if source == "cursor":
        # In init: selection mode
        # In result: not present
        return msg.get("model", "Auto")
    else:  # claude_cli
        # Always the actual model ID
        return msg["model"]
```

---

### Challenge 2: Timing Granularity

**Problem:**
- Cursor conflates `duration_api_ms` with `duration_ms`
- Claude CLI separates API time from total time

**Solution:**
```python
def parse_timing(result):
    total = result["duration_ms"]
    api = result.get("duration_api_ms", total)
    overhead = total - api

    return {
        "total_ms": total,
        "api_ms": api,
        "overhead_ms": overhead
    }
```

---

### Challenge 3: Message Metadata

**Problem:**
- Claude CLI's message has optional fields that Cursor lacks
- Different message routing (Cursor echoes user, Claude doesn't)

**Solution:**
```python
def parse_assistant_message(msg):
    content = msg.get("content", [])

    metadata = {
        "stop_reason": msg.get("stop_reason"),
        "stop_sequence": msg.get("stop_sequence"),
        "model": msg.get("model"),
        "message_id": msg.get("id"),
        "tokens_used": msg.get("usage", {})
    }

    return {
        "content": extract_text(content),
        "metadata": metadata
    }
```

---

### Challenge 4: Cost Tracking

**Problem:**
- Claude CLI includes `total_cost_usd` and detailed `usage`
- Cursor has no cost tracking

**Solution:**
```python
def extract_cost(result):
    if "total_cost_usd" in result:
        return {
            "cost_usd": result["total_cost_usd"],
            "input_tokens": result.get("usage", {}).get("input_tokens", 0),
            "output_tokens": result.get("usage", {}).get("output_tokens", 0)
        }
    else:
        return None  # Cursor has no cost info
```

---

## Unified Parser Design

```python
class UnifiedParser:
    def __init__(self, source: Literal["cursor", "claude_cli"]):
        self.source = source

    def parse_line(self, json_line: str) -> Message:
        data = json.loads(json_line)
        msg_type = data.get("type")

        if msg_type == "system":
            return self._parse_system(data)
        elif msg_type == "user":
            return self._parse_user(data)
        elif msg_type == "assistant":
            return self._parse_assistant(data)
        elif msg_type == "result":
            return self._parse_result(data)
        else:
            raise ValueError(f"Unknown message type: {msg_type}")

    def _parse_system(self, data):
        # Extract common: session_id, cwd, permissionMode
        # Extract source-specific: apiKeySource (cursor), tools/mcp (cli)
        pass

    def _parse_assistant(self, data):
        # Extract content (both have this)
        # Extract metadata: model, stop_reason, usage (cli only)
        pass

    def _parse_result(self, data):
        # Extract common: duration_ms, is_error
        # Extract source-specific: request_id (cursor), cost (cli)
        pass
```

---

## Key Takeaways

| Aspect | Cursor | Claude CLI | For Parsers |
|--------|--------|-----------|------------|
| **Format** | NDJSON | NDJSON | Same |
| **Message flow** | 4 types (init, user, assistant, result) | 3-4 types (init, assistant, result) | User message differs |
| **Metadata** | Minimal | Rich (tokens, costs, IDs) | Must handle optional fields |
| **Timing** | Conflated | Separated | Use `.get()` for optional |
| **Model info** | Selection mode in init | Actual model ID throughout | Context-aware parsing |
| **Error handling** | Basic (`is_error`) | Basic (`is_error`) | Same |
| **Future compatibility** | May add more fields | Likely to expand | Plan for extensibility |

---

## Recommended Parser Strategy

1. **Detect source** from first message (presence of `apiKeySource` = Cursor, presence of `tools` = Claude CLI)
2. **Use source-aware parsing** with conditional field extraction
3. **Build schema** that accepts both formats without loss
4. **Handle optional fields** gracefully with `.get()` and defaults
5. **Test against both** formats in CI/CD to catch regressions
6. **Document assumptions** about field presence/absence per source

---

## Implementation Checklist

- [ ] Detect source reliably (first message analysis)
- [ ] Parse system/init (both sources)
- [ ] Parse user (Cursor only)
- [ ] Parse assistant (handle metadata differences)
- [ ] Parse result (handle timing and cost differences)
- [ ] Extract text content from nested structure
- [ ] Convert to canonical format (for uniform downstream processing)
- [ ] Handle missing optional fields
- [ ] Add logging for debugging mismatches
- [ ] Unit test both formats
- [ ] Integration test with real CLI output
