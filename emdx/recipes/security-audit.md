---
inputs:
  - name: target
    description: What to audit (module, directory, or repo)
    required: true
  - name: severity
    description: Minimum severity to report
    default: medium
tags: [security, audit]
---

# Security Audit

## Step 1: Scan
Scan {{target}} for security vulnerabilities. Focus on:
- Authentication and authorization flaws
- Input validation and injection risks (SQL, XSS, command injection)
- Sensitive data exposure
- CORS and CSRF protections
- Error handling that leaks information

Report findings at {{severity}} severity and above.

## Step 2: Triage
Prioritize the findings by:
- Exploitability (how easy is it to exploit?)
- Impact (what's the blast radius?)
- Likelihood (how likely is this to be discovered?)

Group related findings and identify root causes.

## Step 3: Fix [--pr]
For each high-priority finding:
1. Create a fix that addresses the root cause
2. Add tests that verify the fix
3. Document what was fixed and why

Create a PR with all fixes grouped by category.
