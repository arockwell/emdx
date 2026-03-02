---
name: investigate
description: Deep-dive investigation into a topic — searches the KB, reads source code, identifies knowledge gaps, and produces a comprehensive analysis document saved to the KB with follow-up tasks.
---

# Investigate Topic

Conduct a thorough investigation of: **$ARGUMENTS**

## Process

### Phase 1: Search the Knowledge Base for Prior Art

Search the KB multiple ways to find everything that already exists on this topic.

**Keyword search:**
```bash
emdx find "$ARGUMENTS" -s
```

**Semantic search (catches conceptual matches that keyword search misses):**
```bash
emdx find "$ARGUMENTS" --mode semantic
```

**Tag-based search for related analysis and active work:**
```bash
emdx find --tags "analysis" -s
emdx find --tags "active" -s
```

**Recent documents (may contain ongoing work on this topic):**
```bash
emdx find --recent 10 -s
```

Read any relevant documents found:
```bash
emdx view <id>
```

Important: `emdx find` does NOT support OR/AND/NOT operators. Run separate find commands for each angle of the topic. Break compound topics into individual searches.

### Phase 2: Read Relevant Source Code

Go beyond the KB and examine the actual codebase. Use Grep, Glob, and Read tools to find code related to the topic.

- Search for relevant filenames, class names, function names, and constants
- Read key files to understand implementation details
- Trace data flows and call chains
- Look at tests for behavioral documentation
- Check git history for recent changes: `git log --oneline --all -- <relevant-paths> | head -20`

Focus on understanding:
- **How it works today** -- current implementation
- **Why it works that way** -- design decisions visible in code comments, commit messages, or structure
- **Where the boundaries are** -- interfaces, APIs, configuration points
- **What tests cover** -- what's verified vs assumed

### Phase 3: Identify Gaps

Compare what the KB knows against what the codebase reveals. Identify:

- **Undocumented decisions** -- architectural choices visible in code but not explained in the KB
- **Missing context** -- things a new developer would struggle with
- **Stale information** -- KB docs that contradict current code
- **Uncovered areas** -- code paths, modules, or behaviors with no KB documentation
- **Risks and concerns** -- potential issues discovered during investigation

### Phase 4: Synthesize Findings

Write a comprehensive analysis document with these sections:

```markdown
# Investigation: <topic>

## Prior Knowledge
What the KB already contains on this topic. Reference specific document IDs.
Note any contradictions or outdated information found.

## Codebase Analysis
What the source code reveals. Include specific file paths, function names,
and code patterns. Explain the current state of implementation.

## Gaps Identified
What's missing from the KB. Rank by importance:
- Critical gaps (would cause someone to make a wrong decision)
- Important gaps (would slow someone down significantly)
- Minor gaps (nice-to-have documentation)

## Recommendations
Concrete next steps:
- Documents that should be created or updated
- Code changes worth considering
- Further investigations needed
- Tasks to create for follow-up work
```

### Phase 5: Save to Knowledge Base

Save the analysis document:

```bash
echo "<analysis document>" | emdx save --title "Investigation: $ARGUMENTS" --tags "analysis,active"
```

### Phase 6: Create Follow-Up Tasks

For each actionable recommendation, create a task:

```bash
emdx task add "Title describing the work" -D "Details from the investigation" --cat FEAT
```

Use appropriate categories:
- `FEAT` for new features or capabilities
- `FIX` for bugs or issues discovered
- `ARCH` for refactoring or structural changes
- `DOCS` for documentation gaps
- `TEST` for missing test coverage

If there's an active epic related to the topic, add `--epic <id>`.

## Guidelines

- **Be thorough but focused**: Follow the topic wherever it leads, but don't pad with irrelevant findings
- **Cite sources**: Reference KB document IDs (`#42`) and file paths (`emdx/database/search.py:L45`) throughout
- **Distinguish fact from opinion**: Clearly mark observations vs interpretations vs recommendations
- **Quantify when possible**: "3 of 7 modules lack tests" is better than "some modules lack tests"
- **Think adversarially**: What could go wrong? What assumptions might be wrong? What edge cases exist?
- **Connect the dots**: The value of investigation is finding relationships between disparate pieces of information
- **Be honest about unknowns**: If something is unclear after investigation, say so -- that itself is a finding
