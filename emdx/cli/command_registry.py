"""
Command registration utilities for EMDX.
Provides defensive error handling and preparation for Phase 2 architecture.
"""
from typing import Dict, List, Optional, Callable, Any
import typer
from rich.console import Console

console = Console()


def safe_register_commands(target_app: typer.Typer, source_app: typer.Typer, module_name: str) -> int:
    """
    Safely register commands with comprehensive error handling.
    
    Args:
        target_app: The typer app to register commands to
        source_app: The typer app to register commands from
        module_name: Name of the module for error reporting
    
    Returns:
        Number of commands successfully registered
    """
    try:
        if not hasattr(source_app, 'registered_commands'):
            console.print(f"[yellow]Warning: {module_name} has no registered_commands attribute[/yellow]")
            return 0
            
        commands = source_app.registered_commands
        if not commands:
            console.print(f"[yellow]Warning: {module_name} has no commands to register[/yellow]")
            return 0
            
        count = 0
        for command in commands:
            try:
                target_app.registered_commands.append(command)
                count += 1
            except Exception as e:
                console.print(f"[red]Error registering individual command from {module_name}: {e}[/red]")
                
        if count > 0:
            console.print(f"[green]Registered {count} commands from {module_name}[/green]", style="dim")
        return count
        
    except Exception as e:
        console.print(f"[red]Error registering commands from {module_name}: {e}[/red]")
        return 0


def safe_register_subapp(target_app: typer.Typer, subapp: typer.Typer, name: str, help: str) -> bool:
    """
    Safely register a typer subapp with error handling.
    
    Args:
        target_app: The main typer app
        subapp: The subapp to register
        name: Name for the subcommand group
        help: Help text for the subcommand group
    
    Returns:
        True if registration succeeded, False otherwise
    """
    try:
        target_app.add_typer(subapp, name=name, help=help)
        console.print(f"[green]Registered subapp '{name}'[/green]", style="dim")
        return True
    except Exception as e:
        console.print(f"[red]Error registering subapp '{name}': {e}[/red]")
        return False


def safe_register_function(target_app: typer.Typer, function: Callable, name: Optional[str] = None) -> bool:
    """
    Safely register a standalone function as a command.
    
    Args:
        target_app: The typer app to register to
        function: The function to register
        name: Optional command name (uses function name if not provided)
    
    Returns:
        True if registration succeeded, False otherwise
    """
    try:
        if name:
            target_app.command(name=name)(function)
        else:
            target_app.command()(function)
        
        func_name = name or function.__name__
        console.print(f"[green]Registered function '{func_name}'[/green]", style="dim")
        return True
    except Exception as e:
        func_name = name or getattr(function, '__name__', 'unknown')
        console.print(f"[red]Error registering function '{func_name}': {e}[/red]")
        return False


def validate_command_registration(app: typer.Typer) -> Dict[str, Any]:
    """
    Validate the current state of command registration.
    
    Args:
        app: The typer app to validate
    
    Returns:
        Dictionary with validation results
    """
    results = {
        "valid": True,
        "errors": [],
        "warnings": [],
        "stats": {
            "total_commands": 0,
            "registered_commands": 0,
            "subapps": 0
        }
    }
    
    try:
        # Check if app has registered_commands
        if hasattr(app, 'registered_commands'):
            registered = app.registered_commands or []
            results["stats"]["registered_commands"] = len(registered)
            
            # Validate each command
            for i, command in enumerate(registered):
                if not hasattr(command, 'callback'):
                    results["errors"].append(f"Command {i} has no callback")
                    results["valid"] = False
                elif not callable(command.callback):
                    results["errors"].append(f"Command {i} callback is not callable")
                    results["valid"] = False
        else:
            results["warnings"].append("App has no registered_commands attribute")
        
        # Try to get command information
        try:
            # This will work if typer has proper command introspection
            if hasattr(app, 'registered_groups'):
                results["stats"]["subapps"] = len(app.registered_groups)
        except:
            pass
            
    except Exception as e:
        results["errors"].append(f"Validation error: {e}")
        results["valid"] = False
    
    return results


# Foundation for Phase 2 - will be expanded
class CommandRegistryFoundation:
    """
    Foundation class for future Phase 2 command registry architecture.
    Currently provides basic validation and error tracking.
    """
    
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.registered_modules: List[str] = []
    
    def register_module_safe(self, target_app: typer.Typer, source_app: typer.Typer, module_name: str) -> int:
        """Register a module with tracking."""
        count = safe_register_commands(target_app, source_app, module_name)
        if count > 0:
            self.registered_modules.append(module_name)
        return count
    
    def get_status(self) -> Dict[str, Any]:
        """Get current registration status."""
        return {
            "modules_registered": len(self.registered_modules),
            "modules": self.registered_modules,
            "errors": self.errors,
            "warnings": self.warnings,
            "has_errors": len(self.errors) > 0
        }
    
    def validate_app(self, app: typer.Typer) -> bool:
        """Validate the app and update internal state."""
        results = validate_command_registration(app)
        self.errors.extend(results["errors"])
        self.warnings.extend(results["warnings"])
        return results["valid"]