import os
from pathlib import Path
import selectors
import shutil
import subprocess
import tempfile
import time


POLICY = {
    'included': ['versioned .gitattributes from each pinned tree'],
    'excluded': ['input repository info/attributes', 'global attributes', 'system attributes', 'working tree', 'index'],
    'engine': 'git check-attr --source with NUL input/output',
    'values': 'literal Git output; set, unset and unspecified can also be string values',
    'objects': 'local read-only alternates; lazy fetch and replacement objects disabled',
}
ORDINARY = {'100644', '100755'}


class Failure(Exception):
    def __init__(self, message, code=2):
        super().__init__(message)
        self.code = code


def decode(value):
    return value.decode('utf-8', 'surrogateescape')


class Git:
    def __init__(self, root, max_bytes, timeout):
        self.root = root
        self.remaining = max_bytes
        self.deadline = time.monotonic() + timeout
        self.env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        self.env.update(
            HOME=str(root), XDG_CONFIG_HOME=str(root), LC_ALL='C',
            GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_SYSTEM=os.devnull,
            GIT_CONFIG_GLOBAL=os.devnull, GIT_ATTR_NOSYSTEM='1',
            GIT_NO_LAZY_FETCH='1', GIT_NO_REPLACE_OBJECTS='1',
            GIT_OPTIONAL_LOCKS='0', GIT_TERMINAL_PROMPT='0',
        )
        self.binary = shutil.which('git')
        if self.binary is None:
            raise Failure('Git executable not found on PATH.', 3)

    def guard(self):
        if time.monotonic() >= self.deadline:
            raise Failure('Time limit reached; comparison is incomplete.')

    def charge(self, count):
        self.remaining -= count
        if self.remaining < 0:
            raise Failure('Byte limit reached; comparison is incomplete.')
        self.guard()

    def run(self, repo, *args, data=b'', input_error=False):
        self.charge(len(data))
        command = [self.binary, '--no-replace-objects', '-c', 'core.hooksPath=' + os.devnull,
                   '-c', 'core.fsmonitor=false', '-c', 'core.attributesFile=' + os.devnull,
                   '-c', 'protocol.allow=never', '-c', 'gc.auto=0', '-C', str(repo), *args]
        with tempfile.TemporaryFile(dir=self.root) as stdin:
            stdin.write(data)
            stdin.seek(0)
            try:
                process = subprocess.Popen(command, stdin=stdin, stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE, env=self.env)
            except OSError as exc:
                raise Failure('Cannot start Git: ' + str(exc), 3) from exc
            output, errors = bytearray(), bytearray()
            try:
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ, output)
                    selector.register(process.stderr, selectors.EVENT_READ, errors)
                    while selector.get_map():
                        self.guard()
                        for key, _ in selector.select(min(0.1, max(0, self.deadline - time.monotonic()))):
                            chunk = os.read(key.fileobj.fileno(), 65536)
                            if not chunk:
                                selector.unregister(key.fileobj)
                                continue
                            self.charge(len(chunk))
                            key.data.extend(chunk)
                process.wait(timeout=max(0.001, self.deadline - time.monotonic()))
                self.guard()
            except subprocess.TimeoutExpired as exc:
                raise Failure('Time limit reached; comparison is incomplete.') from exc
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait()
                process.stdout.close()
                process.stderr.close()
            if process.returncode or errors:
                message = decode(bytes(errors)).strip() or 'exit ' + str(process.returncode)
                raise Failure('Git ' + args[0] + ': ' + message, 3 if input_error else 2)
            return bytes(output)


def inventory(git, repo, tree, max_paths, union):
    raw = git.run(repo, 'ls-tree', '-r', '-t', '-z', '--full-tree', tree)
    entries, objects, attributes = {}, set(), set()
    for record in raw.split(b'\0'):
        git.guard()
        if not record:
            continue
        metadata, path = record.split(b'\t', 1)
        mode, kind, oid = metadata.decode('ascii').split(' ')
        if kind != 'commit':
            objects.add(oid)
        if kind == 'tree':
            continue
        union.add(path)
        if len(union) > max_paths:
            raise Failure('Path limit reached; comparison is incomplete.')
        entries[path] = {'mode': mode, 'oid': oid}
        if path.rsplit(b'/', 1)[-1] == b'.gitattributes' and mode in ORDINARY:
            attributes.add(oid)
    return entries, objects, attributes


def verify_objects(git, repo, objects, attributes):
    ids = sorted(objects)
    raw = git.run(repo, 'cat-file', '--batch-check=%(objectname) %(objecttype) %(objectsize)',
                  data=''.join(oid + '\n' for oid in ids).encode('ascii'))
    lines = raw.splitlines()
    if len(lines) != len(ids):
        raise Failure('Incomplete object inventory from Git.')
    for oid, line in zip(ids, lines):
        git.guard()
        fields = line.split()
        if len(fields) != 3 or fields[0].decode('ascii') != oid:
            raise Failure('Required local object unavailable: ' + oid + '. Fetch it explicitly before retrying.')
        if oid in attributes:
            git.charge(int(fields[2]))


def attributes(git, repo, tree, paths, attrs):
    values = {}
    for start in range(0, len(paths), 256):
        batch = paths[start:start + 256]
        raw = git.run(repo, 'check-attr', '--source=' + tree, '--stdin', '-z', *attrs,
                      data=b''.join(path + b'\0' for path in batch))
        fields = raw.split(b'\0')
        if fields[-1:] != [b''] or (len(fields) - 1) % 3:
            raise Failure('Malformed NUL attribute response from Git.')
        batch_set = set(batch)
        for index in range(0, len(fields) - 1, 3):
            git.guard()
            path, attr, value = fields[index:index + 3]
            name = decode(attr)
            key = (path, name)
            if path not in batch_set or name not in attrs or key in values:
                raise Failure('Unexpected or duplicate path/attribute response from Git.')
            values[key] = decode(value)
        if any((path, attr) not in values for path in batch for attr in attrs):
            raise Failure('Missing path/attribute response from Git.')
    return values


