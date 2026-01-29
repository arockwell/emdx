"""
Swarm Orchestrator - the brain of your battlestation.

This module coordinates parallel agent execution, manages worktrees,
collects results, and optionally synthesizes outputs.

This replaces/supersedes the workflow system with a simpler approach:
- Python runs the loop (reliable, debuggable)
- Claude agents are disposable compute (spawn, work, die)
- EMDX stores everything (survives restarts)
"""

import asyncio
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional
import uuid

from emdx.swarm.k8s import K3dCluster, ClusterConfig, PodStatus


@dataclass
class SwarmConfig:
    """Configuration for a swarm execution."""
    max_concurrent: int = 6  # How many agents at once
    memory_per_agent: str = "3Gi"
    cpu_per_agent: str = "2"
    timeout_per_task: int = 600  # 10 minutes default
    synthesize: bool = False  # Combine results at end
    save_to_emdx: bool = True
    tags: list[str] = field(default_factory=lambda: ["swarm-output"])
    worktree_base: Optional[str] = None  # Auto-detect from git
    image: str = "emdx/claude-agent:latest"


@dataclass
class AgentTask:
    """A task to be executed by an agent."""
    id: str
    prompt: str
    worktree: Optional[str] = None
    pod_name: Optional[str] = None
    status: str = "pending"  # pending, running, completed, failed
    result: Optional[str] = None
    error: Optional[str] = None
    duration: Optional[float] = None
    emdx_doc_id: Optional[int] = None


@dataclass
class SwarmResult:
    """Result of a swarm execution."""
    tasks: list[AgentTask]
    total_duration: float
    successful: int
    failed: int
    synthesis_doc_id: Optional[int] = None


