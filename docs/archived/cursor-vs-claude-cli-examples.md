# Cursor vs Claude CLI: Side-by-Side Examples

This document provides annotated JSON examples showing exactly where and how the two formats differ.

---

## Example 1: System Initialization

### Cursor Output

```json
{
  "type": "system",
  "subtype": "init",
  "apiKeySource": "login",           ← CURSOR-ONLY: How auth was obtained
  "cwd": "/Users/alexrockwell/dev/worktrees/emdx-cursorify",
  "session_id": "472896b5-0079-411c-9c10-ec912453c2a4",
  "model": "Auto",                   ← CURSOR: User's selection mode
  "permissionMode": "default"
}
```

### Claude CLI Output

```json
{
  "type": "system",
  "subtype": "init",
  "cwd": "/Users/alexrockwell/dev/worktrees/emdx-cursorify",
  "session_id": "4318e3f4-0333-4e88-b253-fa0b89a7591a",
  "tools": [...],                    ← CLAUDE-ONLY: Available tools
  "mcp_servers": [...],              ← CLAUDE-ONLY: MCP server config
  "model": "claude-sonnet-4-5-20250929",  ← CLAUDE: Actual model ID
  "permissionMode": "default"
}
```

### Parser Strategy

```python
source = "cursor" if "apiKeySource" in data else "claude_cli"

if source == "cursor":
    model_selection = data["model"]  # "Auto"
    has_tools_info = False
else:  # claude_cli
    model_id = data["model"]         # "claude-sonnet-4-5-20250929"
    has_tools_info = True
    tools = data.get("tools", [])
    mcp_servers = data.get("mcp_servers", [])
```

---

## Example 2: User Input (Cursor Only)

### Cursor Output

```json
{
  "type": "user",
  "message": {
    "role": "user",
    "content": [
      {
        "type": "text",
        "text": "respond with just the word hello"
      }
    ]
  },
  "session_id": "472896b5-0079-411c-9c10-ec912453c2a4"
}
```

### Claude CLI Output

*(No user message is output - this is the key difference)*

### Parser Strategy

```python
if msg_type == "user":
    # Only Cursor outputs user messages
    source = "cursor"
    user_text = extract_text(msg["content"])
    return UserMessage(text=user_text)
else:
    # Claude CLI doesn't echo user input in the stream
    pass
```

---

## Example 3: Assistant Response

### Cursor Output

```json
{
  "type": "assistant",
  "message": {
    "role": "assistant",
    "content": [
      {
        "type": "text",
        "text": "hello"
      }
    ]
  },
  "session_id": "472896b5-0079-411c-9c10-ec912453c2a4"
}
```

### Claude CLI Output

```json
{
  "type": "assistant",
  "message": {
    "model": "claude-sonnet-4-5-20250929",  ← CLAUDE: Model that generated this
    "id": "msg_01SK5Tg5fgiQKQgQg8xCC2UE",  ← CLAUDE: Anthropic message ID
    "type": "message",                      ← CLAUDE: Type indicator
    "role": "assistant",
    "content": [
      {
        "type": "text",
        "text": "hello"
      }
    ],
    "stop_reason": null,                    ← CLAUDE: Why generation stopped
    "stop_sequence": null,                  ← CLAUDE: Stop sequence matched
    "usage": {                              ← CLAUDE: Token metrics
      "input_tokens": 15,
      "output_tokens": 1
    }
  }
}
```

### Parser Strategy

```python
def parse_assistant(msg_obj):
    message = msg_obj["message"]

    # Extract common fields
    content = extract_text(message.get("content", []))
    role = message.get("role")

    # Extract optional Claude CLI fields
    metadata = {
        "model": message.get("model"),
        "message_id": message.get("id"),
        "stop_reason": message.get("stop_reason"),
        "stop_sequence": message.get("stop_sequence"),
        "usage": message.get("usage", {})
    }

    # Filter out None values
    metadata = {k: v for k, v in metadata.items() if v is not None}

    return AssistantMessage(
        content=content,
        role=role,
        metadata=metadata
    )
```

---

