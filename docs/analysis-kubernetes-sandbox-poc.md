# Option D: Kubernetes Sandbox for EMDX Cascade/Workflows - Deep Dive Analysis

## Executive Summary

This document presents a comprehensive analysis of implementing Kubernetes-based sandboxing for EMDX's cascade and workflow execution systems. Based on extensive research of the 2025 landscape, we evaluate multiple approaches from managed services (E2B, Modal) to self-hosted solutions (Agent Sandbox, Fly Machines), with detailed architecture proposals and cost estimates.

---

## 1. Research Findings: The 2025 Sandbox Landscape

### 1.1 Kubernetes Agent Sandbox (kubernetes-sigs/agent-sandbox)

**Status**: Production-ready, launched at KubeCon NA 2025

**Key Features**:
- Declarative API via Custom Resource Definitions (CRDs)
- Three core resources: Sandbox, SandboxTemplate, SandboxClaim
- WarmPools for sub-second cold starts via pre-warmed pods
- Dual runtime support: gVisor (default) and Kata Containers
- Native integration with ADK, LangChain, and other AI frameworks

**Architecture**:
```
┌─────────────────────────────────────────────────────────────────┐
│                    Kubernetes Cluster                           │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │ WarmPool    │  │ WarmPool    │  │ WarmPool    │   Pre-warmed │
│  │ (gVisor)    │  │ (gVisor)    │  │ (Kata)      │   Pods       │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘              │
│         │                │                │                      │
│  ┌──────▼─────────────────▼────────────────▼──────┐              │
│  │              Sandbox Controller                 │              │
│  │  - Claims pods from WarmPools                  │              │
│  │  - Manages lifecycle                           │              │
│  │  - Handles persistent storage                  │              │
│  └────────────────────────────────────────────────┘              │
└─────────────────────────────────────────────────────────────────┘
```

**Security Model**:
| Runtime   | Isolation Type          | Startup Time | Syscall Support | Overhead |
|-----------|------------------------|--------------|-----------------|----------|
| gVisor    | User-space kernel      | 50-100ms     | 70-80%          | Lower    |
| Kata      | Hardware virtualization| 150-300ms    | ~100%           | Higher   |

