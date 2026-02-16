---
inputs:
  - name: idea
    description: The idea or feature to implement
    required: true
tags: [recipe-output, implementation]
---

# Idea to PR

## Step 1: Refine
Convert this raw idea into a well-formed, detailed prompt that could be
given to an AI coding assistant. Be specific about requirements, constraints,
and expected outcomes.

Idea to refine:

{{idea}}

## Step 2: Analyze
Analyze the prompt thoroughly. Consider:
- What is being asked, explicitly and implicitly?
- What are the technical requirements?
- What are potential challenges or edge cases?
- What context or information is needed from the codebase?

## Step 3: Plan
Based on the analysis, create a detailed implementation gameplan:
- Step-by-step implementation plan
- Files that need to be created or modified
- Key design decisions and trade-offs
- Testing approach
- Potential risks and mitigations

## Step 4: Implement [--pr, --timeout 1800]
Implement the gameplan:
1. Write the actual code changes
2. Create a new git branch for this work
3. Make commits as you go with clear messages
4. When done, create a Pull Request using `gh pr create`
5. Report the PR URL at the end of your output