class Swarm:
    """
    The swarm orchestrator - coordinates parallel agent execution.

    Usage:
        swarm = Swarm()
        result = swarm.run([
            "Fix all lint errors in src/",
            "Add tests for the auth module",
            "Document the API endpoints"
        ])
    """

    def __init__(
        self,
        config: Optional[SwarmConfig] = None,
        cluster: Optional[K3dCluster] = None
    ):
        self.config = config or SwarmConfig()
        self.cluster = cluster or K3dCluster()
        self._worktree_base = self._detect_worktree_base()

    def _detect_worktree_base(self) -> Path:
        """Detect the git repo root for worktree creation."""
        if self.config.worktree_base:
            return Path(self.config.worktree_base)

        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())

        return Path("/tmp/emdx-workspaces")

    def _setup_worktree(self, task_id: str) -> str:
        """Create a git worktree for an agent."""
        worktree_path = self._worktree_base.parent / f"swarm-{task_id}"

        # Get current branch
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True,
            cwd=self._worktree_base
        )
        current_branch = result.stdout.strip() if result.returncode == 0 else "main"

        # Create worktree
        subprocess.run([
            "git", "worktree", "add", "-b", f"swarm-{task_id}",
            str(worktree_path), current_branch
        ], capture_output=True, cwd=self._worktree_base)

        return str(worktree_path)

    def _cleanup_worktree(self, worktree_path: str):
        """Remove a git worktree."""
        subprocess.run([
            "git", "worktree", "remove", "--force", worktree_path
        ], capture_output=True, cwd=self._worktree_base)

    def _save_result_to_emdx(self, task: AgentTask) -> Optional[int]:
        """Save an agent's result to EMDX."""
        if not self.config.save_to_emdx or not task.result:
            return None

        # Use emdx save via subprocess
        tags_str = ",".join(self.config.tags)
        title = f"Swarm: {task.prompt[:50]}..."

        result = subprocess.run(
            ["emdx", "save", "--title", title, "--tags", tags_str],
            input=task.result,
            capture_output=True,
            text=True
        )

        # Parse doc ID from output (e.g., "✅ Saved as #5920:")
        if result.returncode == 0:
            import re
            match = re.search(r"#(\d+)", result.stdout)
            if match:
                return int(match.group(1))

        return None

    def _execute_task_in_pod(self, task: AgentTask) -> AgentTask:
        """Execute a single task in a k3d pod."""
        start_time = time.time()
        task.status = "running"

        try:
            # Setup worktree
            task.worktree = self._setup_worktree(task.id)

            # Create pod
            task.pod_name = self.cluster.create_agent_pod(
                task=task.prompt,
                worktree=task.worktree,
                image=self.config.image,
                memory=self.config.memory_per_agent,
                cpu=self.config.cpu_per_agent
            )

            # Wait for completion
            status = self.cluster.wait_for_pod(
                task.pod_name,
                timeout=self.config.timeout_per_task
            )

            # Get logs as result
            task.result = self.cluster.get_pod_logs(task.pod_name)

            if status.phase == "Succeeded":
                task.status = "completed"
                task.emdx_doc_id = self._save_result_to_emdx(task)
            else:
                task.status = "failed"
                task.error = f"Pod failed with exit code {status.exit_code}"

        except Exception as e:
            task.status = "failed"
            task.error = str(e)

        finally:
            task.duration = time.time() - start_time

            # Cleanup
            if task.pod_name:
                self.cluster.delete_pod(task.pod_name)
            if task.worktree:
                self._cleanup_worktree(task.worktree)

        return task

    def _execute_task_local(self, task: AgentTask) -> AgentTask:
        """Execute a single task locally (fallback when k3d not available)."""
        start_time = time.time()
        task.status = "running"

        try:
            # Setup worktree
            task.worktree = self._setup_worktree(task.id)

            # Run claude directly
            result = subprocess.run(
                ["claude", "-p", task.prompt, "--output-format", "text"],
                capture_output=True,
                text=True,
                cwd=task.worktree,
                timeout=self.config.timeout_per_task
            )

            task.result = result.stdout
            if result.returncode == 0:
                task.status = "completed"
                task.emdx_doc_id = self._save_result_to_emdx(task)
            else:
                task.status = "failed"
                task.error = result.stderr

        except subprocess.TimeoutExpired:
            task.status = "failed"
            task.error = "Task timed out"

        except Exception as e:
            task.status = "failed"
            task.error = str(e)

        finally:
            task.duration = time.time() - start_time

            # Cleanup worktree
            if task.worktree:
                self._cleanup_worktree(task.worktree)

        return task

    def _synthesize_results(self, tasks: list[AgentTask]) -> Optional[int]:
        """Synthesize all results into a single document."""
        if not self.config.synthesize:
            return None

        successful_tasks = [t for t in tasks if t.status == "completed" and t.result]
        if not successful_tasks:
            return None

        # Build synthesis prompt
        combined = "\n\n---\n\n".join([
            f"## Task: {t.prompt}\n\n{t.result}"
            for t in successful_tasks
        ])

        synthesis_prompt = f"""Synthesize and summarize the following results from parallel agent executions:

{combined}

Provide:
1. Key findings across all tasks
2. Common themes or patterns
3. Actionable recommendations
4. Any conflicts or inconsistencies between results"""

        # Run synthesis via claude
        result = subprocess.run(
            ["claude", "-p", synthesis_prompt, "--output-format", "text"],
            capture_output=True,
            text=True,
            timeout=300
        )

        if result.returncode != 0:
            return None

        # Save synthesis to EMDX
        save_result = subprocess.run(
            ["emdx", "save", "--title", "Swarm Synthesis", "--tags", "swarm-synthesis"],
            input=result.stdout,
            capture_output=True,
            text=True
        )

        import re
        match = re.search(r"#(\d+)", save_result.stdout)
        return int(match.group(1)) if match else None

    def run(
        self,
        prompts: list[str],
        use_k3d: bool = True,
        progress_callback: Optional[Callable[[AgentTask], None]] = None
    ) -> SwarmResult:
        """
        Run multiple tasks in parallel.

        Args:
            prompts: List of task prompts for agents
            use_k3d: Whether to use k3d pods (False = local subprocesses)
            progress_callback: Called when each task completes

        Returns:
            SwarmResult with all task outcomes
        """
        start_time = time.time()

        # Create tasks
        tasks = [
            AgentTask(id=uuid.uuid4().hex[:8], prompt=prompt)
            for prompt in prompts
        ]

        # Choose executor
        execute_fn = self._execute_task_in_pod if use_k3d else self._execute_task_local

        # Ensure cluster is running if using k3d
        if use_k3d:
            if not self.cluster.is_running():
                print("Starting k3d cluster...")
                self.cluster.start()

        # Execute in parallel with thread pool
        completed_tasks = []
        with ThreadPoolExecutor(max_workers=self.config.max_concurrent) as executor:
            futures = {executor.submit(execute_fn, task): task for task in tasks}

            for future in as_completed(futures):
                task = future.result()
                completed_tasks.append(task)

                if progress_callback:
                    progress_callback(task)

        # Synthesize if requested
        synthesis_doc_id = self._synthesize_results(completed_tasks)

        return SwarmResult(
            tasks=completed_tasks,
            total_duration=time.time() - start_time,
            successful=sum(1 for t in completed_tasks if t.status == "completed"),
            failed=sum(1 for t in completed_tasks if t.status == "failed"),
            synthesis_doc_id=synthesis_doc_id
        )

    def status(self) -> dict:
        """Get current swarm status."""
        pods = self.cluster.list_agent_pods()

        running = [p for p in pods if p.phase == "Running"]
        pending = [p for p in pods if p.phase == "Pending"]
        completed = [p for p in pods if p.phase == "Succeeded"]
        failed = [p for p in pods if p.phase == "Failed"]

        return {
            "cluster_running": self.cluster.is_running(),
            "running_agents": len(running),
            "pending_agents": len(pending),
            "completed_agents": len(completed),
            "failed_agents": len(failed),
            "pods": pods
        }