**Source**: [kubernetes-sigs/agent-sandbox](https://github.com/kubernetes-sigs/agent-sandbox), [Agent Sandbox Docs](https://agent-sandbox.sigs.k8s.io/)

### 1.2 E2B (Firecracker MicroVMs)

**Status**: Production-ready, used by Perplexity, Hugging Face, Groq

**Key Features**:
- ~150ms sandbox spin-up (Firecracker microVMs)
- Hardware-level isolation via KVM virtualization
- 24-hour continuous session support
- Multi-language: Python, JavaScript, TypeScript, Ruby, C++

**Architecture**: Managed service with REST API. Each sandbox runs in a dedicated Firecracker microVM with:
- <5 MiB memory overhead per VM
- Full Linux kernel per sandbox
- Capability-based I/O isolation

**Pricing**:
- Pay-per-second billing
- ~$0.0001/second for basic sandbox
- $0.50-2.00/hour for GPU sandboxes

**Source**: [E2B Documentation](https://e2b.dev/docs), [E2B GitHub](https://github.com/e2b-dev/E2B)

### 1.3 Modal Sandboxes

**Status**: Generally available (January 2025)

**Key Features**:
- Sub-second cold starts (but 2-5s for complex containers)
- Autoscale from 0 to 50,000+ concurrent sessions
- Serverless container fabric
- Python-first API

**Use Case**: Powers Poe's AI code execution (Quora platform)

**Pricing**:
- Per-second billing for compute
- ~$0.0001/second for CPU
- ~$0.001/second for GPU

**Source**: [Modal Sandboxes](https://modal.com/products/sandboxes), [Modal Docs](https://modal.com/docs/examples/agent)

### 1.4 Fly Machines

**Status**: Production, used by many edge workloads

**Key Features**:
- Sub-second VM startup (Firecracker-based)
- 40% discount with reservations
- Stopped machines charged only for rootfs ($0.15/GB/month)
- Global edge deployment

**Pricing** (2025):
| Resource          | Cost                    |
|-------------------|-------------------------|
| shared-cpu-1x     | $0.0035/hour           |
| performance-1x    | $0.0070/hour           |
| Rootfs (stopped)  | $0.15/GB/month         |
| Bandwidth         | $0.02/GB (NA/EU)       |

**Source**: [Fly.io Pricing](https://fly.io/docs/about/pricing/)

### 1.5 WebAssembly Sandboxing

**Status**: Emerging, production use at NVIDIA

**Key Features**:
- Runs in browser (client-side execution)
- Capability-based security model
- Memory safety with automatic bounds checking
- Sub-millisecond startup

**Limitations**:
- Limited syscall support
- No native file system access
- Requires explicit capability grants

**Use Cases**:
- Lightweight code execution (Pyodide for Python)
- Secure evaluation of untrusted code
- Defense-in-depth layer

**Source**: [NVIDIA WebAssembly Blog](https://developer.nvidia.com/blog/sandboxing-agentic-ai-workflows-with-webassembly/)

---

## 2. Wild Ideas: Moonshot Approaches

### 2.1 Full Kubernetes Operator: EmdxCascade CRD

```yaml
apiVersion: emdx.io/v1alpha1
kind: EmdxCascade
metadata:
  name: feature-dark-mode
  namespace: emdx-pipelines
spec:
  # Starting document content
  idea: "Add dark mode toggle to the settings page"

  # Pipeline configuration
  stopAt: done  # idea -> prompt -> analyzed -> planned -> done

  # Execution parameters
  model: claude-opus-4-5
  timeout: 30m

  # Git integration
  git:
    repository: https://github.com/user/repo
    baseBranch: main
    createPR: true
    prTemplate: |
      ## Summary
      {{.analysis}}

      ## Changes
      {{.changes}}

  # Resource limits per stage
  resources:
    cpu: "2"
    memory: "4Gi"

  # Result handling
  output:
    saveToEmdx: true
    tags: ["feature", "cascade-output"]
```

**Operator Behavior**:
```
EmdxCascade CR Created
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│               EmdxCascade Controller                         │
├─────────────────────────────────────────────────────────────┤
│  1. Watch for EmdxCascade CRs                               │
│  2. Create Sandbox per stage                                │
│  3. Inject Claude CLI + credentials                         │
│  4. Execute stage transform                                 │
│  5. Capture output, update CR status                        │
│  6. Advance to next stage                                   │
│  7. Create PR at "done" stage                               │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Firecracker MicroVM Farm (Self-Hosted E2B)

Run your own Firecracker orchestration:

```
┌─────────────────────────────────────────────────────────────┐
│                 EMDX Firecracker Farm                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐ │
│  │ MicroVM Pool │     │ MicroVM Pool │     │ MicroVM Pool │ │
│  │  (idle: 5)   │     │  (idle: 10)  │     │  (idle: 3)   │ │
│  │  Small (1c)  │     │  Medium (2c) │     │  Large (4c)  │ │
│  └──────┬───────┘     └──────┬───────┘     └──────┬───────┘ │
│         │                    │                    │          │
│  ┌──────▼────────────────────▼────────────────────▼───────┐ │
│  │            Firecracker Manager (containerd + FC)       │ │
│  │  - VM lifecycle                                        │ │
│  │  - Snapshot/restore for <100ms boot                    │ │
│  │  - Network isolation (CNI)                             │ │
│  └────────────────────────────────────────────────────────┘ │
│                              │                               │
│  ┌───────────────────────────▼───────────────────────────┐  │
│  │                EMDX Scheduler                          │  │
│  │  - Receives cascade/workflow requests                 │  │
│  │  - Claims VM from pool                                │  │
│  │  - Injects task, monitors execution                   │  │
│  │  - Returns results to EMDX KB                         │  │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 WebAssembly + Browser Hybrid

Use WASM for lightweight tasks, escalate to containers for heavy lifting:

```
                    ┌────────────────────────────┐
                    │     EMDX Local Client      │
                    └──────────────┬─────────────┘
                                   │
                    ┌──────────────▼─────────────┐
                    │    Task Complexity Router  │
                    └──────────────┬─────────────┘
                                   │
         ┌─────────────────────────┼─────────────────────────┐
         │                         │                         │
         ▼                         ▼                         ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   WASM Sandbox  │     │  Local Docker   │     │  Remote K8s     │
│   (in-browser)  │     │   Container     │     │    Sandbox      │
├─────────────────┤     ├─────────────────┤     ├─────────────────┤
│ Simple analysis │     │ Medium tasks    │     │ Full cascade    │
│ Text transforms │     │ Code generation │     │ PR creation     │
│ Validations     │     │ Tests           │     │ Long-running    │
│ <10s tasks      │     │ <5min tasks     │     │ GPU inference   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

### 2.4 P2P Cascade Network

Distributed execution across EMDX users:

```
┌─────────────────────────────────────────────────────────────────┐
│                   P2P EMDX Compute Network                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────┐        ┌──────────┐        ┌──────────┐          │
│  │  Node A  │◄──────►│  Node B  │◄──────►│  Node C  │          │
│  │ (Alice)  │        │  (Bob)   │        │ (Carol)  │          │
│  └────┬─────┘        └────┬─────┘        └────┬─────┘          │
│       │                   │                   │                 │
│       │    ┌──────────────▼──────────────┐    │                 │
│       └───►│   Distributed Hash Table    │◄───┘                 │
│            │   (Task Discovery/Routing)  │                      │
│            └─────────────────────────────┘                      │
│                                                                  │
│  Features:                                                       │
│  - Contribute idle compute, earn credits                        │
│  - Execute others' cascade stages                               │
│  - Encrypted task payloads (only executor sees content)        │
│  - Reputation system for reliability                            │
│  - Auto-scaling based on network capacity                       │
└─────────────────────────────────────────────────────────────────┘
```

### 2.5 Self-Healing Pipelines with Checkpointing

```
┌────────────────────────────────────────────────────────────────┐
│              Self-Healing Cascade Architecture                  │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│  │  idea   │───►│  prompt  │───►│ analyzed │───►│ planned  │  │
│  │   ●     │    │    ●     │    │    ●     │    │    ●     │  │
│  │ ckpt:1  │    │ ckpt:2   │    │ ckpt:3   │    │ ckpt:4   │  │
│  └────┬────┘    └────┬─────┘    └────┬─────┘    └────┬─────┘  │
│       │              │               │               │         │
│       ▼              ▼               ▼               ▼         │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │               Checkpoint Store (SQLite/S3)               │ │
│  │  - Full document state                                   │ │
│  │  - Git branch/commit                                     │ │
│  │  - Model conversation history                            │ │
│  │  - Execution metadata                                    │ │
│  └──────────────────────────────────────────────────────────┘ │
│                              │                                  │
│                              ▼                                  │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │                  Recovery Manager                         │ │
│  │  - Detect failed stages                                  │ │
│  │  - Restore from checkpoint                               │ │
│  │  - Retry with exponential backoff                        │ │
│  │  - Notify on repeated failures                           │ │
│  └──────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────┘
```

---

## 3. Practical Approaches: Implementation-Ready

### 3.1 Docker Containers per Execution (Works Today)

**Architecture**:
```
┌─────────────────────────────────────────────────────────────┐
│                  EMDX Docker Executor                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              Local Docker Daemon                       │  │
│  │  ┌─────────────────────────────────────────────────┐  │  │
│  │  │  Container: emdx-cascade-{doc_id}-{stage}       │  │  │
│  │  │                                                  │  │  │
│  │  │  ┌──────────────────────────────────────────┐   │  │  │
│  │  │  │   Claude CLI + Environment               │   │  │  │
│  │  │  │   - Git repo mounted (read-only)         │   │  │  │
│  │  │  │   - Worktree mounted (read-write)        │   │  │  │
│  │  │  │   - API keys via secrets                 │   │  │  │
│  │  │  │   - Output dir mounted                   │   │  │  │
│  │  │  └──────────────────────────────────────────┘   │  │  │
│  │  └─────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────┘  │
│                              │                               │
│  ┌───────────────────────────▼───────────────────────────┐  │
│  │                EMDX Integration Layer                  │  │
│  │  - Create container with stage-specific image         │  │
│  │  - Stream logs to EMDX activity                       │  │
│  │  - Capture output, update documents                   │  │
│  │  - Cleanup containers on completion                   │  │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

**Dockerfile**:
```dockerfile
FROM python:3.13-slim

# Install Claude CLI and dependencies
RUN pip install anthropic-claude-cli emdx

# Install git for worktree operations
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd -m -s /bin/bash emdx
USER emdx

WORKDIR /workspace

# Entry point that receives task via stdin or args
ENTRYPOINT ["claude"]
```

**Integration Code** (extends current `execute_cli_sync`):
```python
def execute_in_docker(
    task: str,
    doc_id: int,
    stage: str,
    working_dir: Path,
) -> ExecutionResult:
    """Execute cascade stage in isolated Docker container."""
    container_name = f"emdx-cascade-{doc_id}-{stage}-{int(time.time())}"

    # Build docker run command
    cmd = [
        "docker", "run",
        "--rm",
        "--name", container_name,
        "-v", f"{working_dir}:/workspace:rw",
        "-e", f"ANTHROPIC_API_KEY={os.environ['ANTHROPIC_API_KEY']}",
        "--memory", "4g",
        "--cpus", "2",
        "emdx-claude:latest",
        "-p", task,
    ]

    # ... execution logic
```

**Pros**: Works immediately, minimal changes to existing code
**Cons**: Local-only, no auto-scaling, resource competition

### 3.2 Agent Sandbox (kubernetes-sigs) for K8s-Native

**CRD Integration**:
```yaml
# sandbox-template.yaml
apiVersion: agent-sandbox.sigs.k8s.io/v1alpha1
kind: SandboxTemplate
metadata:
  name: emdx-cascade-template
spec:
  resources:
    cpu: "2"
    memory: "4Gi"
    ephemeralStorage: "10Gi"
  securityContext:
    runAsNonRoot: true
    seccompProfile:
      type: RuntimeDefault
  runtime: gvisor  # or "kata" for stronger isolation
  image: ghcr.io/user/emdx-sandbox:latest
  env:
    - name: EMDX_MODE
      value: "sandbox"
```

```yaml
# sandbox-claim.yaml (created per cascade execution)
apiVersion: agent-sandbox.sigs.k8s.io/v1alpha1
kind: SandboxClaim
metadata:
  name: cascade-{doc_id}-{stage}
  labels:
    emdx.io/doc-id: "{doc_id}"
    emdx.io/stage: "{stage}"
spec:
  sandboxTemplateName: emdx-cascade-template
  workspaceVolume:
    persistentVolumeClaim:
      claimName: cascade-workspace-{doc_id}
```

**EMDX Kubernetes Client**:
```python
from kubernetes import client, config

class K8sSandboxExecutor:
    """Execute cascade stages in Kubernetes Agent Sandbox."""

    def __init__(self):
        config.load_kube_config()
        self.custom_api = client.CustomObjectsApi()
        self.core_api = client.CoreV1Api()

    def execute_stage(
        self,
        doc_id: int,
        stage: str,
        task: str,
        working_dir: str,
    ) -> ExecutionResult:
        """Execute a cascade stage in a sandbox."""
        claim_name = f"cascade-{doc_id}-{stage}"

        # Create SandboxClaim
        claim = {
            "apiVersion": "agent-sandbox.sigs.k8s.io/v1alpha1",
            "kind": "SandboxClaim",
            "metadata": {
                "name": claim_name,
                "namespace": "emdx-cascade",
            },
            "spec": {
                "sandboxTemplateName": "emdx-cascade-template",
            },
        }

        self.custom_api.create_namespaced_custom_object(
            group="agent-sandbox.sigs.k8s.io",
            version="v1alpha1",
            namespace="emdx-cascade",
            plural="sandboxclaims",
            body=claim,
        )

        # Wait for sandbox to be ready
        sandbox_ready = self._wait_for_sandbox(claim_name)

        # Execute task in sandbox
        result = self._exec_in_sandbox(sandbox_ready, task)

        # Cleanup
        self._delete_sandbox_claim(claim_name)

        return result
```

### 3.3 Modal/E2B for Managed Sandboxes

**E2B Integration**:
```python
from e2b import Sandbox

class E2BExecutor:
    """Execute cascade stages in E2B sandboxes."""

    async def execute_stage(
        self,
        doc_id: int,
        stage: str,
        task: str,
        repo_url: str,
    ) -> ExecutionResult:
        """Execute a cascade stage in E2B sandbox."""

        # Create sandbox with Claude CLI pre-installed
        sandbox = Sandbox(template="emdx-claude")

        try:
            # Clone the repository
            sandbox.process.start_and_wait(f"git clone {repo_url} /workspace")

            # Write task to file
            sandbox.filesystem.write("/workspace/task.txt", task)

            # Execute Claude
            process = sandbox.process.start_and_wait(
                "claude -p 'Complete the task in task.txt' --output-dir /workspace/output",
                timeout=1800,
            )

            # Read output
            output = sandbox.filesystem.read("/workspace/output/result.md")

            return ExecutionResult(
                success=process.exit_code == 0,
                output=output,
                execution_time_ms=process.duration_ms,
            )

        finally:
            sandbox.close()
```

**Modal Integration**:
```python
import modal

app = modal.App("emdx-cascade")

sandbox_image = (
    modal.Image.debian_slim(python_version="3.13")
    .pip_install("anthropic-claude-cli", "emdx")
    .apt_install("git")
)

@app.function(image=sandbox_image, timeout=1800)
def execute_cascade_stage(
    doc_id: int,
    stage: str,
    task: str,
    repo_url: str,
) -> dict:
    """Execute cascade stage in Modal sandbox."""
    import subprocess
    import os

    # Clone repo
    subprocess.run(["git", "clone", repo_url, "/workspace"], check=True)
    os.chdir("/workspace")

    # Execute Claude
    result = subprocess.run(
        ["claude", "-p", task],
        capture_output=True,
        text=True,
    )

    return {
        "success": result.returncode == 0,
        "output": result.stdout,
        "stderr": result.stderr,
    }
```

### 3.4 Fly Machines for Stateful Agents

**Fly.toml Configuration**:
```toml
app = "emdx-cascade-workers"
primary_region = "sjc"

[build]
  image = "ghcr.io/user/emdx-sandbox:latest"

[http_service]
  internal_port = 8080
  force_https = true
  auto_stop_machines = true
  auto_start_machines = true
  min_machines_running = 0
  processes = ["app"]

[[vm]]
  cpu_kind = "shared"
  cpus = 2
  memory_mb = 2048
```

**Fly Machines API Integration**:
```python
import httpx

class FlyMachinesExecutor:
    """Execute cascade stages on Fly Machines."""

    def __init__(self, app_name: str, api_token: str):
        self.app_name = app_name
        self.api_token = api_token
        self.base_url = f"https://api.machines.dev/v1/apps/{app_name}/machines"

    async def execute_stage(
        self,
        doc_id: int,
        stage: str,
        task: str,
        repo_url: str,
    ) -> ExecutionResult:
        """Spin up a Fly Machine, execute task, return result."""

        async with httpx.AsyncClient() as client:
            # Create machine
            machine = await client.post(
                self.base_url,
                headers={"Authorization": f"Bearer {self.api_token}"},
                json={
                    "config": {
                        "image": "ghcr.io/user/emdx-sandbox:latest",
                        "env": {
                            "TASK": task,
                            "REPO_URL": repo_url,
                            "DOC_ID": str(doc_id),
                            "STAGE": stage,
                        },
                        "guest": {"cpus": 2, "memory_mb": 4096},
                        "auto_destroy": True,
                    },
                },
            )

            machine_id = machine.json()["id"]

            # Wait for completion (machine auto-stops)
            result = await self._wait_for_completion(machine_id)

            return result
```

---

## 4. EMDX-Specific Architecture Design

### 4.1 How Local EMDX Submits Jobs to Remote

```
┌─────────────────────────────────────────────────────────────────┐
│                    Local EMDX Client                             │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  emdx cascade add "Add dark mode" --remote k8s            │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                 EMDX Remote Gateway (REST API)                   │
│  POST /api/v1/cascade                                            │
│  {                                                               │
│    "idea": "Add dark mode toggle",                              │
│    "stop_at": "done",                                            │
│    "git": {                                                      │
│      "repo": "https://github.com/user/repo",                    │
│      "token": "ghs_xxx",                                         │
│      "base_branch": "main"                                       │
│    },                                                            │
│    "callback_url": "https://your-server/webhook",               │
│    "emdx_sync": {                                                │
│      "enabled": true,                                            │
│      "api_key": "emdx_xxx"                                       │
│    }                                                             │
│  }                                                               │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Kubernetes Cluster                            │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                 EMDX Controller                              ││
│  │  - Creates CascadeRun CR                                    ││
│  │  - Watches for stage completions                            ││
│  │  - Advances to next stage                                   ││
│  └─────────────────────────────────────────────────────────────┘│
│                              │                                   │
│  ┌───────────────────────────▼───────────────────────────────┐  │
│  │              Agent Sandbox (per stage)                     │  │
│  │  - Git clone with token auth                              │  │
│  │  - Execute Claude CLI                                     │  │
│  │  - Capture output                                         │  │
│  │  - Git commit/push                                        │  │
│  │  - Create PR (at done stage)                             │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Results Flow Back to Local KB

**Sync Protocol**:
```
Remote Execution Completes
         │
         ▼
┌────────────────────────────────────────────────────────────────┐
│  Stage Output Captured                                          │
│  - Document content                                             │
│  - Metadata (tokens, cost, time)                               │
│  - Git diff / PR URL                                            │
└────────────────────────────────────────────────────────────────┘
         │
         │  Option A: Webhook (real-time)
         ▼
┌────────────────────────────────────────────────────────────────┐
│  POST {callback_url}                                            │
│  {                                                              │
│    "event": "stage_completed",                                  │
│    "cascade_id": "xxx",                                         │
│    "stage": "analyzed",                                         │
│    "output_doc": { "title": "...", "content": "..." },         │
│    "metrics": { "tokens": 5000, "cost_usd": 0.02 }             │
│  }                                                              │
└────────────────────────────────────────────────────────────────┘
         │
         │  Local EMDX receives webhook
         ▼
┌────────────────────────────────────────────────────────────────┐
│  emdx save --title "Remote: analyzed" --tags cascade,remote    │
│  Update local cascade_runs table                                │
└────────────────────────────────────────────────────────────────┘

         │  Option B: Polling (simpler)
         │
         ▼
┌────────────────────────────────────────────────────────────────┐
│  emdx cascade sync --remote k8s                                 │
│  - Polls remote API every 30s                                   │
│  - Downloads new documents                                      │
│  - Updates local state                                          │
└────────────────────────────────────────────────────────────────┘
```

### 4.3 Authentication Model

```
┌─────────────────────────────────────────────────────────────────┐
│                    Authentication Layers                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Layer 1: EMDX API Authentication                               │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  API Key stored in ~/.config/emdx/remote.json               ││
│  │  {                                                           ││
│  │    "k8s": {                                                  ││
│  │      "api_url": "https://emdx-k8s.example.com",             ││
│  │      "api_key": "emdx_k8s_xxx"                              ││
│  │    }                                                         ││
│  │  }                                                           ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  Layer 2: Git Authentication (per-request)                      │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  Option A: PAT passed with request (encrypted in transit)  ││
│  │  Option B: GitHub App installation token                    ││
│  │  Option C: SSH key mounted as K8s secret                   ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  Layer 3: Anthropic API Key                                     │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  Stored as Kubernetes Secret                                ││
│  │  Injected into sandbox at runtime                          ││
│  │  Never transmitted to/from local client                    ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

### 4.4 Remote Git Worktrees

**Challenge**: Local worktrees don't exist in remote environment

**Solution**: Branch-per-execution pattern

```
┌─────────────────────────────────────────────────────────────────┐
│               Remote Git Workflow                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Clone fresh copy in sandbox                                 │
│     git clone --depth 1 --branch main {repo_url}               │
│                                                                  │
│  2. Create execution branch                                     │
│     git checkout -b cascade/{doc_id}/{stage}                   │
│                                                                  │
│  3. Execute Claude with write access                            │
│     - Modifications happen on branch                            │
│     - Commits tracked per stage                                 │
│                                                                  │
│  4. Push branch (not main)                                      │
│     git push origin cascade/{doc_id}/{stage}                   │
│                                                                  │
│  5. At "done" stage, create PR                                  │
│     gh pr create --base main --head cascade/{doc_id}/planned   │
│                                                                  │
│  Result:                                                         │
│  - No worktree management needed                                │
│  - Each stage has isolated branch                              │
│  - Full git history preserved                                   │
│  - Easy to inspect/rollback                                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 5. Cost Model

### 5.1 Per-Execution Costs

| Platform          | CPU-hours | Memory | Storage | API/Network | Est. per Cascade |
|-------------------|-----------|--------|---------|-------------|------------------|
| **Local Docker**  | Free      | Free   | Free    | $0.05-0.20  | $0.05-0.20      |
| **E2B**           | $0.36/hr  | Incl.  | Incl.   | $0.05-0.20  | $0.15-0.50      |
| **Modal**         | $0.20/hr  | Incl.  | Incl.   | $0.05-0.20  | $0.10-0.40      |
| **Agent Sandbox** | $0.05/hr* | Incl.  | $0.05   | $0.05-0.20  | $0.08-0.30      |
| **Fly Machines**  | $0.07/hr  | Incl.  | $0.02   | $0.05-0.20  | $0.09-0.35      |

*Agent Sandbox: cluster cost amortized across executions

### 5.2 Monthly Infrastructure Costs

| Scenario                      | E2B       | Modal    | Self-Hosted K8s | Fly      |
|-------------------------------|-----------|----------|-----------------|----------|
| **Light** (50 cascades/mo)    | $7.50     | $5.00    | $50 (min)       | $4.50    |
| **Medium** (200 cascades/mo)  | $30.00    | $20.00   | $50-100         | $18.00   |
| **Heavy** (1000 cascades/mo)  | $150.00   | $100.00  | $100-200        | $90.00   |

### 5.3 Claude API Costs (Dominant Factor)

The Claude API cost typically dominates execution costs:

| Stage    | Avg Tokens | Opus 4.5 Cost | Sonnet 3.5 Cost |
|----------|------------|---------------|-----------------|
| idea     | 2,000      | $0.06         | $0.01           |
| prompt   | 3,000      | $0.09         | $0.02           |
| analyzed | 5,000      | $0.15         | $0.03           |
| planned  | 8,000      | $0.24         | $0.05           |
| **Total**| 18,000     | **$0.54**     | **$0.11**       |

**Key Insight**: Compute infrastructure is 10-30% of total cascade cost. Claude API is 70-90%.

---

## 6. Recommendation: Phased Implementation

### Phase 1: Docker Containers (Now - Week 2)

**Scope**: Add optional Docker isolation to existing executor

```python
# emdx/config/settings.py
EXECUTION_BACKENDS = {
    "local": LocalExecutor,          # Current behavior (default)
    "docker": DockerExecutor,        # New: Docker container
}
```

**CLI Integration**:
```bash
# Use local (current behavior)
emdx cascade add "idea" --auto

# Use Docker isolation
emdx cascade add "idea" --auto --backend docker

# Configure globally
emdx config set execution.backend docker
```

**Effort**: 2-3 days

### Phase 2: Fly Machines (Week 3-4)

**Scope**: Remote execution on Fly's edge infrastructure

**Why Fly First**:
- Simple API, well-documented
- Low fixed costs (pay-per-use)
- Sub-second startup
- Built-in auto-destroy

**Effort**: 1 week

### Phase 3: Agent Sandbox (Month 2-3)

**Scope**: Full Kubernetes-native integration for teams/enterprise

**Prerequisites**:
- Kubernetes cluster (GKE, EKS, or self-hosted)
- Agent Sandbox operator installed
- EMDX controller deployment

**Effort**: 2-3 weeks

### Phase 4: Custom CRD (Month 4+)

**Scope**: Full EmdxCascade operator for declarative pipelines

**Effort**: 4-6 weeks

---

## 7. Conclusion

The 2025 sandbox landscape offers mature, production-ready options for EMDX cascade execution. The recommended path:

1. **Start simple**: Docker containers add security without infrastructure overhead
2. **Scale with Fly**: When local resources become a bottleneck, Fly Machines offer easy remote execution
3. **Enterprise with K8s**: Agent Sandbox provides the most flexible, scalable, and secure option for teams

The dominant cost factor is always the Claude API, not compute infrastructure. This means that optimizing prompts and using efficient models (Sonnet for early stages) provides better ROI than aggressive infrastructure optimization.

---

## Sources

### Kubernetes & Containers
- [kubernetes-sigs/agent-sandbox](https://github.com/kubernetes-sigs/agent-sandbox)
- [Agent Sandbox Docs](https://agent-sandbox.sigs.k8s.io/)
- [Google Open Source Blog: Autonomous AI Agents](https://opensource.googleblog.com/2025/11/unleashing-autonomous-ai-agents-why-kubernetes-needs-a-new-standard-for-agent-execution.html)
- [Kata Containers Agent Sandbox Integration](https://katacontainers.io/blog/kata-containers-agent-sandbox-integration/)

### Managed Sandbox Services
- [E2B Documentation](https://e2b.dev/docs)
- [E2B GitHub](https://github.com/e2b-dev/E2B)
- [Modal Sandboxes](https://modal.com/products/sandboxes)
- [Modal Blog: Top Code Sandbox Products 2025](https://modal.com/blog/top-code-agent-sandbox-products)

### Fly.io
- [Fly.io Resource Pricing](https://fly.io/docs/about/pricing/)
- [Fly.io Pricing Calculator](https://fly.io/calculator)

### Security & Isolation
- [gVisor vs Kata vs Firecracker Comparison](https://dev.to/agentsphere/choosing-a-workspace-for-ai-agents-the-ultimate-showdown-between-gvisor-kata-and-firecracker-b10)
- [NVIDIA: Sandboxing Agentic AI with WebAssembly](https://developer.nvidia.com/blog/sandboxing-agentic-ai-workflows-with-webassembly/)

### Claude Code Orchestration
- [wshobson/agents](https://github.com/wshobson/agents)
- [claude-flow](https://github.com/ruvnet/claude-flow)
- [Claude-Code K8s Issue #5045](https://github.com/anthropics/claude-code/issues/5045)
