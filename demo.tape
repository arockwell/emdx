# emdx TUI Demo — Docs & Tasks
# Run: vhs demo.tape

Output demo.gif
Require emdx

Set Shell "bash"
Set FontSize 16
Set Width 900
Set Height 700
Set Padding 20
Set Theme "Dracula"
Set TypingSpeed 50ms
Set PlaybackSpeed 1

# Launch the TUI — hidden so we skip the typing
Hide
Type "cd /Users/alexrockwell/dev/worktrees/emdx-explore && poetry run emdx gui"
Enter
Sleep 4s
Show

# --- Docs screen (tab 1, default) ---
Sleep 1s
Type "j"
Sleep 500ms
Type "j"
Sleep 500ms
Type "j"
Sleep 500ms
Type "j"
Sleep 500ms
Type "j"
Sleep 800ms

# Move back up
Type "k"
Sleep 500ms
Type "k"
Sleep 500ms
Type "k"
Sleep 800ms

# --- Switch to Tasks screen (tab 2) ---
Type "2"
Sleep 2s

# Move to first task so details load
Type "j"
Sleep 1s

# Browse down
Type "j"
Sleep 500ms
Type "j"
Sleep 500ms
Type "j"
Sleep 800ms

# Move back up
Type "k"
Sleep 500ms
Type "k"
Sleep 500ms
Type "k"
Sleep 1s

# Quit — hidden so we don't show the exit
Hide
Type "q"
Sleep 1s
