# EMDX Claude Agent Container
#
# This container runs inside k3d pods for isolated agent execution.
# It has Claude Code CLI, git, and gh installed.
#
# Build:
#   docker build -t emdx/claude-agent:latest -f emdx/swarm/Dockerfile .
#
# The container expects these environment variables:
#   TASK - The task/prompt for Claude to execute
#   WORKTREE - Path to the git worktree (mounted at /workspaces)
#   EMDX_HOST - Host for saving results (usually host.k3d.internal)
#
# Optional:
#   ANTHROPIC_API_KEY - For Claude API access
#   GITHUB_TOKEN - For gh CLI operations
#   EMDX_TAGS - Comma-separated tags for output

FROM python:3.13-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    jq \
    && rm -rf /var/lib/apt/lists/*

# Install GitHub CLI
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update \
    && apt-get install -y gh \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI via npm (it's a node package)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g @anthropic-ai/claude-code \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies for the agent script
RUN pip install --no-cache-dir requests

# Copy the agent script
COPY emdx/swarm/agent.py /agent.py

# Set up workspace
WORKDIR /workspaces

# The entrypoint runs the agent script
ENTRYPOINT ["python", "/agent.py"]