def compare(repo, before, after, attrs, max_paths=100000, max_bytes=67108864, timeout=30):
    report = {
        'schema_version': 1, 'status': 'incomplete', 'complete': False,
        'before_oid': None, 'after_oid': None, 'before_tree': None, 'after_tree': None,
        'git_version': None, 'source_policy': POLICY, 'attributes': attrs,
        'limits': {'max_paths': max_paths, 'max_bytes': max_bytes, 'timeout_seconds': timeout},
        'inventory': [], 'differences': [], 'omissions': [], 'summary': None, 'errors': [],
    }
    try:
        with tempfile.TemporaryDirectory(prefix='attr-drift-') as temporary:
            root = Path(temporary)
            git = Git(root, max_bytes, timeout)
            report['git_version'] = decode(git.run(root, '--version')).strip()
            source = Path(repo).absolute()
            for label, rev in [('before', before), ('after', after)]:
                report[label + '_oid'] = decode(git.run(
                    source, 'rev-parse', '--verify', '--end-of-options', rev, input_error=True)).strip()
            object_dir = git.run(source, 'rev-parse', '--path-format=absolute', '--git-path', 'objects', input_error=True).removesuffix(b'\n')
            object_format = decode(git.run(source, 'rev-parse', '--show-object-format', input_error=True)).strip()
            isolated = root / 'repo.git'
            git.run(root, 'init', '--bare', '--quiet', '--template=', '--object-format=' + object_format, str(isolated))
            quoted = '"' + ''.join('\\%03o' % b if b < 32 or b >= 127 else '\\' + chr(b) if b in (34, 92) else chr(b) for b in object_dir) + '"\n'
            (isolated / 'objects' / 'info' / 'alternates').write_text(quoted, encoding='ascii')
            for label in ('before', 'after'):
                report[label + '_oid'] = decode(git.run(
                    isolated, 'rev-parse', '--verify', report[label + '_oid'] + '^{}')).strip()
                kind = git.run(isolated, 'cat-file', '-t', report[label + '_oid']).strip()
                if kind not in (b'commit', b'tree'):
                    raise Failure('Revision must identify a commit or tree, not ' + decode(kind) + '.', 3)
                report[label + '_tree'] = decode(git.run(
                    isolated, 'rev-parse', '--verify', report[label + '_oid'] + '^{tree}')).strip()
            support = git.run(isolated, 'check-attr', '--source=' + report['before_tree'], '--stdin', '-z', attrs[0])
            if support:
                raise Failure('Git check-attr --source capability probe returned unexpected data.')
            union = set()
            left, lo, la = inventory(git, isolated, report['before_tree'], max_paths, union)
            right, ro, ra = inventory(git, isolated, report['after_tree'], max_paths, union)
            verify_objects(git, isolated, lo | ro, la | ra)
            common = []
            added = removed = 0
            for path in sorted(union):
                git.guard()
                old, new = left.get(path), right.get(path)
                state = 'added' if old is None else 'removed' if new is None else 'common'
                added += state == 'added'
                removed += state == 'removed'
                regular = all(entry['mode'] in ORDINARY for entry in (old, new) if entry)
                item = {'path': decode(path), 'status': state, 'before': old, 'after': new,
                        'blob_changed': old['oid'] != new['oid'] if old and new and regular else None}
                report['inventory'].append(item)
                if not regular:
                    report['omissions'].append({'path': decode(path), 'reason': 'non-ordinary mode',
                                                'before_mode': old['mode'] if old else None,
                                                'after_mode': new['mode'] if new else None})
                elif state == 'common':
                    common.append(path)
            old_values = attributes(git, isolated, report['before_tree'], common, attrs)
            new_values = attributes(git, isolated, report['after_tree'], common, attrs)
            unchanged = pairs = 0
            for path in common:
                git.guard()
                changes = [{'attribute': attr, 'before': old_values[path, attr], 'after': new_values[path, attr]}
                           for attr in attrs if old_values[path, attr] != new_values[path, attr]]
                if changes:
                    changed = left[path]['oid'] != right[path]['oid']
                    unchanged += not changed
                    pairs += len(changes)
                    report['differences'].append({'path': decode(path), 'blob_changed': changed, 'changes': changes})
            report['summary'] = {
                'inventoried_paths': len(union), 'before_paths': len(left), 'after_paths': len(right),
                'compared_paths': len(common), 'added_paths': added, 'removed_paths': removed,
                'omitted_paths': len(report['omissions']), 'affected_paths': len(report['differences']),
                'affected_unchanged_blobs': unchanged, 'changed_attribute_pairs': pairs,
                'stable_paths': len(common) - len(report['differences']),
            }
            git.guard()
            report['complete'] = True
            report['status'] = 'differences' if report['differences'] else 'no-differences'
            return report, 1 if report['differences'] else 0
    except Failure as exc:
        report['status'] = 'input-error' if exc.code == 3 else 'incomplete'
        report['errors'].append(str(exc))
        report['differences'] = []
        report['summary'] = None
        report['complete'] = False
        return report, exc.code
    except (OSError, ValueError) as exc:
        report['errors'].append('Cannot complete comparison: ' + str(exc))
        report['differences'] = []
        report['summary'] = None
        report['complete'] = False
        return report, 2
