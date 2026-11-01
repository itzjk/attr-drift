# Report contract, version 1

`--json` writes one JSON object to stdout. Text output quotes paths and values, escaping control characters. JSON uses UTF-8 decoding with surrogateescape for non-UTF-8 path bytes, then ASCII JSON escapes. Consumers needing the original path bytes can encode decoded strings with UTF-8 and surrogateescape.

A completed report contains:

- `schema_version`, `status`, `complete`, and `git_version`.
- `before_oid` and `after_oid`: peeled revision IDs fixed before evaluation. Tree revisions are accepted. `before_tree` and `after_tree` identify their trees.
- `source_policy`, `attributes`, and the requested `limits`.
- `inventory`: union of leaf paths in byte-sorted order. Each has `status` (`common`, `added`, `removed`), `before` and `after` entries containing `mode` and `oid`, or null. `blob_changed` is boolean for common ordinary files, null otherwise.
- `differences`: affected common ordinary paths, their `blob_changed` flag, and `changes`, each containing `attribute`, `before`, `after` as literal Git strings.
- `omissions`: paths with non-ordinary modes on either side, with both modes and a reason. A regular file replaced by a symlink is omitted too. Modes `100644` and `100755` are ordinary; `120000` is a symlink; `160000` is a gitlink. Gitlinks are opaque, and their target commit need not exist locally.
- `summary`: before/after/union, compared, stable, added, removed, omitted, affected path counts, affected unchanged blobs, and changed attribute pairs.
- `errors`: empty on complete reports.

A failure has `complete: false`, a nonempty `errors` array and exit 2 or 3. `summary` is null and `differences` is cleared: no partial comparison is presented as a total. Inventory may be retained if already completed. Argument parsing errors return a minimal versioned object when `--json` is present.

## Scope and safety

Attribute values are Git's literal output. No typed interpretation is added, including for ambiguous string values. Complete coverage applies to common ordinary files and selected attributes. Additions, removals and explicit special-mode exclusions are not failures.

Resolution reads refs and local configuration only to find and pin input objects. Attribute evaluation uses a newly initialized bare repository with an empty template and its own configuration. Global/system config and attributes, XDG attributes, input `info/attributes`, inherited `GIT_*` settings, replacements, hooks and fsmonitor are disabled or excluded. Alternates provide read access to the original object store, including existing object alternates. Git warnings are failures so ignored rules cannot produce a reassuring empty result.

All tree and blob objects referenced by the two snapshots are checked for local availability, including added and removed files. No history traversal or integrity fsck is performed. Object availability checks are not a guarantee against concurrent deletion or disk corruption. Attribute-blob sizes count toward the byte budget before evaluation. Git subprocess input, stdout and stderr share that budget. Other blob contents are not loaded. The path limit bounds the union of leaf paths, not directories; Git stream bytes bound tree enumeration. The deadline covers comparison work, with subprocess termination on expiry; rendering and OS scheduling are not hard real-time guarantees.

There are no remotes in the evaluation repository. Lazy fetch is disabled, protocols are denied, and Git never checks out files. Use a trusted Git executable on PATH. The repository is treated as data, not as an executable project. Built-in Git behavior remains the source of truth; this tool does not lint patterns or compute checkout bytes.

## CI

Treat exit 1 as a review signal and exit 2 or 3 as a failed check. Read `complete` before consuming totals. Do not use `|| true` to discard all nonzero statuses. Select attributes explicitly for your review policy, such as `text,eol,filter,diff,merge,export-ignore`.
