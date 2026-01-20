# Cursor vs Claude CLI: Complete Analysis & Parser Implementation

A comprehensive guide for understanding and parsing JSON output from both Cursor and Claude CLI, with production-ready Python implementations.

---

## Document Overview

This analysis consists of four interconnected documents:

### 1. **[cursor-vs-claude-cli-json.md](cursor-vs-claude-cli-json.md)** - Structural Comparison
**Best for:** Understanding the high-level differences between formats

Contains:
- Executive summary of key differences
- Detailed comparison tables
  - Common fields (work identically)
  - Fields unique to Claude CLI
  - Fields unique to Cursor
  - Same field names with different structures
- Compatibility implications with examples
- Unified parser design overview
- Parser compatibility matrix

**Key sections:**
- "Parser Compatibility Matrix" - Shows data flow differences
- "Compatibility Implications" - 4 major challenges with solutions
- "Unified Parser Design" - High-level architecture

**Read this first if:** You want to understand the big picture.

---

### 2. **[cursor-vs-claude-cli-examples.md](cursor-vs-claude-cli-examples.md)** - Annotated Examples
**Best for:** Seeing concrete JSON examples with explanations

Contains:
- Side-by-side JSON output from both tools
- Line-by-line annotations showing differences
- Complete example flows (init → response → result)
- Parser strategy code snippets for each example
- Timing analysis
- Format detection algorithms
- Common pitfalls to avoid (with correct solutions)
- Test vectors for validation

**Key sections:**
- "Example 1-4" - Complete flows with annotations
- "Parser Strategy" - Code for each example
- "Common Pitfalls" - Shows ❌ wrong vs ✅ right patterns
- "Test Vectors" - Copy-paste JSON for testing

**Read this second if:** You're building a parser or want concrete examples.

---

### 3. **[cursor-vs-claude-cli-parser.md](cursor-vs-claude-cli-parser.md)** - Implementation
**Best for:** Copy-paste production code

Contains:
- Complete data models (dataclasses)
- Source detection class
- Unified NDJSON parser class
- 4 usage examples (file processing, streaming, etc.)
- Callback-based stream processor
- Comprehensive unit tests
- Integration checklist
- Performance characteristics

**Key sections:**
- "Data Models" - Ready-to-use dataclasses
- "UnifiedNDJSONParser" - Main parser class
- "Usage Examples" - Copy-paste ready
- "TestUnifiedParser" - Full test suite

**Read this if:** You need to implement the parser.

---

### 4. **This Document (README)**
Navigation guide and quick reference

---

## Quick Decision Tree

```
What do you need to do?

1. Understand the differences
   → Read: cursor-vs-claude-cli-json.md
   → Section: "Detailed Comparison Table"

2. See concrete examples
   → Read: cursor-vs-claude-cli-examples.md
   → Section: "Example 1: System Initialization"

3. Build a parser
   → Read: cursor-vs-claude-cli-parser.md
   → Section: "Complete Implementation"
   → Copy: UnifiedNDJSONParser class

4. Debug parser issues
   → Read: cursor-vs-claude-cli-examples.md
   → Section: "Common Pitfalls to Avoid"

5. Find test vectors
   → Read: cursor-vs-claude-cli-examples.md
   → Section: "Test Vectors"

6. Understand timing
   → Read: cursor-vs-claude-cli-examples.md
   → Section: "Timing Analysis Example"
```

---

## Key Differences At A Glance

| Aspect | Cursor | Claude CLI | Impact |
|--------|--------|-----------|--------|
| **Format** | NDJSON | NDJSON | Same |
| **Message Types** | 4 (init, user, assistant, result) | 3 (init, assistant, result) | User messages only in Cursor |
| **Model Field** | `"Auto"` (mode) | `"claude-sonnet-4-5-20250929"` (ID) | Different semantics |
| **Auth Info** | `apiKeySource` field | No equivalent | Use field presence to detect |
| **Token Tracking** | Not included | Included in messages & result | Cost tracking in Claude only |
| **Message IDs** | No | Yes (Anthropic IDs) | Use for tracing |
| **Timing** | `duration_ms` ≈ `duration_api_ms` | Separated (overhead visible) | API vs total time |
| **Cost Tracking** | No | Yes (`total_cost_usd`) | Financial data only in Claude |

---

## Implementation Path

### Minimum Viable Implementation (5 minutes)

```python
# Detect source from first line
def detect_source(first_line):
    data = json.loads(first_line)
    if "apiKeySource" in data:
        return "cursor"
    elif "tools" in data:
        return "claude_cli"

# Extract text from both formats
def extract_text(content):
    return "".join(item["text"] for item in content if item.get("type") == "text")

# Process stream
for line in stream:
    data = json.loads(line)
    if data["type"] == "assistant":
        text = extract_text(data["message"]["content"])
        print(text)
```

### Recommended Implementation (30 minutes)

Copy the `UnifiedNDJSONParser` class from [cursor-vs-claude-cli-parser.md](cursor-vs-claude-cli-parser.md) and use:

