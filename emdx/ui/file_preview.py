"""File preview widget for EMDX file browser."""

import mimetypes
from pathlib import Path
from typing import Optional

from rich.syntax import Syntax
from rich.text import Text
from textual.containers import ScrollableContainer
from textual.widgets import RichLog

from ..ui.markdown_config import MarkdownConfig


class FilePreview(ScrollableContainer):
    """Preview pane for selected file."""
    
    def __init__(self, **kwargs):
        """Initialize preview pane."""
        super().__init__(**kwargs)
        self.current_file: Optional[Path] = None
        self.add_class("file-preview")
    
    def compose(self):
        """Compose the preview layout."""
        yield RichLog(id="preview-content", wrap=True, highlight=True, markup=True)
    
    def on_mount(self) -> None:
        """Set up the preview pane."""
        self.styles.width = "50%"
    
    def preview_file(self, path: Path) -> None:
        """Preview the given file.
        
        Args:
            path: File path to preview
        """
        self.current_file = path
        log = self.query_one("#preview-content", RichLog)
        log.clear()
        
        if not path or not path.exists():
            log.write(Text("File not found", style="red"))
            return
        
        # Show file info header
        log.write(Text(f"📄 {path.name}", style="bold cyan"))
        
        if path.is_dir():
            self._preview_directory(path, log)
        else:
            # Get file info
            try:
                stat = path.stat()
                size = self._format_size(stat.st_size)
                
                # Check if in EMDX
                from .file_list import FileList
                file_list = FileList()
                in_emdx = " ✅ In EMDX" if file_list.check_file_in_emdx(path) else ""
                
                log.write(Text(f"Size: {size} | Type: {self._get_file_type(path)}{in_emdx}", style="dim"))
                log.write("")  # Blank line
                
                # Preview content
                self._preview_file_content(path, log)
                
            except PermissionError:
                log.write(Text("Permission denied", style="red"))
            except Exception as e:
                log.write(Text(f"Error: {e}", style="red"))
    
    def _preview_directory(self, path: Path, log: RichLog) -> None:
        """Preview directory contents."""
        try:
            items = list(path.iterdir())
            hidden_count = sum(1 for item in items if item.name.startswith('.'))
            visible_count = len(items) - hidden_count
            
            log.write(Text(f"Directory with {visible_count} items", style="dim"))
            if hidden_count:
                log.write(Text(f"({hidden_count} hidden)", style="dim"))
            
            # Show first few items
            log.write("")
            log.write(Text("Contents:", style="bold"))
            
            shown = 0
            for item in sorted(items, key=lambda x: (not x.is_dir(), x.name.lower())):
                if not item.name.startswith('.'):
                    icon = "📁" if item.is_dir() else "📄"
                    log.write(f"  {icon} {item.name}")
                    shown += 1
                    if shown >= 20:
                        remaining = visible_count - shown
                        if remaining > 0:
                            log.write(f"  ... and {remaining} more items")
                        break
                        
        except PermissionError:
            log.write(Text("Permission denied", style="red"))
    
    def _preview_file_content(self, path: Path, log: RichLog) -> None:
        """Preview file content with appropriate formatting."""
        # Determine file type
        mime_type, _ = mimetypes.guess_type(str(path))
        
        # Check if it's likely a text file
        if self._is_text_file(path, mime_type):
            try:
                # Read file content (limit size)
                max_size = 1024 * 1024  # 1MB
                if path.stat().st_size > max_size:
                    with open(path, 'r', encoding='utf-8', errors='replace') as f:
                        content = f.read(max_size)
                    content += f"\n\n... (file truncated, showing first {max_size} bytes)"
                else:
                    content = path.read_text(encoding='utf-8', errors='replace')
                
                # Apply syntax highlighting if applicable
                lexer = self._get_lexer(path)
                if lexer:
                    syntax = Syntax(
                        content,
                        lexer,
                        theme="monokai",
                        line_numbers=True,
                        word_wrap=True
                    )
                    log.write(syntax)
                elif path.suffix.lower() in {'.md', '.markdown'}:
                    # Use markdown rendering
                    # Limit preview length for performance
                    if len(content) > 10000:
                        content = content[:10000] + "\n\n... (preview truncated)"
                    md = MarkdownConfig.create_markdown(content)
                    log.write(md)
                else:
                    # Plain text
                    log.write(content)
                    
            except UnicodeDecodeError:
                log.write(Text("Binary file (not shown)", style="dim italic"))
            except Exception as e:
                log.write(Text(f"Error reading file: {e}", style="red"))
        else:
            # Binary file
            log.write(Text("Binary file", style="dim italic"))
            
            # Show hex preview for small files
            if path.stat().st_size < 1024:  # 1KB
                try:
                    with open(path, 'rb') as f:
                        data = f.read(256)
                    
                    log.write("")
                    log.write(Text("Hex preview:", style="bold"))
                    
                    # Format as hex dump
                    for i in range(0, len(data), 16):
                        chunk = data[i:i+16]
                        hex_part = ' '.join(f'{b:02x}' for b in chunk)
                        ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
                        log.write(f"{i:04x}  {hex_part:<48}  {ascii_part}")
                        
                except Exception:
                    pass
    
    def _is_text_file(self, path: Path, mime_type: Optional[str]) -> bool:
        """Determine if file is likely text."""
        # Check MIME type
        if mime_type and mime_type.startswith('text/'):
            return True
        
        # Check extension
        text_extensions = {
            '.txt', '.md', '.py', '.js', '.ts', '.jsx', '.tsx',
            '.java', '.c', '.cpp', '.h', '.hpp', '.rs', '.go',
            '.rb', '.php', '.swift', '.kt', '.scala', '.r',
            '.sh', '.bash', '.zsh', '.fish', '.ps1', '.bat',
            '.html', '.css', '.scss', '.sass', '.less',
            '.xml', '.json', '.yaml', '.yml', '.toml', '.ini',
            '.cfg', '.conf', '.log', '.csv', '.sql',
            '.vim', '.el', '.lisp', '.clj', '.ex', '.exs',
            '.pl', '.pm', '.lua', '.jl', '.m', '.R',
            '.dockerfile', '.gitignore', '.editorconfig',
            '.env', '.htaccess', '.nginx', '.apache'
        }
        
        if path.suffix.lower() in text_extensions:
            return True
        
        # Check for files without extension
        if not path.suffix and path.name in {
            'Makefile', 'Dockerfile', 'README', 'LICENSE',
            'AUTHORS', 'CONTRIBUTING', 'CHANGELOG', 'TODO'
        }:
            return True
        
        return False
    
    def _get_lexer(self, path: Path) -> Optional[str]:
        """Get syntax highlighting lexer for file."""
        # Map extensions to lexers
        lexer_map = {
            '.py': 'python',
            '.js': 'javascript',
            '.ts': 'typescript',
            '.jsx': 'jsx',
            '.tsx': 'tsx',
            '.java': 'java',
            '.c': 'c',
            '.cpp': 'cpp',
            '.h': 'c',
            '.hpp': 'cpp',
            '.rs': 'rust',
            '.go': 'go',
            '.rb': 'ruby',
            '.php': 'php',
            '.swift': 'swift',
            '.kt': 'kotlin',
            '.scala': 'scala',
            '.r': 'r',
            '.R': 'r',
            '.sh': 'bash',
            '.bash': 'bash',
            '.zsh': 'zsh',
            '.fish': 'fish',
            '.ps1': 'powershell',
            '.bat': 'batch',
            '.html': 'html',
            '.css': 'css',
            '.scss': 'scss',
            '.sass': 'sass',
            '.xml': 'xml',
            '.json': 'json',
            '.yaml': 'yaml',
            '.yml': 'yaml',
            '.toml': 'toml',
            '.ini': 'ini',
            '.sql': 'sql',
            '.vim': 'vim',
            '.lua': 'lua',
            '.jl': 'julia',
            '.m': 'matlab',
            '.dockerfile': 'dockerfile',
            '.nginx': 'nginx',
        }
        
        # Check by suffix
        lexer = lexer_map.get(path.suffix.lower())
        if lexer:
            return lexer
        
        # Check by filename
        if path.name == 'Dockerfile':
            return 'dockerfile'
        elif path.name == 'Makefile':
            return 'makefile'
        elif path.name.endswith('.gitignore'):
            return 'gitignore'
        
        return None
    
    def _get_file_type(self, path: Path) -> str:
        """Get human-readable file type."""
        mime_type, _ = mimetypes.guess_type(str(path))
        if mime_type:
            return mime_type
        
        if path.suffix:
            return f"{path.suffix[1:].upper()} file"
        
        return "Unknown"
    
    def _format_size(self, size: int) -> str:
        """Format file size."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                if unit == 'B':
                    return f"{size} {unit}"
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"
