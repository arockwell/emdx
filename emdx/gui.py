"""
GUI (fzf-based) interface for emdx
"""

import os
import subprocess
import sys
import tempfile
from typing import Optional
from pathlib import Path

import typer
from rich.console import Console

from emdx.database import db

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
    script = '''#!/usr/bin/env python3
import sys
from pathlib import Path

# Add emdx to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from emdx.database import db

doc_id = int(sys.argv[1])
doc = db.get_document(str(doc_id))
if doc:
    print(doc['content'])
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
        emdx_cmd = sys.argv[0]  # Get the emdx command path
        
        # Check if mdcat is available, otherwise use cat
        if subprocess.run(["which", "mdcat"], capture_output=True).returncode == 0:
            preview_cmd = f"{sys.executable} {preview_script_path} {{1}} | mdcat --columns 80"
        else:
            preview_cmd = f"{sys.executable} {preview_script_path} {{1}}"
        
        # Simple commands using emdx
        view_cmd = f"{emdx_cmd} view {{1}} < /dev/tty"
        reload_cmd = f"{sys.executable} -c 'from emdx.gui import format_document_list; print(\"\\n\".join(format_document_list()))'"
        
        # Create fzf command
        fzf_cmd = [
            fzf_path,
            f"--preview={preview_cmd}",
            "--preview-window=right:60%:wrap",
            "--bind=j:down",
            "--bind=k:up",
            "--bind=/:toggle-search",
            f"--bind=enter:execute({view_cmd})",
            "--bind=ctrl-d:preview-page-down",
            "--bind=ctrl-u:preview-page-up",
            "--bind=ctrl-f:preview-page-down",
            "--bind=ctrl-b:preview-page-up",
            "--bind=g:first",
            "--bind=G:last",
            f"--bind=ctrl-r:reload({reload_cmd})",
            "--bind=q:abort",
            "--bind=ctrl-c:abort",
            "--bind=ctrl-h:execute(echo -e \"\\n📚 emdx - Help\\n\\nNavigation:\\n  j/k, ↑/↓    Move up/down\\n  g/G         First/last item\\n  /           Toggle search\\n  Mouse       Click & scroll\\n\\nActions:\\n  Enter       View document\\n  Ctrl-R      Refresh list\\n\\nPreview:\\n  Ctrl-D/U    Scroll down/up\\n  Ctrl-F/B    Page down/up\\n\\nOther:\\n  q, Ctrl-C   Quit\\n\\nPress any key to continue...\" && read -n 1)",
            "--header=📚 emdx - Documentation Index (/: search, ctrl-h: help, q: quit)",
            "--delimiter= │ ",
            "--with-nth=1,2,3,4",
            "--info=inline",
            "--layout=default",
            "--cycle",
        ]
        
        # App loop - stay in browser until quit
        while True:
            # Get document list
            doc_list = format_document_list()
            
            # Run fzf with direct terminal access
            result = subprocess.run(
                fzf_cmd,
                input='\n'.join(doc_list),
                text=True
            )
            
            # Check exit status
            # fzf returns 130 for ctrl-c, 1 for ESC/q
            if result.returncode in (130, 1):
                break
            elif result.returncode == 2:
                # fzf error - exit gracefully
                break
            
            # For any other status (including 0 for Enter), continue the loop
            
    finally:
        # Clean up temp file
        os.unlink(preview_script_path)
    
    # Clear screen on exit
    os.system('clear')
