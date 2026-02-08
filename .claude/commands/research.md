Use `emdx delegate` to research the following topic in parallel. Break the user's request into 3-8 focused sub-tasks and run them simultaneously.

```bash
emdx delegate --synthesize "sub-task 1" "sub-task 2" "sub-task 3" ...
```

User's research request: $ARGUMENTS

Guidelines:
- Break the request into independent, focused sub-tasks
- Each sub-task should investigate one specific aspect
- Use --synthesize to combine the results
- Results print to stdout — read them and continue the conversation
- Do NOT use Task subagents — use `emdx delegate` for parallel work
