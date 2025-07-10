#!/usr/bin/env python3
"""
True modal browser for emdx with vim-style navigation.

This replaces the fzf-based browser with a custom TUI that supports:
- NORMAL mode: j/k navigation, e/d/v execute actions  
- SEARCH mode: all keys just filter, ESC returns to normal
"""

import curses
import sys
import subprocess
import logging
from typing import List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime

from emdx.database import db

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='/tmp/emdx_modal_browser.log'
)
logger = logging.getLogger(__name__)


class Mode(Enum):
    NORMAL = "NORMAL"
    SEARCH = "SEARCH"


@dataclass
class Document:
    id: int
    title: str
    project: str
    created_at: datetime
    access_count: int
    content: str = ""
    
    def matches(self, query: str) -> bool:
        """Check if document matches search query."""
        query_lower = query.lower()
        return (query_lower in self.title.lower() or 
                query_lower in self.project.lower() or
                query_lower in self.content.lower())


class ModalBrowser:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.mode = Mode.NORMAL
        self.documents: List[Document] = []
        self.filtered_docs: List[Document] = []
        self.cursor_pos = 0
        self.search_query = ""
        self.status_message = ""
        self.preview_scroll = 0
        
        # Initialize curses
        curses.curs_set(0)  # Hide cursor
        self.stdscr.keypad(True)
        curses.start_color()
        curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLACK)  # Headers
        curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK)  # Mode indicator
        curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLACK)  # Selected item
        curses.init_pair(4, curses.COLOR_RED, curses.COLOR_BLACK)  # Status messages
        
        # Load documents
        self.load_documents()
        
    def load_documents(self):
        """Load documents from database."""
        try:
            docs = db.list_documents(limit=1000)
            self.documents = [
                Document(
                    id=doc['id'],
                    title=doc['title'],
                    project=doc['project'] or 'None',
                    created_at=doc['created_at'],
                    access_count=doc['access_count']
                )
                for doc in docs
            ]
            self.filtered_docs = self.documents.copy()
            logger.debug(f"Loaded {len(self.documents)} documents")
        except Exception as e:
            logger.error(f"Error loading documents: {e}")
            self.documents = []
            self.filtered_docs = []
    
    def filter_documents(self):
        """Filter documents based on search query."""
        if not self.search_query:
            self.filtered_docs = self.documents.copy()
        else:
            # Load content for searching if needed
            for doc in self.documents:
                if not doc.content:
                    try:
                        db_doc = db.get_document(str(doc.id))
                        if db_doc:
                            doc.content = db_doc['content']
                    except:
                        pass
            
            self.filtered_docs = [doc for doc in self.documents if doc.matches(self.search_query)]
        
        # Reset cursor if out of bounds
        if self.cursor_pos >= len(self.filtered_docs):
            self.cursor_pos = max(0, len(self.filtered_docs) - 1)
    
    def get_preview(self, doc: Document) -> List[str]:
        """Get preview lines for a document."""
        if not doc.content:
            try:
                db_doc = db.get_document(str(doc.id))
                if db_doc:
                    doc.content = db_doc['content']
            except:
                return ["Error loading preview"]
        
        lines = doc.content.split('\n')
        return lines
    
    def draw_header(self):
        """Draw the header with mode indicator."""
        height, width = self.stdscr.getmaxyx()
        
        # Mode indicator
        mode_str = f" {self.mode.value} "
        self.stdscr.attron(curses.color_pair(2))
        self.stdscr.addstr(0, 0, mode_str)
        self.stdscr.attroff(curses.color_pair(2))
        
        # Title
        title = " emdx - Documentation Browser"
        self.stdscr.attron(curses.color_pair(1))
        self.stdscr.addstr(0, len(mode_str), title)
        self.stdscr.attroff(curses.color_pair(1))
        
        # Help text
        if self.mode == Mode.NORMAL:
            help_text = "j/k:nav e:edit d:delete v:view /:search q:quit"
        else:
            help_text = "Type to search, ESC to cancel"
        
        help_x = width - len(help_text) - 1
        if help_x > len(mode_str) + len(title):
            self.stdscr.addstr(0, help_x, help_text)
    
    def draw_search_bar(self):
        """Draw search bar when in search mode."""
        if self.mode == Mode.SEARCH:
            height, width = self.stdscr.getmaxyx()
            search_str = f"Search: {self.search_query}_"
            self.stdscr.addstr(1, 0, search_str[:width-1])
    
    def draw_document_list(self):
        """Draw the document list."""
        height, width = self.stdscr.getmaxyx()
        
        # Calculate list area
        start_row = 3 if self.mode == Mode.SEARCH else 2
        list_height = height - start_row - 2  # Leave room for status
        list_width = min(80, width // 2)  # Half screen or 80 chars
        
        # Draw documents
        for i in range(list_height):
            row = start_row + i
            if row >= height - 1:
                break
                
            if i < len(self.filtered_docs):
                doc = self.filtered_docs[i]
                
                # Format document line
                title = doc.title[:40] + "..." if len(doc.title) > 40 else doc.title
                line = f"{doc.id:>5} │ {title:<40} │ {doc.project:<15}"
                
                # Highlight selected
                if i == self.cursor_pos:
                    self.stdscr.attron(curses.color_pair(3))
                    self.stdscr.addstr(row, 0, line[:list_width-1])
                    self.stdscr.attroff(curses.color_pair(3))
                else:
                    self.stdscr.addstr(row, 0, line[:list_width-1])
    
    def draw_preview(self):
        """Draw document preview on the right side."""
        height, width = self.stdscr.getmaxyx()
        
        # Calculate preview area
        start_col = min(82, width // 2 + 2)
        preview_width = width - start_col - 1
        start_row = 2
        preview_height = height - start_row - 2
        
        if preview_width < 20 or not self.filtered_docs:
            return
        
        # Get current document
        if 0 <= self.cursor_pos < len(self.filtered_docs):
            doc = self.filtered_docs[self.cursor_pos]
            lines = self.get_preview(doc)
            
            # Draw preview border
            self.stdscr.attron(curses.color_pair(1))
            self.stdscr.addstr(start_row - 1, start_col, f"═ Preview: {doc.title[:30]} " + "═" * (preview_width - 35))
            self.stdscr.attroff(curses.color_pair(1))
            
            # Draw preview content
            for i in range(preview_height):
                if self.preview_scroll + i < len(lines):
                    line = lines[self.preview_scroll + i]
                    # Truncate long lines
                    if len(line) > preview_width:
                        line = line[:preview_width-3] + "..."
                    try:
                        self.stdscr.addstr(start_row + i, start_col, line)
                    except:
                        pass
    
    def draw_status(self):
        """Draw status bar at bottom."""
        height, width = self.stdscr.getmaxyx()
        
        # Status message
        if self.status_message:
            self.stdscr.attron(curses.color_pair(4))
            self.stdscr.addstr(height - 1, 0, self.status_message[:width-1])
            self.stdscr.attroff(curses.color_pair(4))
        else:
            # Document count
            status = f" {len(self.filtered_docs)}/{len(self.documents)} documents"
            self.stdscr.addstr(height - 1, 0, status)
    
    def draw(self):
        """Draw the entire screen."""
        self.stdscr.clear()
        self.draw_header()
        self.draw_search_bar()
        self.draw_document_list()
        self.draw_preview()
        self.draw_status()
        self.stdscr.refresh()
    
    def handle_normal_mode(self, key):
        """Handle key press in normal mode."""
        if key == ord('j') or key == curses.KEY_DOWN:
            if self.cursor_pos < len(self.filtered_docs) - 1:
                self.cursor_pos += 1
                self.preview_scroll = 0
        elif key == ord('k') or key == curses.KEY_UP:
            if self.cursor_pos > 0:
                self.cursor_pos -= 1
                self.preview_scroll = 0
        elif key == ord('g'):
            self.cursor_pos = 0
            self.preview_scroll = 0
        elif key == ord('G'):
            self.cursor_pos = max(0, len(self.filtered_docs) - 1)
            self.preview_scroll = 0
        elif key == ord('/'):
            self.mode = Mode.SEARCH
            self.search_query = ""
        elif key == ord('e'):
            self.edit_document()
        elif key == ord('d'):
            self.delete_document()
        elif key == ord('v'):
            self.view_document()
        elif key == 10:  # Enter
            self.view_document()
        elif key == ord('q'):
            return False
        elif key == 4:  # Ctrl-D
            self.preview_scroll += 10
        elif key == 21:  # Ctrl-U
            self.preview_scroll = max(0, self.preview_scroll - 10)
        
        return True
    
    def handle_search_mode(self, key):
        """Handle key press in search mode."""
        if key == 27:  # ESC
            self.mode = Mode.NORMAL
            self.search_query = ""
            self.filter_documents()
        elif key == 10:  # Enter
            self.mode = Mode.NORMAL
        elif key == curses.KEY_BACKSPACE or key == 127:
            if self.search_query:
                self.search_query = self.search_query[:-1]
                self.filter_documents()
        elif 32 <= key <= 126:  # Printable characters
            self.search_query += chr(key)
            self.filter_documents()
        
        return True
    
    def edit_document(self):
        """Edit the selected document."""
        if 0 <= self.cursor_pos < len(self.filtered_docs):
            doc = self.filtered_docs[self.cursor_pos]
            curses.endwin()
            subprocess.run([sys.executable, '-m', 'emdx.cli', 'edit', str(doc.id)])
            self.stdscr = curses.initscr()
            curses.curs_set(0)
            self.stdscr.keypad(True)
            self.load_documents()
            self.filter_documents()
            self.status_message = f"Edited document {doc.id}"
    
    def delete_document(self):
        """Delete the selected document with confirmation."""
        if 0 <= self.cursor_pos < len(self.filtered_docs):
            doc = self.filtered_docs[self.cursor_pos]
            
            # Show confirmation
            height, width = self.stdscr.getmaxyx()
            confirm_msg = f"Delete document {doc.id}: {doc.title}? (y/n)"
            self.stdscr.attron(curses.color_pair(4))
            self.stdscr.addstr(height - 1, 0, confirm_msg[:width-1])
            self.stdscr.attroff(curses.color_pair(4))
            self.stdscr.refresh()
            
            key = self.stdscr.getch()
            if key == ord('y') or key == ord('Y'):
                try:
                    subprocess.run([sys.executable, '-m', 'emdx.cli', 'delete', str(doc.id)], 
                                 capture_output=True)
                    self.load_documents()
                    self.filter_documents()
                    self.status_message = f"Deleted document {doc.id}"
                except Exception as e:
                    self.status_message = f"Error deleting: {e}"
            else:
                self.status_message = "Delete cancelled"
    
    def view_document(self):
        """View the selected document."""
        if 0 <= self.cursor_pos < len(self.filtered_docs):
            doc = self.filtered_docs[self.cursor_pos]
            curses.endwin()
            # Use mdcat if available
            result = subprocess.run(['which', 'mdcat'], capture_output=True)
            if result.returncode == 0:
                cmd = [sys.executable, '-m', 'emdx.cli', 'view', str(doc.id), 
                       '--raw', '--no-pager', '--no-header']
                proc1 = subprocess.Popen(cmd, stdout=subprocess.PIPE)
                proc2 = subprocess.Popen(['mdcat', '--paginate'], stdin=proc1.stdout)
                proc1.stdout.close()
                proc2.wait()
            else:
                subprocess.run([sys.executable, '-m', 'emdx.cli', 'view', str(doc.id)])
            
            self.stdscr = curses.initscr()
            curses.curs_set(0)
            self.stdscr.keypad(True)
            # Update access count
            db.record_access(str(doc.id))
            self.load_documents()
            self.filter_documents()
    
    def run(self):
        """Main event loop."""
        while True:
            self.draw()
            key = self.stdscr.getch()
            
            if self.mode == Mode.NORMAL:
                if not self.handle_normal_mode(key):
                    break
            else:  # SEARCH mode
                if not self.handle_search_mode(key):
                    break


def main(stdscr):
    """Main entry point."""
    try:
        # Ensure database
        db.ensure_schema()
        
        # Check if any documents exist
        docs = db.list_documents(limit=1)
        if not docs:
            stdscr.clear()
            stdscr.addstr(0, 0, "No documents found in knowledge base.")
            stdscr.addstr(2, 0, "Get started with:")
            stdscr.addstr(3, 2, "emdx save <file>         - Save a markdown file")
            stdscr.addstr(4, 2, "emdx direct <title>      - Create a document directly")
            stdscr.addstr(5, 2, "emdx note 'quick note'   - Save a quick note")
            stdscr.addstr(7, 0, "Press any key to exit...")
            stdscr.refresh()
            stdscr.getch()
            return
        
        # Run browser
        browser = ModalBrowser(stdscr)
        browser.run()
        
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)