```python
parser = UnifiedNDJSONParser(auto_detect=True)
with open("output.ndjson") as f:
    for message in parser.parse_stream(f):
        print(f"{type(message).__name__}: {message}")
```

### Production Implementation (with tests)

Include the complete implementation from [cursor-vs-claude-cli-parser.md](cursor-vs-claude-cli-parser.md):
- Data models
- Source detection
- Parser class
- Stream processor
- Unit tests

---

## Source Detection

Two reliable methods:

### Method 1: Check for Cursor-Specific Field
```python
data = json.loads(first_line)
if "apiKeySource" in data:
    return "cursor"
```

### Method 2: Check for Claude CLI-Specific Fields
```python
if "tools" in data or "mcp_servers" in data:
    return "claude_cli"
```

**Both check the `system/init` message (first line).**

---

## Common Integration Points

### Logging the Source

```python
parser = UnifiedNDJSONParser(auto_detect=True)
messages = parser.parse_stream(stream)

if parser.source == Source.CURSOR:
    logger.info("Processing Cursor output")
else:
    logger.info("Processing Claude CLI output")
```

### Handling Source-Specific Fields

```python
for message in messages:
    if isinstance(message, ResultMessage):
        if parser.source == Source.CURSOR:
            # Use Cursor fields
            request_id = message.request_id
        else:
            # Use Claude CLI fields
            cost = message.cost_usd
            tokens = message.input_tokens
```

### Extracting Results

```python
# Both formats have this
result_text = result_message.result

# Claude CLI has additional metadata
if result_message.cost_usd:
    log(f"Cost: ${result_message.cost_usd}")
```

---

## Testing Your Parser

### 1. Use Provided Test Vectors

Copy JSON from "Test Vectors" section in [cursor-vs-claude-cli-examples.md](cursor-vs-claude-cli-examples.md)

```python
cursor_ndjson = """{"type":"system",...}
{"type":"user",...}
{"type":"assistant",...}
{"type":"result",...}"""

parser = UnifiedNDJSONParser()
messages = list(parser.parse_stream(cursor_ndjson.split("\n")))
assert len(messages) == 4
```

### 2. Run with Real Data

```bash
# Generate test output
cursor api "hello"
python -c "
import json
with open('cursor.ndjson') as f:
    for line in f:
        data = json.loads(line)
        print(f'{data[\"type\"]}: OK' if data else 'FAIL')
"
```

### 3. Compare Outputs

```bash
# See what each CLI produces
cursor api "test" > cursor_output.ndjson
claude api "test" > claude_output.ndjson
diff -u cursor_output.ndjson claude_output.ndjson
```

---

## Troubleshooting

### "Cannot determine source"

**Cause:** First message is not `type: "system"`

**Solution:** Ensure stream starts with system init message

```python
# ✓ Correct
{"type":"system",...}  ← First line

# ✗ Wrong
{"type":"assistant",...}  ← Can't detect
```

### Parser says "Unknown message type"

**Cause:** Field contains unexpected value

**Solution:** Check actual CLI output format:

```bash
# See raw output
cursor api "test" | head -20
```

### Missing token data in Cursor

**Cause:** Cursor doesn't output tokens

**Solution:** Handle None values:

```python
if message.input_tokens is not None:
    print(f"Tokens: {message.input_tokens}")
```

### Timing difference confuses results

**Cause:** Cursor shows `duration_ms` ≈ `duration_api_ms`, Claude CLI separates them

**Solution:** Calculate overhead:

```python
overhead = message.duration_ms - message.api_duration_ms
print(f"Total: {message.duration_ms}ms (API: {message.api_duration_ms}ms, Overhead: {overhead}ms)")
```

---

## Performance Notes

### Parsing Speed
- Detect source: <1ms
- Parse 100 messages: ~5ms
- Extract text: <1ms per message

### Memory Usage
- Minimal for streaming (no buffering required)
- Each message object: ~500 bytes
- Test with 1000+ message streams

### Optimization Tips

1. **Use generators** for large files
```python
# ✓ Streaming
for message in parser.parse_stream(f):
    process(message)

# ✗ Buffering
messages = list(parser.parse_stream(f))  # Loads all into memory
```

2. **Skip text extraction** if not needed
```python
# Faster if you only need message type
msg_type = data["type"]
```

3. **Batch processing** for multiple files
```python
for file in files:
    parser = UnifiedNDJSONParser()  # Reuse source detection
    for message in parser.parse_stream(open(file)):
        process(message)
```

---

## API Reference Quick Links

| Class | Purpose | Location |
|-------|---------|----------|
| `SystemMessage` | Init message | parser.md § Data Models |
| `UserMessage` | User input | parser.md § Data Models |
| `AssistantMessage` | AI response | parser.md § Data Models |
| `ResultMessage` | Completion | parser.md § Data Models |
| `SourceDetector` | Detect format | parser.md § Source Detection |
| `UnifiedNDJSONParser` | Main parser | parser.md § Parser Implementation |
| `StreamProcessor` | Callback handler | parser.md § Advanced |

---

## Field Mapping Reference

### Fields Present in Both

```
type              → Message classification
session_id        → Session tracking
duration_ms       → Total elapsed time
is_error          → Success indicator
```

