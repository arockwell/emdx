"""
Modern command registration system for EMDX.
Replaces fragile typer internals manipulation with clean, maintainable patterns.
"""
from typing import Protocol, Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
import typer
from rich.console import Console
from datetime import datetime

console = Console()


@dataclass
class CommandDefinition:
    """Definition of a single CLI command"""
    name: str
    function: Callable
    help: str
    aliases: List[str] = field(default_factory=list)
    group: Optional[str] = None
    hidden: bool = False
    deprecated: bool = False
    
    def __post_init__(self):
        if not callable(self.function):
            raise ValueError(f"Command {self.name} function must be callable")


class CommandModule(Protocol):
    """Protocol for command modules with standardized interface"""
    def get_commands(self) -> List[CommandDefinition]:
        """Return list of commands provided by this module"""
        ...


class CommandRegistry:
    """Central registry for all CLI commands"""
    
    def __init__(self):
        self.commands: Dict[str, CommandDefinition] = {}
        self.groups: Dict[str, typer.Typer] = {}
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.registered_modules: List[str] = []
    
    def register_module(self, module: CommandModule, prefix: Optional[str] = None) -> int:
        """Register all commands from a module"""
        try:
            commands = module.get_commands()
            count = 0
            
            for cmd in commands:
                full_name = f"{prefix}.{cmd.name}" if prefix else cmd.name
                
                if full_name in self.commands:
                    self.errors.append(f"Duplicate command: {full_name}")
                    continue
                    
                self.commands[full_name] = cmd
                count += 1
                
            if count > 0:
                console.print(f"[green]Registered {count} commands from module[/green]", style="dim")
                self.registered_modules.append(getattr(module, '__name__', 'unknown'))
            return count
            
        except Exception as e:
            error_msg = f"Failed to register module: {e}"
            self.errors.append(error_msg)
            console.print(f"[red]{error_msg}[/red]")
            return 0
    
    def register_subapp(self, subapp: typer.Typer, name: str, help: str) -> bool:
        """Register a typer subapp (for complex command groups)"""
        try:
            if name in self.groups:
                self.errors.append(f"Duplicate group: {name}")
                return False
                
            self.groups[name] = subapp
            console.print(f"[green]Registered subapp '{name}'[/green]", style="dim")
            return True
            
        except Exception as e:
            error_msg = f"Failed to register group {name}: {e}"
            self.errors.append(error_msg)
            console.print(f"[red]{error_msg}[/red]")
            return False
    
    def register_function(self, function: Callable, name: Optional[str] = None, help: str = "") -> bool:
        """Register a standalone function as a command"""
        try:
            cmd_name = name or function.__name__
            if cmd_name in self.commands:
                self.errors.append(f"Duplicate command: {cmd_name}")
                return False
            
            # Extract help from docstring if not provided
            if not help and function.__doc__:
                help = function.__doc__.strip().split('\n')[0]
            
            cmd_def = CommandDefinition(
                name=cmd_name,
                function=function,
                help=help
            )
            self.commands[cmd_name] = cmd_def
            console.print(f"[green]Registered function '{cmd_name}'[/green]", style="dim")
            return True
            
        except Exception as e:
            error_msg = f"Failed to register function {name or 'unknown'}: {e}"
            self.errors.append(error_msg)
            console.print(f"[red]{error_msg}[/red]")
            return False
    
    def build_app(self, 
                  name: str = "emdx",
                  help: str = "Documentation Index Management System") -> typer.Typer:
        """Build the final typer application"""
        
        app = typer.Typer(
            name=name,
            help=help,
            add_completion=True,
            rich_markup_mode="rich"
        )
        
        # Register individual commands
        for cmd_name, cmd_def in self.commands.items():
            try:
                app.command(
                    name=cmd_name,
                    help=cmd_def.help,
                    hidden=cmd_def.hidden,
                    deprecated=cmd_def.deprecated
                )(cmd_def.function)
                
                # Register aliases
                for alias in cmd_def.aliases:
                    app.command(
                        name=alias,
                        help=f"Alias for {cmd_name}",
                        hidden=True
                    )(cmd_def.function)
                    
            except Exception as e:
                error_msg = f"Failed to register command {cmd_name}: {e}"
                self.errors.append(error_msg)
                console.print(f"[red]{error_msg}[/red]")
        
        # Register subgroups
        for group_name, group_app in self.groups.items():
            try:
                app.add_typer(group_app, name=group_name)
            except Exception as e:
                error_msg = f"Failed to register group {group_name}: {e}"
                self.errors.append(error_msg)
                console.print(f"[red]{error_msg}[/red]")
        
        # Report any errors
        if self.errors:
            console.print(f"[yellow]Command registration completed with {len(self.errors)} errors[/yellow]")
            for error in self.errors:
                console.print(f"  [red]•[/red] {error}")
        
        return app
    
    def validate(self) -> bool:
        """Validate the current registry state"""
        valid = True
        
        # Check for naming conflicts
        all_names = set(self.commands.keys()) | set(self.groups.keys())
        
        # Check command functions
        for cmd_name, cmd_def in self.commands.items():
            if not callable(cmd_def.function):
                self.errors.append(f"Command {cmd_name} has non-callable function")
                valid = False
        
        return valid and not self.errors
    
    def get_status(self) -> Dict[str, Any]:
        """Get current registration status"""
        return {
            "modules_registered": len(self.registered_modules),
            "modules": self.registered_modules,
            "commands_count": len(self.commands),
            "groups_count": len(self.groups),
            "errors": self.errors,
            "warnings": self.warnings,
            "has_errors": len(self.errors) > 0,
            "timestamp": datetime.now().isoformat()
        }


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