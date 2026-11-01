# attr-drift

See which tracked files inherit different Git attributes, even when their contents stay the same.

[![CI](https://github.com/itzjk/attr-drift/actions/workflows/ci.yml/badge.svg)](https://github.com/itzjk/attr-drift/actions/workflows/ci.yml)
[![MIT license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

![A policy-only diff changes eol on two unchanged files](docs/demo.gif)

## Quick start

Install with Python 3.9+ and [pipx](https://pipx.pypa.io/):

```sh
pipx install git+https://github.com/itzjk/attr-drift.git
```

Compare two local revisions:

```sh
attr-drift HEAD~1 HEAD --repo . --attrs text,eol
```

Requires Git with `check-attr --source` support, checked at runtime. Linux and macOS are supported.

## Features

- Find policy changes on files missing from the ordinary content diff.
- See each attribute's previous and next value, with unchanged blobs called out.
- Keep additions, removals, symlinks and submodule entries visible and separate.
- Compare committed rules without checking out either revision or touching your index.
- Use versioned JSON and distinct exit codes in review scripts and CI.
- Stop with incomplete coverage when objects, resource budgets or Git support are missing.

## Why

Editing a root `.gitattributes` can change thousands of untouched files while the diff shows one file. In the [six-file reproduction](docs/reproduction.md), only the root rule changes, yet `a.txt` and `docs/b.txt` switch from `lf` to `crlf`; an explicit nested exception stays on `lf`.

[Git exposes the underlying query](https://git-scm.com/docs/git-check-attr), and [gitattributes-lint](https://github.com/fumiya-kume/gitattributes-lint) checks syntax and current effective attributes. attr-drift packages the two-tree inventory, comparison and coverage report; the reproduction demonstrates the gap, rather than measuring product demand.

## How it works

Both revisions resolve to fixed object IDs before comparison. A temporary bare repository reads their local objects through alternates, inventories the union with `ls-tree -z`, and asks Git for selected attributes on common ordinary files using `check-attr --source` and NUL-delimited input and output. Results match by path and attribute, preserving Git's own nested rules and macros. Global, system and input-repository `info/attributes` are excluded. There is no checkout, normalization or execution of hooks, filters, diff drivers, textconv or project commands. The original repository receives no writes.

## Usage

| Argument or option | Purpose |
| --- | --- |
| `<before> <after>` | Local commits, tags, branches or tree IDs |
| `--repo PATH` | Repository to read; defaults to `.` |
| `--attrs text,eol` | Required explicit, comma-separated attribute selection |
| `--json` | JSON report, `schema_version: 1` |
| `--max-paths N` | Union path budget; default 100,000 |
| `--max-bytes N` | Git I/O plus unique attribute-blob bytes; default 67,108,864 |
| `--timeout SECONDS` | Comparison deadline; default 30 seconds |
| `--version` | Installed version |

Exit codes: **0** means no attribute differences, **1** means differences, **2** means incomplete coverage, and **3** means invalid input. An added or removed path alone does not count as attribute drift. A limit never becomes a successful empty report. [Report details](docs/report.md) describe inventory, exclusions and CI handling.

## FAQ

**Does it use my working tree or staged attributes?** No. Each side reads versioned rules from its pinned tree. Uncommitted changes do not affect either side.

**Will it download missing objects?** No. Lazy fetching and network protocols are disabled. Fetch required objects yourself, then rerun the comparison.

**Does “blob unchanged” mean checkout bytes stay identical?** It means the stored blob ID stayed the same. Checkout behavior also depends on configuration and available filters; this report compares attributes only.

**Can I request custom attributes?** Yes, including attributes expanded through macros. Select up to 64 unique names. Reserved `builtin_*` attributes are outside versioned-rule scope.

## Limitations

- Common ordinary files are compared; additions and removals are inventoried without a cross-tree attribute comparison.
- Symlinks, gitlinks and transitions involving those modes appear as explicit omissions. A complete report covers the declared ordinary-file scope, not submodule contents.
- Local objects must be available. Remote URLs, rename inference and uncommitted files are outside scope.
- Git returns literal strings. A value named `unspecified`, `set` or `unset` can be indistinguishable from its corresponding special state.
- Git diagnostics make coverage incomplete, including warnings about rules Git ignores. The report does not identify which rule caused a change.

## Contributing

Run `python3 -m unittest discover -s tests -v`; see [reproduction and demo recording](docs/reproduction.md) for the fixture and VHS tape.

## License

[MIT](LICENSE).
