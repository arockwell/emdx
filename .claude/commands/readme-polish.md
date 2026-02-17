# README Polish

Iterative README improvement — make the document build progressively.

## Approach

$ARGUMENTS is optional focus area (e.g., "hero section", "delegate section").

### 1. Read Current State
Read README.md and identify the document's rhythm:
- Which sections build and flow?
- Which sections are flat command lists?
- What does the reader already know by the time they reach each section?

### 2. Identify Problems
Common README anti-patterns:
- **Flat lists**: Section is just commands with comments, no progression
- **Repetition**: Section re-shows what the hero already demonstrated
- **No payoff**: Commands shown without output — reader can't see what they get
- **Disconnected examples**: Each command is independent, no narrative thread

### 3. Rewrite with Progressive Rhythm
Each section should build beat by beat:
- Start simple, add complexity with each step
- Show output so the reader sees the payoff
- Later sections go *deeper* than earlier ones, not wider
- Use `$` prompts and realistic output (✅, 📋, 🔍, 🔀)
- Comments should narrate what's happening, not describe the flag

### 4. Check Flow Between Sections
After rewriting, read the full doc top to bottom:
- Does each section assume knowledge from the previous one?
- Is anything repeated between hero and body sections?
- Does the document reward continued reading?

### 5. Push and Iterate
Commit, push, present the diff to the user for feedback.
Expect 2-3 rounds of iteration — that's the process working.

## Anti-patterns
- Don't add `<details>` collapsible sections — content is either worth showing or not
- Don't use generic examples like "t1" "t2" "t3" when a realistic example would be clearer
- Don't show commands without output when the output is the selling point
