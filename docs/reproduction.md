# Reproduce the unchanged-file case

Run from a clone with Python 3.9+ and Git supporting `check-attr --source`:

```sh
python3 tools/make_demo.py /tmp/attr-drift-example
git -C /tmp/attr-drift-example diff-tree --no-commit-id --name-only -r before after
python3 -m attr_drift before after --repo /tmp/attr-drift-example --attrs text,eol
```

The target directory must not exist. The generator creates six tracked paths, two commits and tags `before` and `after`. Only the root `.gitattributes` changes from `*.txt text eol=lf` to `*.txt text eol=crlf`. The nested rule under `protected/` stays on LF. The diff prints `.gitattributes`; attr-drift exits 1 and prints:

```text
attr-drift: 2 affected paths (2 unchanged blobs)
6 compared | 4 stable | 0 added | 0 removed | 0 omitted
```

The affected paths are exactly `a.txt` and `docs/b.txt`, each with `eol: "lf" -> "crlf"`. `protected/c.txt` stays unchanged. The blob IDs of both affected files stay identical.

## Baseline evaluation, 2026-10-31

Before implementing the CLI, Git 2.54.0 and the short script in `native_compare.py` produced the same two path/value changes:

```sh
python3 docs/native_compare.py /tmp/attr-drift-example before after
```

That script is a baseline for this controlled fixture. It uses the caller's normal Git attribute sources and has no resource or coverage contract. The packaged CLI adds source isolation, object checks, mode handling, limits, installation and structured results.

The published `@fumiya-kume/gitattributes-lint` package was also executed against this fixture, using `--no-config --format json --cwd`. It returned `valid: true`, six checked paths, and effective names `text` and `eol`, with no errors or warnings. Its [documented CLI](https://github.com/fumiya-kume/gitattributes-lint) has no two-revision comparison option. This is a bounded alternative check, not proof that no equivalent tool exists. The ToolQuill snapshot simulator could not be retrieved during this implementation review, so it was not executed.

The brief's [code-review interest reference](https://github.com/multica-ai/andrej-karpathy-skills) concerns assistant coding practices. It is not evidence of attribute incidents, demand for this CLI or measured time savings. The synthetic reproduction is the direct evidence used here; broader demand remains unmeasured.

## Tests and recording

```sh
python3 -m unittest discover -s tests -v
vhs docs/demo.tape
```

The tape creates a new temporary fixture and runs the actual CLI, first showing the ordinary diff and then the effective attribute changes. It records a 10-25 second GIF at `docs/demo.gif`. VHS requires ttyd, FFmpeg and a compatible Chromium installation. Run it from the repository root. The CLI's exit 1 in the demo means differences were found.