### Cursor-Only Fields

```
subtype              → "init", "success"
apiKeySource         → "login"
model                → "Auto" (in init)
permissionMode       → "default"
request_id           → Request UUID
result               → Output value
```

### Claude CLI-Only Fields

```
tools                → Available tools (in init)
mcp_servers          → MCP config (in init)
model                → "claude-sonnet-4-5-..." (actual model)
id                   → Anthropic message ID (in assistant)
stop_reason          → Why generation stopped
stop_sequence        → Stop sequence matched
usage                → {"input_tokens": ..., "output_tokens": ...}
num_turns            → Conversation turns
total_cost_usd       → Token cost
modelUsage           → Model-specific metrics
```

---

## Examples By Use Case

### Use Case 1: "I want to extract just the text response"

→ See [cursor-vs-claude-cli-parser.md](cursor-vs-claude-cli-parser.md) § "Usage Examples" → Example 1

```python
parser = UnifiedNDJSONParser()
for msg in parser.parse_stream(f):
    if isinstance(msg, AssistantMessage):
        print(msg.content)
```

### Use Case 2: "I need to track API costs"

→ See [cursor-vs-claude-cli-examples.md](cursor-vs-claude-cli-examples.md) § "Example 4: Final Result"

```python
if isinstance(msg, ResultMessage) and msg.cost_usd:
    total_cost += msg.cost_usd
```

### Use Case 3: "I'm debugging a parsing failure"

→ See [cursor-vs-claude-cli-examples.md](cursor-vs-claude-cli-examples.md) § "Common Pitfalls to Avoid"

```python
# Look for these exact patterns in examples
# ❌ WRONG vs ✅ CORRECT
```

### Use Case 4: "I need to write unit tests"

→ See [cursor-vs-claude-cli-parser.md](cursor-vs-claude-cli-parser.md) § "Testing"

```python
# Copy TestUnifiedParser class and test vectors
# From: cursor-vs-claude-cli-examples.md § "Test Vectors"
```

### Use Case 5: "I need to process both formats transparently"

→ See [cursor-vs-claude-cli-parser.md](cursor-vs-claude-cli-parser.md) § "Advanced: Streaming with Callbacks"

```python
processor = StreamProcessor(on_result=handle_result)
processor.process(stream)
```

---

## Format Evolution Monitoring

Since both formats may change, monitor for:

1. **New message types** - Add to `MessageType` enum
2. **New optional fields** - Use `.get()` for safe access
3. **Changed field meanings** - Check `model` field semantics
4. **New output types** - Tool results, etc.

Track in git with test vectors:

```bash
git add docs/cursor-vs-claude-cli-examples.md  # Test vectors
git commit -m "Update test vectors for Cursor v2.0"
```

---

## Document Statistics

| Document | Lines | Purpose |
|----------|-------|---------|
| cursor-vs-claude-cli-json.md | 348 | Structural comparison & analysis |
| cursor-vs-claude-cli-examples.md | 437 | Annotated JSON examples |
| cursor-vs-claude-cli-parser.md | 581 | Production-ready implementation |
| **Total** | **1,366** | **Complete reference** |

---

## Navigation by Task

| Task | Document | Section |
|------|----------|---------|
| Understand differences | json.md | "Detailed Comparison Table" |
| See examples | examples.md | "Example 1-4" |
| Implement parser | parser.md | "Complete Implementation" |
| Test parser | parser.md | "Testing" |
| Find test data | examples.md | "Test Vectors" |
| Debug issues | examples.md | "Common Pitfalls" |
| Integrate into code | parser.md | "Usage Examples" |
| Handle errors | examples.md | "Common Pitfalls" |
| Track costs | examples.md | "Cost Calculation" |
| Measure timing | examples.md | "Timing Analysis" |

---

## Contributing & Maintenance

### To Update This Reference

1. Run actual CLIs to capture new output formats
2. Update examples in `cursor-vs-claude-cli-examples.md`
3. Update parser in `cursor-vs-claude-cli-parser.md`
4. Update tests with new test vectors
5. Commit with message: `docs: Update Cursor/Claude CLI format analysis`

### To Report Discrepancies

Include:
- Output from your CLI
- Expected vs actual parsing result
- Both Cursor and Claude CLI versions

---

## See Also

- **AI System Documentation**: [docs/ai-system.md](ai-system.md)
- **CLI Reference**: [docs/cli-api.md](cli-api.md)
- **Architecture**: [docs/architecture.md](architecture.md)

---

## Summary

You now have:

1. ✅ **Complete structural analysis** (json.md)
2. ✅ **Concrete JSON examples** (examples.md)
3. ✅ **Production-ready code** (parser.md)
4. ✅ **Navigation guide** (this README)

**Next step:** Open [cursor-vs-claude-cli-json.md](cursor-vs-claude-cli-json.md) for the quick summary, or jump to [cursor-vs-claude-cli-parser.md](cursor-vs-claude-cli-parser.md) if you need code.

---

**Last Updated:** 2026-01-19
**Documents:** 4 interconnected markdown files
**Total Content:** 1,366 lines + Python code examples
