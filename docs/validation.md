# Validation

Checked on 2026-10-31 with Python 3.9.6 and Git 2.54.0 on macOS.

- A fresh Git clone ran all 35 tests successfully in 19.527 seconds. An independent source-copy review also passed all 35 tests and exercised the installed console entry point.
- The six-path fixture matched native queries in a separate temporary bare repository: exactly `a.txt` and `docs/b.txt` changed from LF to CRLF, with identical blob IDs. Four paths stayed stable.
- Three deliberately broken implementations were detected by the main integration test: comparing only content-changed files, omitting the source tree, and losing the nested exception. Reproduce with `python3 tools/check_mutations.py`.
- A local HTTP trap received its control request, then no requests during a missing-promisor-object comparison. Original file, index, ref and object hashes were preserved.
- Missing root trees and commits return incomplete coverage. Blob revisions return an input error. A forced deadline after aggregation confirmed that failed reports discard partial totals.
- Local pip and pipx installations built and ran version 0.1.0. GitHub installation was attempted but the repository was unavailable before publication. Hosted CI has not run yet.
- VHS recorded `docs/demo.tape` and exited 0. FFprobe measured `docs/demo.gif` at 15.52 seconds, 1120 by 650 pixels, 388 frames. A local recorder timeout around browser closure and limited FFmpeg worker threads were needed in the restricted recording environment. The GIF shows commands executing the CLI against the generated fixture.

The CI matrix covers Python 3.9 and 3.13 on Linux and macOS. Linux additionally exercises path bytes that macOS filesystems cannot represent. Those hosted runs remain to be verified.
