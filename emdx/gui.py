"""
GUI (fzf-based) interface for emdx
"""

import os
import subprocess
import sys
import tempfile
from typing import Optional
from pathlib import Path
import logging

import typer
from rich.console import Console

from emdx.database import db

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='/tmp/emdx_gui_debug.log'
)
logger = logging.getLogger(__name__)

app = typer.Typer()
console = Console()


def get_fzf_path() -> Optional[str]:
    """Get the path to fzf executable."""
    # Try common fzf locations
    fzf_paths = [
        "fzf",  # In PATH
        "/opt/homebrew/bin/fzf",  # Homebrew ARM64
        "/usr/local/bin/fzf",  # Homebrew Intel
        "/home/linuxbrew/.linuxbrew/bin/fzf",  # Linux
    ]
    
    for fzf_path in fzf_paths:
        try:
            result = subprocess.run([fzf_path, "--version"], capture_output=True)
            if result.returncode == 0:
                return fzf_path
        except FileNotFoundError:
            continue
    
    # Try which command as fallback
    try:
        result = subprocess.run(["which", "fzf"], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip()
    except:
        pass
    
    return None


def format_document_list():
    """Format documents for fzf display."""
    docs = db.list_documents(limit=1000)
    
    lines = []
    for doc in docs:
        # Format: ID | Title | Project | Created | Views
        created = doc['created_at'].strftime('%Y-%m-%d')
        title = doc['title'][:50] + "..." if len(doc['title']) > 50 else doc['title']
        project = doc['project'] or 'None'
        views = str(doc['access_count'])
        
        line = f"{doc['id']:>5} │ {title:<50} │ {project:<20} │ {created} │ {views:>5}"
        lines.append(line)
    
    return lines


def create_preview_script():
    """Create a Python script for document preview."""
    # Get the actual emdx module path
    import emdx
    emdx_path = Path(emdx.__file__).parent.parent
    
    script = f'''#!/usr/bin/env python3
import sys
from pathlib import Path

# Add emdx to path using the correct path
sys.path.insert(0, '{emdx_path}')

try:
    from emdx.database import db
    
    if len(sys.argv) < 2:
        print("No document ID provided")
        sys.exit(1)
    
    doc_id = int(sys.argv[1])
    
    # Ensure database connection
    db.ensure_schema()
    
    doc = db.get_document(str(doc_id))
    if doc:
        print(doc['content'])
    else:
        print(f"Document {{doc_id}} not found")
except Exception as e:
    print(f"Error: {{e}}")
'''
    return script


@app.command()
def gui():
    """Interactive FZF-based document browser for emdx."""
    # Check prerequisites
    fzf_path = get_fzf_path()
    if not fzf_path:
        console.print("❌ Error: fzf is not installed", style="red")
        console.print("Install with: brew install fzf")
        raise typer.Exit(1)
    
    # Ensure database schema exists
    try:
        db.ensure_schema()
    except Exception as e:
        console.print(f"❌ Error: Cannot connect to database: {e}", style="red")
        raise typer.Exit(1)
    
    # Check if any documents exist
    docs = db.list_documents(limit=1)
    if not docs:
        console.print()
        console.print("No documents found in knowledge base.")
        console.print()
        console.print("💡 Get started with:")
        console.print("   emdx save <file>         - Save a markdown file")
        console.print("   emdx direct <title>      - Create a document directly")
        console.print("   emdx note 'quick note'   - Save a quick note")
        return
    
    # Create a temporary preview script
    preview_script = create_preview_script()
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(preview_script)
        preview_script_path = f.name
    
    try:
        # Make the preview script executable
        os.chmod(preview_script_path, 0o755)
        
        # Build commands
        # Use proper module invocation instead of direct script path
        emdx_cmd = f"{sys.executable} -m emdx.cli"
        
        # Check if mdcat is available, otherwise use cat
        if subprocess.run(["which", "mdcat"], capture_output=True).returncode == 0:
            preview_cmd = f"{sys.executable} {preview_script_path} {{1}} | mdcat --columns 80"
        else:
            preview_cmd = f"{sys.executable} {preview_script_path} {{1}}"
        
        # Simple commands using emdx - made portable for all shells
        # Use mdcat for better markdown viewing
        if subprocess.run(["which", "mdcat"], capture_output=True).returncode == 0:
            view_cmd = f"{emdx_cmd} view {{1}} --raw --no-pager --no-header | mdcat --paginate"
        else:
            # Fallback to less if mdcat not available
            view_cmd = f"FORCE_COLOR=1 {emdx_cmd} view {{1}} --no-pager --no-header 2>&1 | less -R"
        edit_cmd = f"{emdx_cmd} edit {{1}} < /dev/tty"
        # Use Python for the delete confirmation to be shell-agnostic
        delete_cmd = f"{sys.executable} -c \"import sys; print('Delete document {{1}}? (soft delete - can be restored)'); print('Press y to confirm, any other key to cancel: ', end='', flush=True); import termios, tty; fd = sys.stdin.fileno(); old = termios.tcgetattr(fd); try: tty.setraw(fd); ch = sys.stdin.read(1); finally: termios.tcsetattr(fd, termios.TCSADRAIN, old); print(); sys.exit(0 if ch.lower() == 'y' else 1)\" < /dev/tty && {emdx_cmd} delete {{1}} < /dev/tty"
        reload_cmd = f"{sys.executable} -c \"from emdx.gui import format_document_list; print('\\n'.join(format_document_list()))\""
        
        # Log the command strings for debugging
        logger.debug(f"view_cmd: {view_cmd}")
        logger.debug(f"edit_cmd: {edit_cmd}")
        logger.debug(f"delete_cmd: {delete_cmd}")
        
        
        # Create a state file for leader mode
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            leader_file = f.name
            f.write('0')
        
        # Create Python helper scripts for leader mode
        set_leader_script = f'''import time; open('{leader_file}', 'w').write(str(time.time()))'''
        
        check_and_execute_script = '''
import sys
import time
import subprocess
import os

# Debug logging
debug_log = '/tmp/emdx_leader_debug.log'
with open(debug_log, 'a') as log:
    log.write(f"\\nLeader check called: {sys.argv}\\n")

leader_file = sys.argv[1]
action = sys.argv[2]
doc_id = sys.argv[3]

# Check if leader was pressed within last 2 seconds
try:
    with open(leader_file, 'r') as f:
        content = f.read().strip()
        leader_time = float(content) if content and content != '0' else 0
    
    current_time = time.time()
    time_diff = current_time - leader_time
    
    with open(debug_log, 'a') as log:
        log.write(f"Leader time: {leader_time}, Current time: {current_time}, Diff: {time_diff}\\n")
    
    if leader_time > 0 and time_diff < 2:
        # Leader was pressed, execute action
        with open(leader_file, 'w') as f:
            f.write('0')  # Reset
        
        with open(debug_log, 'a') as log:
            log.write(f"Executing action: {action} on doc {doc_id}\\n")
        
        if action == 'edit':
            subprocess.run([sys.executable, '-m', 'emdx.cli', 'edit', doc_id], stdin=open('/dev/tty'))
        elif action == 'delete':
            # Run the delete confirmation
            result = subprocess.run([sys.executable, '-c', """import sys; print('Delete document {0}? (soft delete - can be restored)'); print('Press y to confirm, any other key to cancel: ', end='', flush=True); import termios, tty; fd = sys.stdin.fileno(); old = termios.tcgetattr(fd); try: tty.setraw(fd); ch = sys.stdin.read(1); finally: termios.tcsetattr(fd, termios.TCSADRAIN, old); print(); sys.exit(0 if ch.lower() == 'y' else 1)""".format(doc_id)], stdin=open('/dev/tty'))
            if result.returncode == 0:
                subprocess.run([sys.executable, '-m', 'emdx.cli', 'delete', doc_id], stdin=open('/dev/tty'))
        elif action == 'view':
            result = subprocess.run([sys.executable, '-m', 'emdx.cli', 'view', doc_id, '--raw', '--no-pager', '--no-header'], capture_output=True, text=True)
            print(result.stdout)
    else:
        # No leader or timeout
        with open(debug_log, 'a') as log:
            log.write(f"No leader or timeout - exiting\\n")
        with open(leader_file, 'w') as f:
            f.write('0')
        sys.exit(1)
except Exception as e:
    with open(debug_log, 'a') as log:
        log.write(f"Error: {e}\\n")
    sys.exit(1)
'''
        
        # Save the check script
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            check_script_path = f.name
            f.write(check_and_execute_script)
        
        # Commands
        set_leader_cmd = f'''execute-silent({sys.executable} -c "{set_leader_script}")'''
        leader_edit_cmd = f"execute({sys.executable} {check_script_path} {leader_file} edit {{1}} < /dev/tty)"
        leader_delete_cmd = f"execute({sys.executable} {check_script_path} {leader_file} delete {{1}} < /dev/tty)"
        leader_view_cmd = f"execute({sys.executable} {check_script_path} {leader_file} view {{1}} | mdcat --paginate)"
        
        # Create fzf command with LEADER KEYS!
        fzf_cmd = [
            fzf_path,
            f"--preview={preview_cmd}",
            "--preview-window=right:60%:wrap",
            "--prompt=> ",
            # Navigation bindings
            "--bind=j:down",
            "--bind=k:up",
            "--bind=g:first",
            "--bind=G:last",
            "--bind=/:toggle-search",
            f"--bind=enter:execute({view_cmd})",
            # LEADER KEY (comma)
            f"--bind=,:change-prompt(LEADER> )+{set_leader_cmd}",
            # Leader actions
            f"--bind=e:{leader_edit_cmd}+reload({reload_cmd})+change-prompt(> )",
            f"--bind=d:{leader_delete_cmd}+reload({reload_cmd})+change-prompt(> )",
            f"--bind=v:{leader_view_cmd}+change-prompt(> )",
            # Preview scrolling
            "--bind=ctrl-d:preview-page-down",
            "--bind=ctrl-u:preview-page-up",
            "--bind=ctrl-f:preview-page-down",
            "--bind=ctrl-b:preview-page-up",
            # Global bindings
            f"--bind=ctrl-r:reload({reload_cmd})",
            "--bind=q:abort",
            "--bind=ctrl-c:abort",
            "--bind=esc:cancel",
            f"--bind=ctrl-h:execute({sys.executable} -c \"print('\\n📚 emdx - Help\\n\\nNavigation:\\n  j/k         Move up/down\\n  g/G         First/last item\\n  /           Toggle search\\n\\nLeader Key Actions:\\n  ,           Leader key (press first)\\n  ,e          Edit document\\n  ,d          Delete document\\n  ,v          View document\\n\\nDirect Actions:\\n  Enter       View document\\n\\nPreview:\\n  Ctrl-D/U    Preview scroll down/up\\n  Ctrl-F/B    Preview page down/up\\n\\nOther:\\n  Ctrl-R      Refresh list\\n  q           Quit\\n  Ctrl-C      Quit\\n  ESC         Cancel search / Quit\\n  Ctrl-H      Show this help\\n\\nNote: Press comma (,) followed by e/d/v within 2 seconds.\\nAll letters work normally in search mode.\\n\\nPress any key to continue...'); input()\" < /dev/tty)",
            "--header=📚 emdx - Documentation Index (,e: edit, ,d: delete, /: search, q: quit, ctrl-h: help)",
            "--delimiter= │ ",
            "--with-nth=1,2,3,4",
            "--info=inline",
            "--layout=default",
            "--cycle",
        ]
        
        logger.debug(f"Full fzf command: {' '.join(fzf_cmd)}")
        
        # App loop - stay in browser until quit
        while True:
            # Get document list
            doc_list = format_document_list()
            
            logger.debug(f"Running fzf with {len(doc_list)} documents")
            
            # Run fzf with direct terminal access
            result = subprocess.run(
                fzf_cmd,
                input='\n'.join(doc_list),
                text=True,
                capture_output=True
            )
            
            logger.debug(f"fzf exit code: {result.returncode}")
            logger.debug(f"fzf stdout: {result.stdout}")
            logger.debug(f"fzf stderr: {result.stderr}")
            
            # Check exit status
            # fzf returns 130 for ctrl-c, 1 for ESC/q
            if result.returncode in (130, 1):
                break
            elif result.returncode == 2:
                # fzf error - exit gracefully
                logger.error(f"fzf error: {result.stderr}")
                console.print(f"[red]Error running fzf: {result.stderr}[/red]")
                break
            
            # For any other status (including 0 for Enter), continue the loop
            
    finally:
        # Clean up temp files
        os.unlink(preview_script_path)
        if 'leader_file' in locals():
            try:
                os.unlink(leader_file)
            except:
                pass
        if 'check_script_path' in locals():
            try:
                os.unlink(check_script_path)
            except:
                pass
    
    # Clear screen on exit
    os.system('clear')


@app.command()
def modal():
    """True modal browser with vim-style navigation."""
    import curses
    from emdx.modal_browser import main as modal_main
    
    try:
        curses.wrapper(modal_main)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        console.print(f"❌ Error: {e}", style="red")
        raise typer.Exit(1)


@app.command()
def textual():
    """Modern TUI browser with mouse support and true modal behavior."""
    from emdx.textual_browser import run as textual_run
    
    try:
        textual_run()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        console.print(f"❌ Error: {e}", style="red")
        raise typer.Exit(1)


@app.command()
def markdown():
    """TUI browser with native markdown rendering (instant preview updates)."""
    from emdx.textual_markdown import run as markdown_run
    
    try:
        markdown_run()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        console.print(f"❌ Error: {e}", style="red")
        raise typer.Exit(1)


@app.command()
def seamless():
    """Seamless TUI browser with no-flash nvim integration."""
    from emdx.textual_browser_seamless import run_seamless
    
    try:
        run_seamless()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        console.print(f"❌ Error: {e}", style="red")
        raise typer.Exit(1)


@app.command()
def wrapper():
    """External wrapper approach - complete terminal state management."""
    from emdx.nvim_wrapper import run_textual_with_nvim_wrapper
    
    try:
        run_textual_with_nvim_wrapper()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        console.print(f"❌ Error: {e}", style="red")
        raise typer.Exit(1)
