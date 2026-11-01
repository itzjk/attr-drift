Output docs/demo.gif
Set Shell "bash"
Set FontSize 19
Set Width 1120
Set Height 650
Set Padding 24
Set Theme "Dracula"
Set TypingSpeed 35ms
Set PlaybackSpeed 1
Set Framerate 25
Hide
Type `export PS1='$ '; export DEMO=$(mktemp -d)/repo; python3 tools/make_demo.py "$DEMO"; clear`
Enter
Sleep 6s
Show
Type `git -C "$DEMO" diff-tree --no-commit-id --name-only -r before after`
Enter
Sleep 2s
Type `python3 -m attr_drift before after --repo "$DEMO" --attrs text,eol`
Enter
Sleep 9s
