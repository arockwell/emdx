You are analyzing a note to create a structured analysis document.

Your task is to:
1. Understand the core problem or idea presented
2. Break it down into clear components
3. Identify requirements and constraints
4. Analyze potential solutions
5. Provide a recommendation

Format your response as a markdown document with these sections:
- Executive Summary
- Problem Breakdown
- Requirements & Constraints
- Solution Analysis (with pros/cons)
- Recommended Approach
- Implementation Considerations

IMPORTANT: 
- DO NOT write any code files or implementations
- DO NOT use Write, Edit, or MultiEdit tools
- When your analysis is complete, save it using this exact format:
  ```bash
  cat << 'EOF' | emdx save --title "Analysis: [topic]" --tags "analysis"
  Your full analysis content here...
  Can span multiple lines...
  EOF
  ```
- Alternatively for shorter content: echo "single line content" | emdx save --title "Title" --tags "analysis"
- Keep your analysis under 10KB to ensure it can be piped

Note content to analyze:
---
{content}
---