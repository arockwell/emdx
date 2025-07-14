You are creating an actionable gameplan from an analysis document.

Your task is to:
1. Extract the recommended approach from the analysis
2. Break it down into concrete implementation steps
3. Order steps by dependencies
4. Provide technical details for each step
5. Define success criteria

Format your response as a markdown document with these sections:
- Overview
- Implementation Steps (numbered, detailed)
- Technical Approach
- Testing Strategy
- Success Criteria
- Risk Mitigation

IMPORTANT:
- DO NOT implement anything - this is planning only
- DO NOT use Write, Edit, or MultiEdit tools  
- Be specific about file paths, function names, and test cases
- When your gameplan is complete, save it using this exact format:
  ```bash
  cat << 'EOF' | emdx save --title "Gameplan: [topic]" --tags "gameplan,active"
  Your full gameplan content here...
  Can span multiple lines...
  EOF
  ```
- Alternatively for shorter content: echo "single line content" | emdx save --title "Title" --tags "gameplan,active"
- Keep your gameplan under 10KB to ensure it can be piped

Analysis content:
---
{content}
---