## Example 4: Final Result

### Cursor Output

```json
{
  "type": "result",
  "subtype": "success",
  "duration_ms": 5182,                     ← Total time (including API)
  "duration_api_ms": 5182,                 ← API time (equal to total)
  "is_error": false,
  "result": "hello",                       ← CURSOR: The output value
  "session_id": "472896b5-0079-411c-9c10-ec912453c2a4",
  "request_id": "7b570630-9840-4846-a38d-1d8ca60621da"  ← CURSOR: Request ID
}
```

### Claude CLI Output

```json
{
  "type": "result",
  "subtype": "success",
  "is_error": false,
  "duration_ms": 2805,                     ← Total time
  "duration_api_ms": 2795,                 ← API time (separated)
  "num_turns": 1,                          ← CLAUDE: Conversation turns
  "result": "hello",
  "session_id": "...",
  "total_cost_usd": 0.07933785,            ← CLAUDE: Token cost
  "usage": {                               ← CLAUDE: Detailed breakdown
    "input_tokens": 15,
    "output_tokens": 1
  },
  "modelUsage": {...}                      ← CLAUDE: Model-specific metrics
}
```

### Parser Strategy

```python
def parse_result(data, source):
    result = {
        "is_error": data["is_error"],
        "total_ms": data["duration_ms"],
        "api_ms": data.get("duration_api_ms", data["duration_ms"]),
        "output": data.get("result"),
    }

    # Calculate overhead
    result["overhead_ms"] = result["total_ms"] - result["api_ms"]

    # Source-specific
    if source == "cursor":
        result["request_id"] = data["request_id"]
    else:  # claude_cli
        result["num_turns"] = data.get("num_turns", 1)
        result["cost_usd"] = data.get("total_cost_usd")
        result["usage"] = data.get("usage", {})
        result["model_usage"] = data.get("modelUsage", {})

    return result
```

---

## Timing Analysis Example

### Cursor
```
Total: 5182ms
API:   5182ms
Overhead: 0ms (rounded)
```

### Claude CLI
```
Total: 2805ms
API:   2795ms
Overhead: 10ms (local processing)
```

### Cost Calculation
```python
# Claude CLI includes this
cost_per_million_input = 0.003  # $3 per million
cost_per_million_output = 0.015 # $15 per million

input_tokens = 15
output_tokens = 1

estimated_cost = (
    (input_tokens / 1_000_000) * cost_per_million_input +
    (output_tokens / 1_000_000) * cost_per_million_output
)
# ≈ $0.000079

# Actual from result: $0.07933785
# (Note: May include API overhead or different pricing)
```

---

## Format Detection Algorithm

```python
def detect_source(first_line: str) -> str:
    """Detect whether output is from Cursor or Claude CLI"""
    data = json.loads(first_line)

    # Check for Cursor-specific fields in system message
    if data.get("type") == "system":
        if "apiKeySource" in data:
            return "cursor"

        if "tools" in data or "mcp_servers" in data:
            return "claude_cli"

    # Fallback: check second line
    raise ValueError("Cannot determine source from first line")
```

### Output

```
CURSOR:
{"type":"system","subtype":"init","apiKeySource":"login",...}
                                    ↑
                         Cursor indicator

CLAUDE CLI:
{"type":"system","subtype":"init",...,"tools":[...],"mcp_servers":[...]}
                                        ↑
                         Claude CLI indicator
```

---

## Content Extraction Pattern

Both formats use the same nested structure for content, but Claude CLI has additional metadata:

```
BOTH:
.message.content[i].type = "text"
.message.content[i].text = "hello"

CLAUDE CLI ONLY:
.message.usage.input_tokens
.message.usage.output_tokens
.message.stop_reason
.message.id
```

### Unified Extractor

```python
def extract_text(content: List[Dict]) -> str:
    """Extract text from content array (works for both formats)"""
    texts = []
    for item in content:
        if item.get("type") == "text":
            texts.append(item["text"])
    return "".join(texts)
```

---

## Common Pitfalls to Avoid

### Pitfall 1: Assuming User Messages

