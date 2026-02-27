# Screencast — Re-record the TUI Demo GIF

Re-render `demo.gif` from `demo.tape` using VHS. Used after TUI changes to update the README screenshot.

## Steps

1. Run `vhs demo.tape` from the project root
2. Check the output size: `ls -lh demo.gif`
3. If > 5MB, tweak `demo.tape` settings (reduce `Framerate`, bump `PlaybackSpeed`, trim sleeps)
4. Report the file size

## If the tape needs updating

The tape lives at `demo.tape` in the project root. Edit it to adjust timing or navigation.

### VHS Quick Reference

| Command | Notes |
|---------|-------|
| `Type "text"` | Simulates typing |
| `Enter` / `Escape` | Key presses |
| `Sleep 2s` / `Sleep 500ms` | Pause |
| `Hide` / `Show` | Hide/show typing (for setup) |
| `Ctrl+c` | Key combo |
| `Up` / `Down` / `Left` / `Right` | Arrow keys (optional repeat: `Down 3`) |
| `Screenshot path.png` | Capture still frame |

### TUI Keybindings

| Key | Action |
|-----|--------|
| `1` | Docs tab |
| `2` | Tasks tab |
| `j` / `k` | Move down / up |
| `Enter` | Select/open |
| `Escape` | Go back |
| `q` | Quit |

### Tape Settings

| Setting | Current | Notes |
|---------|---------|-------|
| `Set Width` | `1400` | Terminal width in pixels |
| `Set Height` | `700` | Terminal height in pixels |
| `Set FontSize` | `16` | Font size |
| `Set Theme` | `"Dracula"` | `vhs themes` to list all |
| `Set TypingSpeed` | `50ms` | Delay between keystrokes |
| `Set PlaybackSpeed` | `1` | Speed multiplier |
| `Set Framerate` | `50` | Lower = smaller file |
