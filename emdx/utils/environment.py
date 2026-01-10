"""Environment validation utilities for EMDX execution system."""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from rich.console import Console

console = Console()


class EnvironmentValidator:
    """Validates execution environment before running Claude."""
    
    REQUIRED_COMMANDS = ["claude", "git"]
    REQUIRED_PYTHON_PACKAGES = ["emdx", "typer", "rich"]
    
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: Dict[str, str] = {}
    
    def validate_all(self) -> bool:
        """Run all validation checks.
        
        Returns:
            True if environment is valid, False otherwise
        """
        self.check_python_version()
        self.check_commands()
        self.check_python_packages()
        self.check_paths()
        self.check_claude_config()
        
        return len(self.errors) == 0
    
    def check_python_version(self) -> None:
        """Check Python version compatibility."""
        version = sys.version_info
        self.info["python_version"] = f"{version.major}.{version.minor}.{version.micro}"
        
        if version.major < 3 or (version.major == 3 and version.minor < 8):
            self.errors.append(f"Python 3.8+ required, found {self.info['python_version']}")
    
    def check_commands(self) -> None:
        """Check if required commands are available."""
        for cmd in self.REQUIRED_COMMANDS:
            path = shutil.which(cmd)
            if path:
                self.info[f"{cmd}_path"] = path
                
                # Get version info if possible
                try:
                    if cmd == "claude":
                        result = subprocess.run(
                            ["claude", "--version"],
                            capture_output=True,
                            text=True,
                            timeout=5
                        )
                        if result.returncode == 0:
                            self.info[f"{cmd}_version"] = result.stdout.strip()
                    elif cmd == "git":
                        result = subprocess.run(
                            ["git", "--version"],
                            capture_output=True,
                            text=True,
                            timeout=5
                        )
                        if result.returncode == 0:
                            self.info[f"{cmd}_version"] = result.stdout.strip()
                except Exception as e:
                    # Version check failed - command exists but version query failed
                    self.warnings.append(f"Could not get version for {cmd}: {str(e)}")
            else:
                self.errors.append(f"Required command '{cmd}' not found in PATH")
    
    def check_python_packages(self) -> None:
        """Check if required Python packages are installed."""
        import importlib.util
        
        for package in self.REQUIRED_PYTHON_PACKAGES:
            spec = importlib.util.find_spec(package)
            if spec is None:
                self.errors.append(f"Required Python package '{package}' not installed")
            else:
                # Get package version if possible
                try:
                    module = importlib.import_module(package)
                    if hasattr(module, "__version__"):
                        self.info[f"{package}_version"] = module.__version__
                except Exception as e:
                    # Package version check failed
                    self.warnings.append(f"Could not get version for {package}: {str(e)}")
    
    def check_paths(self) -> None:
        """Check PATH and important directories."""
        # Check PATH
        path_env = os.environ.get("PATH", "")
        self.info["path_dirs"] = str(len(path_env.split(os.pathsep)))
        
        # Check if running in pipx environment
        if "pipx" in sys.executable:
            self.info["installation"] = "pipx"
            self.warnings.append("Running from pipx environment - ensure claude is accessible")
        else:
            self.info["installation"] = "standard"
        
        # Check EMDX config directory
        config_dir = Path.home() / ".config" / "emdx"
        if config_dir.exists():
            self.info["config_dir"] = str(config_dir)
        else:
            self.warnings.append(f"EMDX config directory not found: {config_dir}")
        
        # Check log directory
        log_dir = config_dir / "logs"
        if not log_dir.exists():
            try:
                log_dir.mkdir(parents=True, exist_ok=True)
                self.info["log_dir"] = str(log_dir)
            except Exception as e:
                self.warnings.append(f"Cannot create log directory: {e}")
    
    def check_claude_config(self) -> None:
        """Check Claude-specific configuration."""
        # Check for Claude config file
        claude_config = Path.home() / ".claude" / "claude_cli.json"
        if claude_config.exists():
            self.info["claude_config"] = str(claude_config)
        else:
            self.warnings.append("Claude config file not found - claude might not be properly configured")
        
        # Check ANTHROPIC_API_KEY
        if os.environ.get("ANTHROPIC_API_KEY"):
            self.info["api_key"] = "set"
        else:
            # Check if claude works without explicit API key
            try:
                result = subprocess.run(
                    ["claude", "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode != 0:
                    self.warnings.append("ANTHROPIC_API_KEY not set and claude might not work")
            except Exception as e:
                self.warnings.append(f"Cannot verify claude installation: {e}")
    
    def print_report(self, verbose: bool = False) -> None:
        """Print validation report."""
        if self.errors:
            console.print("\n[bold red]❌ Environment Validation Failed[/bold red]")
            console.print("\n[red]Errors:[/red]")
            for error in self.errors:
                console.print(f"  • {error}")
        else:
            console.print("\n[bold green]✅ Environment Validation Passed[/bold green]")
        
        if self.warnings:
            console.print("\n[yellow]Warnings:[/yellow]")
            for warning in self.warnings:
                console.print(f"  • {warning}")
        
        if verbose or self.errors:
            console.print("\n[cyan]Environment Info:[/cyan]")
            for key, value in self.info.items():
                console.print(f"  {key}: {value}")
    
    def get_environment_info(self) -> Dict[str, any]:
        """Get environment information for logging."""
        return {
            "valid": len(self.errors) == 0,
            "errors": self.errors,
            "warnings": self.warnings,
            "info": self.info
        }


def validate_execution_environment(verbose: bool = False) -> Tuple[bool, Optional[Dict[str, any]]]:
    """Validate the execution environment.
    
    Args:
        verbose: Whether to print detailed output
        
    Returns:
        Tuple of (is_valid, environment_info)
    """
    validator = EnvironmentValidator()
    is_valid = validator.validate_all()
    
    if verbose or not is_valid:
        validator.print_report(verbose)
    
    return is_valid, validator.get_environment_info()


def ensure_claude_in_path() -> None:
    """Ensure claude command is in PATH for subprocess calls."""
    # Common locations where claude might be installed
    claude_paths = [
        "/usr/local/bin",
        "/opt/homebrew/bin",  # macOS ARM
        Path.home() / ".local" / "bin",  # pip install --user
        Path.home() / ".npm" / "bin",  # npm global
    ]
    
    # Add any missing paths that contain claude
    current_path = os.environ.get("PATH", "").split(os.pathsep)
    added_paths = []
    
    for path in claude_paths:
        path = Path(path)
        if path.exists() and str(path) not in current_path:
            claude_exe = path / "claude"
            if claude_exe.exists() and claude_exe.is_file():
                current_path.append(str(path))
                added_paths.append(str(path))
    
    if added_paths:
        os.environ["PATH"] = os.pathsep.join(current_path)
        console.print(f"[dim]Added to PATH: {', '.join(added_paths)}[/dim]")
