# emdx Tag System Aliases

Add these to your shell configuration file (`.bashrc`, `.zshrc`, or `.config/fish/config.fish`):

## Bash/Zsh aliases

```bash
# Quick tag search
alias ef='emdx find'
alias eft='emdx find --tags'
alias efta='emdx find --any-tags'

# Tag management  
alias et='emdx tag'
alias ets='emdx tags'  # show all tags
```

## Fish aliases

```fish
# Quick tag search
alias ef 'emdx find'
alias eft 'emdx find --tags'
alias efta 'emdx find --any-tags'

# Tag management
alias et 'emdx tag'
alias ets 'emdx tags'
```

## Usage Examples

```bash
# Find all documents with python tag
emdx find --tags python

# Find documents with either python OR rust tags
efta python,rust

# Find documents containing "api" with backend tag
ef api --tags backend

# Add tags to document
et 123 python api backend

# List all tags
ets

# Search by multiple tags (must have all)
eft python,backend,api

# Search by multiple tags (has any)
efta python,rust,go
```