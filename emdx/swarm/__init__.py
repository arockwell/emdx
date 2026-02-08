"""
EMDX Swarm - k3d-based parallel agent execution.

This module provides the battlestation architecture for running multiple
Claude Code agents in isolated k3d pods. It replaces/supersedes the
workflow system with a simpler, more powerful approach.

Architecture:
- Python orchestrator runs on host (the loop)
- Claude agents run in k3d pods (disposable compute)
- EMDX stores all results (persistent memory)
- Git worktrees provide isolation (each agent gets one)

Key concepts:
- Swarm: A collection of parallel agent tasks
- Agent Pod: Isolated container running Claude Code
- Worktree: Git worktree mounted into the pod
- Result: Output saved to EMDX after agent completes
"""

from emdx.swarm.orchestrator import Swarm, SwarmConfig
from emdx.swarm.k8s import K3dCluster

__all__ = ["Swarm", "SwarmConfig", "K3dCluster"]
