# Validation

Checked on 2026-10-31 with Python 3.9.6 and Git 2.54.0 on macOS.

- A fresh Git clone ran all 35 tests successfully in 26.609 seconds. An independent reviewer followed only the README from another fresh clone: all 35 tests passed in 15.716 seconds, isolated `pipx install .` succeeded, and the installed quick-start command reported 20 compared paths, all stable.
- The six-path fixture matched native queries in a separate temporary bare repository: exactly `a.txt` and `docs/b.txt` changed from LF to CRLF, with identical blob IDs. Four paths stayed stable.
- Three deliberately broken implementations were detected by the main integration test: comparing only content-changed files, omitting the source tree, and losing the nested exception. Reproduce with `python3 tools/check_mutations.py`.
- A local HTTP trap received its control request, then no requests during a missing-promisor-object comparison. Original file, index, ref and object hashes were preserved.
- Missing root trees and commits return incomplete coverage. Blob revisions return an input error. A forced deadline after aggregation confirmed that failed reports discard partial totals.
- Local pip and pipx installations built and ran version 0.1.0. The GitHub pipx installation command was attempted again and failed with `Repository not found`. The independent reviewer confirmed that remote limitation. Hosted CI has not run yet.
- VHS recorded `docs/demo.tape` and exited 0. FFprobe measured `docs/demo.gif` at 17.76 seconds, 1120 by 650 pixels, 444 frames. Decoding with FFmpeg produced 109 distinct pixel hashes. Visual inspection of frames 0, 220 and 340 confirmed the complete report in the first frame and commands being typed later in the loop. Both affected paths and their LF-to-CRLF changes are readable. The visible command is the installed `attr-drift` entry point. The tape uses VHS's `LoopOffset` setting for the useful opening frame.
- Recording used a local VHS build with browser endpoint attachment and bounded page closure, plus limited FFmpeg worker threads. The stock recorder could not launch Chromium in this restricted environment; the local build recorded the tape against an existing local Chromium instance. No terminal output was fabricated or composited.
- `git log --all --format='%h %an <%ae> | %cn <%ce>%n%B'` verified both existing commits: author and committer are `ZERACK <189363748+itzjk@users.noreply.github.com>`, with no co-author trailers. A scan of the 20 tracked files found no private path, name, internal product or credential markers. The README has 692 whitespace-separated words.

The CI matrix covers Python 3.9 and 3.13 on Linux and macOS. Linux additionally exercises path bytes that macOS filesystems cannot represent. Those hosted runs remain to be verified.
