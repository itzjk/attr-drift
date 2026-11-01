Output docs/demo.gif
Require attr-drift
Require python3
Require git
Set Shell "bash"
Set FontSize 19
Set Width 1120
Set Height 650
Set Padding 24
Set Theme "Dracula"
Set TypingSpeed 35ms
Set PlaybackSpeed 1
Set Framerate 25
Set LoopOffset 50%
Hide
Type `export PS1='$ '; export DEMO=$(mktemp -d)/repo; python3 tools/make_demo.py "$DEMO"; cd "$DEMO"; clear`
Enter
Sleep 6s
Show
Type `git diff-tree --no-commit-id --name-only -r before after`
Enter
Sleep 2s
Type `attr-drift before after --repo . --attrs text,eol`
Enter
Sleep 12s
