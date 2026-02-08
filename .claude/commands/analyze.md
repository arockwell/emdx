Use `emdx delegate` to analyze files or code matching the user's request. Discover targets dynamically and process them in parallel.

```bash
# Analyze specific aspects in parallel
emdx delegate --synthesize "aspect 1" "aspect 2" "aspect 3" --tags analysis
```

User's analysis request: $ARGUMENTS

Guidelines:
- Break the analysis into independent, focused sub-tasks
- Use --synthesize to combine results into a single summary
- Use --tags to categorize the output (e.g., analysis, security, performance)
- Results print to stdout — read them and continue the conversation
- Do NOT use Task subagents — use `emdx delegate` for parallel work
