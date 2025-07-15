#!/usr/bin/env python3
"""Centralized widget IDs to ensure consistency across the UI."""

# Container IDs
PREVIEW_CONTAINER = "preview"           # ScrollableContainer for preview/edit/selection
EDIT_CONTAINER = "edit-container"       # Horizontal container for line numbers + editor
SIDEBAR_CONTAINER = "sidebar"           # Left sidebar container
STATUS_BAR = "status"                   # Status bar at bottom

# Content widget IDs  
PREVIEW_CONTENT = "preview-content"     # RichLog for normal preview
EDIT_AREA = "edit-area"                # VimEditTextArea for editing
LINE_NUMBERS = "line-numbers"          # Line numbers widget

# Table IDs
DOC_TABLE = "doc-table"                # Document list table
GIT_TABLE = "git-table"                # Git diff table
FILE_LIST = "file-list"                # File browser list

# Input IDs
SEARCH_INPUT = "search-input"          # Search input field
TAG_INPUT = "tag-input"                # Tag input field

# Browser specific
FILE_PREVIEW = "file-preview"          # FilePreview widget
FILE_STATUS_BAR = "file-status-bar"    # File browser status