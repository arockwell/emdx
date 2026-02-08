"""
Kubernetes/k3d cluster management for EMDX Swarm.

Handles cluster lifecycle, pod creation, and resource management.
Designed for local k3d clusters on beefy laptops (48GB+ RAM).
"""

import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import uuid


@dataclass
class ClusterConfig:
    """Configuration for the k3d cluster."""
    name: str = "emdx-battlestation"
    agents: int = 2  # k3d worker nodes
    memory_limit: str = "32Gi"  # Total memory for agents
    cpu_limit: str = "12"  # Total CPUs for agents
    max_pods: int = 15  # Max concurrent agent pods
    workspaces_path: str = "/tmp/emdx-workspaces"
    namespace: str = "emdx-agents"


@dataclass
class PodStatus:
    """Status of an agent pod."""
    name: str
    phase: str  # Pending, Running, Succeeded, Failed
    start_time: Optional[str] = None
    container_status: Optional[str] = None
    exit_code: Optional[int] = None


class K3dCluster:
    """
    Manages a local k3d cluster for running agent pods.

    This is your battlestation's infrastructure layer.
    """

    def __init__(self, config: Optional[ClusterConfig] = None):
        self.config = config or ClusterConfig()
        self._ensure_workspaces_dir()

    def _ensure_workspaces_dir(self):
        """Create the workspaces directory if it doesn't exist."""
        Path(self.config.workspaces_path).mkdir(parents=True, exist_ok=True)

    def _run(self, cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
        """Run a command and return the result."""
        return subprocess.run(cmd, capture_output=True, text=True, check=check)

    def exists(self) -> bool:
        """Check if the cluster exists."""
        result = self._run(["k3d", "cluster", "list", "-o", "json"], check=False)
        if result.returncode != 0:
            return False
        clusters = json.loads(result.stdout)
        return any(c["name"] == self.config.name for c in clusters)

    def is_running(self) -> bool:
        """Check if the cluster is running."""
        result = self._run(["k3d", "cluster", "list", "-o", "json"], check=False)
        if result.returncode != 0:
            return False
        clusters = json.loads(result.stdout)
        for c in clusters:
            if c["name"] == self.config.name:
                # Check if servers are running
                return c.get("serversRunning", 0) > 0
        return False

    def create(self) -> bool:
        """Create the k3d cluster."""
        if self.exists():
            print(f"Cluster '{self.config.name}' already exists")
            return True

        cmd = [
            "k3d", "cluster", "create", self.config.name,
            "--agents", str(self.config.agents),
            "--volume", f"{self.config.workspaces_path}:/workspaces@all",
            "--wait",
        ]

        result = self._run(cmd, check=False)
        if result.returncode != 0:
            print(f"Failed to create cluster: {result.stderr}")
            return False

        # Create namespace and resource quota
        self._setup_namespace()
        return True

    def _setup_namespace(self):
        """Set up the namespace and resource quotas."""
        # Create namespace
        self._run([
            "kubectl", "create", "namespace", self.config.namespace
        ], check=False)

        # Apply resource quota
        quota = {
            "apiVersion": "v1",
            "kind": "ResourceQuota",
            "metadata": {
                "name": "agent-quota",
                "namespace": self.config.namespace
            },
            "spec": {
                "hard": {
                    "requests.memory": self.config.memory_limit,
                    "requests.cpu": self.config.cpu_limit,
                    "pods": str(self.config.max_pods)
                }
            }
        }

        self._run([
            "kubectl", "apply", "-f", "-"
        ], check=False)

    def start(self) -> bool:
        """Start a stopped cluster."""
        if not self.exists():
            return self.create()

        if self.is_running():
            return True

        result = self._run([
            "k3d", "cluster", "start", self.config.name
        ], check=False)
        return result.returncode == 0

    def stop(self) -> bool:
        """Stop the cluster (preserves state)."""
        if not self.is_running():
            return True

        result = self._run([
            "k3d", "cluster", "stop", self.config.name
        ], check=False)
        return result.returncode == 0

    def delete(self) -> bool:
        """Delete the cluster entirely."""
        if not self.exists():
            return True

        result = self._run([
            "k3d", "cluster", "delete", self.config.name
        ], check=False)
        return result.returncode == 0

    def create_agent_pod(
        self,
        task: str,
        worktree: str,
        image: str = "emdx/claude-agent:latest",
        memory: str = "3Gi",
        cpu: str = "2",
        env: Optional[dict] = None,
    ) -> str:
        """
        Create an agent pod for a task.

        Returns the pod name.
        """
        pod_name = f"agent-{uuid.uuid4().hex[:8]}"

        env_vars = [
            {"name": "TASK", "value": task},
            {"name": "WORKTREE", "value": worktree},
            {"name": "EMDX_HOST", "value": "host.k3d.internal"},
        ]
        if env:
            env_vars.extend([{"name": k, "value": v} for k, v in env.items()])

        manifest = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": pod_name,
                "namespace": self.config.namespace,
                "labels": {
                    "app": "emdx-agent",
                    "task-id": pod_name,
                }
            },
            "spec": {
                "restartPolicy": "Never",
                "containers": [{
                    "name": "claude",
                    "image": image,
                    "env": env_vars,
                    "volumeMounts": [{
                        "name": "workspaces",
                        "mountPath": "/workspaces"
                    }],
                    "resources": {
                        "requests": {"memory": memory, "cpu": "1"},
                        "limits": {"memory": memory, "cpu": cpu}
                    }
                }],
                "volumes": [{
                    "name": "workspaces",
                    "hostPath": {"path": "/workspaces"}
                }]
            }
        }

        result = subprocess.run(
            ["kubectl", "apply", "-f", "-"],
            input=json.dumps(manifest),
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            raise RuntimeError(f"Failed to create pod: {result.stderr}")

        return pod_name

    def get_pod_status(self, pod_name: str) -> Optional[PodStatus]:
        """Get the status of a pod."""
        result = self._run([
            "kubectl", "get", "pod", pod_name,
            "-n", self.config.namespace,
            "-o", "json"
        ], check=False)

        if result.returncode != 0:
            return None

        pod = json.loads(result.stdout)
        status = pod.get("status", {})

        container_statuses = status.get("containerStatuses", [])
        container_status = None
        exit_code = None

        if container_statuses:
            cs = container_statuses[0]
            if "running" in cs.get("state", {}):
                container_status = "running"
            elif "terminated" in cs.get("state", {}):
                container_status = "terminated"
                exit_code = cs["state"]["terminated"].get("exitCode")
            elif "waiting" in cs.get("state", {}):
                container_status = "waiting"

        return PodStatus(
            name=pod_name,
            phase=status.get("phase", "Unknown"),
            start_time=status.get("startTime"),
            container_status=container_status,
            exit_code=exit_code
        )

    def get_pod_logs(self, pod_name: str, follow: bool = False) -> str:
        """Get logs from a pod."""
        cmd = [
            "kubectl", "logs", pod_name,
            "-n", self.config.namespace
        ]
        if follow:
            cmd.append("-f")

        result = self._run(cmd, check=False)
        return result.stdout

    def delete_pod(self, pod_name: str) -> bool:
        """Delete a pod."""
        result = self._run([
            "kubectl", "delete", "pod", pod_name,
            "-n", self.config.namespace,
            "--grace-period=5"
        ], check=False)
        return result.returncode == 0

    def list_agent_pods(self) -> list[PodStatus]:
        """List all agent pods."""
        result = self._run([
            "kubectl", "get", "pods",
            "-n", self.config.namespace,
            "-l", "app=emdx-agent",
            "-o", "json"
        ], check=False)

        if result.returncode != 0:
            return []

        pods = json.loads(result.stdout).get("items", [])
        statuses = []

        for pod in pods:
            status = pod.get("status", {})
            container_statuses = status.get("containerStatuses", [])

            container_status = None
            exit_code = None

            if container_statuses:
                cs = container_statuses[0]
                if "running" in cs.get("state", {}):
                    container_status = "running"
                elif "terminated" in cs.get("state", {}):
                    container_status = "terminated"
                    exit_code = cs["state"]["terminated"].get("exitCode")
                elif "waiting" in cs.get("state", {}):
                    container_status = "waiting"

            statuses.append(PodStatus(
                name=pod["metadata"]["name"],
                phase=status.get("phase", "Unknown"),
                start_time=status.get("startTime"),
                container_status=container_status,
                exit_code=exit_code
            ))

        return statuses

    def cleanup_completed_pods(self) -> int:
        """Delete all completed/failed pods. Returns count deleted."""
        pods = self.list_agent_pods()
        deleted = 0

        for pod in pods:
            if pod.phase in ("Succeeded", "Failed"):
                if self.delete_pod(pod.name):
                    deleted += 1

        return deleted

    def wait_for_pod(self, pod_name: str, timeout: int = 600) -> PodStatus:
        """Wait for a pod to complete."""
        start = time.time()

        while time.time() - start < timeout:
            status = self.get_pod_status(pod_name)
            if status is None:
                raise RuntimeError(f"Pod {pod_name} not found")

            if status.phase in ("Succeeded", "Failed"):
                return status

            time.sleep(2)

        raise TimeoutError(f"Pod {pod_name} did not complete within {timeout}s")