```python
# ❌ WRONG
messages = [m for m in stream if m["type"] == "user"]
print(messages)  # Empty for Claude CLI!

# ✅ CORRECT
if source == "cursor":
    user_messages = [m for m in stream if m["type"] == "user"]
```

### Pitfall 2: Model Field Comparison

```python
# ❌ WRONG
if data["model"] == "claude-sonnet":
    ...  # Fails for Cursor where model="Auto"

# ✅ CORRECT
model = data.get("model")
if source == "cursor":
    selection_mode = model
elif source == "claude_cli":
    actual_model = model
```

### Pitfall 3: Missing Optional Fields

```python
# ❌ WRONG
cost = data["total_cost_usd"]  # KeyError for Cursor

# ✅ CORRECT
cost = data.get("total_cost_usd")  # Returns None for Cursor
```

### Pitfall 4: Timing Granularity

```python
# ❌ WRONG - Assumes they're equal
api_time = data["duration_api_ms"]
overhead = data["duration_ms"] - api_time  # Always 0 for Cursor

# ✅ CORRECT
total = data["duration_ms"]
api = data.get("duration_api_ms", total)
overhead = total - api
```

---

## Test Vectors

### Test Case: Cursor Full Flow

```json
{"type":"system","subtype":"init","apiKeySource":"login","cwd":"/Users/alexrockwell/dev/worktrees/emdx-cursorify","session_id":"472896b5-0079-411c-9c10-ec912453c2a4","model":"Auto","permissionMode":"default"}
{"type":"user","message":{"role":"user","content":[{"type":"text","text":"respond with just the word hello"}]},"session_id":"472896b5-0079-411c-9c10-ec912453c2a4"}
{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"hello"}]},"session_id":"472896b5-0079-411c-9c10-ec912453c2a4"}
{"type":"result","subtype":"success","duration_ms":5182,"duration_api_ms":5182,"is_error":false,"result":"hello","session_id":"472896b5-0079-411c-9c10-ec912453c2a4","request_id":"7b570630-9840-4846-a38d-1d8ca60621da"}
```

### Test Case: Claude CLI Full Flow

```json
{"type":"system","subtype":"init","cwd":"/Users/alexrockwell/dev/worktrees/emdx-cursorify","session_id":"4318e3f4-0333-4e88-b253-fa0b89a7591a","tools":[...],"mcp_servers":[...],"model":"claude-sonnet-4-5-20250929","permissionMode":"default"}
{"type":"assistant","message":{"model":"claude-sonnet-4-5-20250929","id":"msg_01SK5Tg5fgiQKQgQg8xCC2UE","type":"message","role":"assistant","content":[{"type":"text","text":"hello"}],"stop_reason":null,"stop_sequence":null,"usage":{"input_tokens":15,"output_tokens":1}}}
{"type":"result","subtype":"success","is_error":false,"duration_ms":2805,"duration_api_ms":2795,"num_turns":1,"result":"hello","session_id":"...","total_cost_usd":0.07933785,"usage":{"input_tokens":15,"output_tokens":1},"modelUsage":{...}}
```

---

## Summary Table: What Each Format Includes

| Aspect | Cursor | Claude CLI | Both |
|--------|--------|-----------|------|
| System init | ✓ (apiKeySource) | ✓ (tools, mcp) | session_id, cwd, model |
| User messages | ✓ | ✗ | — |
| Assistant response | ✓ (basic) | ✓ (rich metadata) | content |
| Result message | ✓ (request_id) | ✓ (cost, tokens) | duration, is_error |
| Token tracking | ✗ | ✓ | — |
| Cost tracking | ✗ | ✓ | — |
| Message IDs | ✗ | ✓ | session_id |
| Stop reason | ✗ | ✓ | — |
| Tool definitions | ✗ | ✓ | — |

---

## Next Steps

1. **Implement the unified parser** using the strategies shown above
2. **Create test fixtures** from the test vectors
3. **Add source detection** to your CLI parser
4. **Handle both formats** transparently in downstream processing
5. **Log source** information for debugging
6. **Monitor for schema changes** in future releases
