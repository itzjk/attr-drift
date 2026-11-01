import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

from attr_drift.core import compare, attributes, Failure
from tools.make_demo import make_demo

ROOT = Path(__file__).resolve().parents[1]


class Integration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='attr-drift-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = make_demo(self.root / 'input')
        self.env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        self.env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)

    def git(self, *args, data=None):
        return subprocess.check_output(['git', '-C', str(self.repo), *args],
                                       input=data, env=self.env, stderr=subprocess.PIPE)

    def cli(self, *options, before='before', after='after', env=None):
        result = subprocess.run([sys.executable, '-m', 'attr_drift', before, after,
                                 '--repo', str(self.repo), '--attrs', 'text,eol', '--json', *options],
                                cwd=ROOT, env=env or self.env, capture_output=True, timeout=45)
        self.assertEqual(result.stderr, b'')
        return result.returncode, json.loads(result.stdout)

    def commit(self, message='Update policy'):
        self.git('add', '-A')
        self.git('commit', '-qm', message)
        self.git('tag', '-f', 'after')

    def snapshot(self):
        return {str(p.relative_to(self.repo)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.repo.rglob('*') if p.is_file() and not p.is_symlink()}

    def native(self, rev, attrs, paths):
        isolated = self.root / ('native-' + rev)
        subprocess.check_call(['git', 'init', '--bare', '-q', '--template=', str(isolated)], env=self.env)
        (isolated / 'objects/info/alternates').write_text(str(self.repo / '.git/objects') + '\n')
        oid = self.git('rev-parse', rev).strip().decode()
        env = dict(self.env, GIT_ATTR_NOSYSTEM='1', HOME=str(self.root), XDG_CONFIG_HOME=str(self.root))
        result = subprocess.check_output(['git', '-c', 'core.attributesFile=' + os.devnull, '-C', str(isolated),
                                          'check-attr', '--source=' + oid, '--stdin', '-z', *attrs],
                                         input=b''.join(p + b'\0' for p in paths), env=env)
        fields = result.split(b'\0')[:-1]
        return {(p, a): v for p, a, v in zip(fields[::3], fields[1::3], fields[2::3])}

    def test_main_case_exact_paths_values_and_native_oracle(self):
        snapshot = self.snapshot()
        code, report = self.cli()
        self.assertEqual(code, 1)
        self.assertTrue(report['complete'])
        self.assertEqual(report['schema_version'], 1)
        self.assertEqual(report['summary'], {
            'inventoried_paths': 6, 'before_paths': 6, 'after_paths': 6, 'compared_paths': 6,
            'added_paths': 0, 'removed_paths': 0, 'omitted_paths': 0, 'affected_paths': 2,
            'affected_unchanged_blobs': 2, 'changed_attribute_pairs': 2, 'stable_paths': 4,
        })
        self.assertEqual(report['differences'], [
            {'path': p, 'blob_changed': False, 'changes': [{'attribute': 'eol', 'before': 'lf', 'after': 'crlf'}]}
            for p in ['a.txt', 'docs/b.txt']
        ])
        self.assertEqual(self.git('diff-tree', '--no-commit-id', '--name-only', '-r', 'before', 'after'), b'.gitattributes\n')
        paths = [entry['path'].encode() for entry in report['inventory']]
        old, new = self.native('before', ['text', 'eol'], paths), self.native('after', ['text', 'eol'], paths)
        self.assertEqual({key: (value, new[key]) for key, value in old.items() if value != new[key]},
                         {(p, b'eol'): (b'lf', b'crlf') for p in [b'a.txt', b'docs/b.txt']})
        self.assertEqual(new[b'protected/c.txt', b'eol'], b'lf')
        self.assertEqual(snapshot, self.snapshot())

    def test_checkout_and_index_do_not_supply_rules(self):
        (self.repo / '.gitattributes').write_text('*.txt -text eol=checkout\n')
        self.git('add', '.gitattributes')
        (self.repo / 'protected/.gitattributes').unlink()
        snapshot = self.snapshot()
        code, report = self.cli()
        self.assertEqual(code, 1)
        self.assertEqual([d['path'] for d in report['differences']], ['a.txt', 'docs/b.txt'])
        self.assertEqual(snapshot, self.snapshot())

    def test_external_attributes_and_config_cannot_contaminate(self):
        global_attrs = self.root / 'global-attributes'
        global_attrs.write_text('* text=external eol=external\n')
        config = self.root / 'gitconfig'
        config.write_text('[core]\n attributesFile = ' + str(global_attrs) + '\n')
        xdg = self.root / 'xdg/git'
        xdg.mkdir(parents=True)
        (xdg / 'attributes').write_text('* text=xdg eol=xdg\n')
        (self.repo / '.git/info').mkdir(exist_ok=True)
        (self.repo / '.git/info/attributes').write_text('* text=info eol=info\n')
        self.git('config', 'core.attributesFile', str(global_attrs))
        self.git('config', 'core.fsmonitor', 'touch ' + str(self.root / 'executed'))
        self.git('config', 'filter.probe.process', 'touch ' + str(self.root / 'executed'))
        env = dict(self.env, GIT_CONFIG_GLOBAL=str(config), HOME=str(self.root), XDG_CONFIG_HOME=str(xdg.parent),
                   GIT_ATTR_SOURCE='before', GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='core.attributesFile',
                   GIT_CONFIG_VALUE_0=str(global_attrs))
        snapshot = self.snapshot()
        code, report = self.cli(env=env)
        self.assertEqual(code, 1)
        self.assertEqual(report['summary']['affected_paths'], 2)
        self.assertEqual(report['differences'][0]['changes'][0]['after'], 'crlf')
        self.assertFalse((self.root / 'executed').exists())
        self.assertEqual(snapshot, self.snapshot())

    def test_macro_removed_attribute_new_value_and_blob_change(self):
        (self.repo / '.gitattributes').write_text('[attr]policy text eol=lf custom=old gone\n*.txt policy\n')
        self.commit()
        self.git('tag', '-f', 'before')
        (self.repo / '.gitattributes').write_text('[attr]policy -text eol=crlf custom=new added=value\n*.txt policy\n')
        (self.repo / 'a.txt').write_text('changed\n')
        self.commit()
        report, code = compare(self.repo, 'before', 'after', ['text', 'eol', 'custom', 'gone', 'added'])
        self.assertEqual(code, 1)
        item = next(item for item in report['differences'] if item['path'] == 'a.txt')
        self.assertTrue(item['blob_changed'])
        self.assertEqual(item['changes'], [
            {'attribute': a, 'before': b, 'after': c} for a, b, c in [
                ('text', 'set', 'unset'), ('eol', 'lf', 'crlf'), ('custom', 'old', 'new'),
                ('gone', 'set', 'unspecified'), ('added', 'unspecified', 'value')]])
        self.assertNotIn('protected/c.txt', [item['path'] for item in report['differences'] if any(
            c['attribute'] == 'eol' for c in item['changes'])])

    def test_literal_unspecified_stays_literal(self):
        (self.repo / '.gitattributes').write_text('*.txt custom=unspecified\n')
        self.commit()
        report, code = compare(self.repo, 'before', 'after', ['custom'])
        self.assertEqual(code, 0)
        self.assertEqual(report['differences'], [])

    def test_added_deleted_are_separate_not_renames(self):
        (self.repo / 'a.txt').unlink()
        (self.repo / 'new.txt').write_text('alpha\n')
        self.commit()
        code, report = self.cli()
        self.assertEqual(code, 1)
        states = {item['path']: item['status'] for item in report['inventory']}
        self.assertEqual(states['a.txt'], 'removed')
        self.assertEqual(states['new.txt'], 'added')
        self.assertEqual([item['path'] for item in report['differences']], ['docs/b.txt'])
        self.assertEqual(report['summary']['added_paths'], 1)
        self.assertEqual(report['summary']['removed_paths'], 1)

    def test_comments_only_and_content_only_are_not_drift(self):
        self.git('reset', '--hard', 'before')
        with (self.repo / '.gitattributes').open('a') as f:
            f.write('# A comment\n')
        (self.repo / 'a.txt').write_text('content change\n')
        self.commit()
        snapshot = self.snapshot()
        code, report = self.cli()
        self.assertEqual(code, 0)
        self.assertEqual(report['summary']['affected_paths'], 0)
        item = next(x for x in report['inventory'] if x['path'] == 'a.txt')
        self.assertTrue(item['blob_changed'])
        self.assertEqual(snapshot, self.snapshot())

    def test_nul_paths_spaces_tabs_newlines_unicode_and_non_utf8(self):
        names = ['space name.txt', 'tab\tname.txt', 'line\nname.txt', 'café-猫.txt', 'escape\x1b[31m.txt']
        if sys.platform.startswith('linux'):
            names.append(os.fsdecode(b'raw-\xff.txt'))
        self.git('reset', '--hard', 'before')
        for name in names:
            (self.repo / name).write_bytes(b'unchanged\n')
        self.commit()
        self.git('tag', '-f', 'before')
        (self.repo / '.gitattributes').write_text('*.txt text eol=crlf\n')
        self.commit()
        code, report = self.cli()
        self.assertEqual(code, 1)
        paths = {item['path'] for item in report['differences']}
        self.assertEqual(paths, set(names + ['a.txt', 'docs/b.txt']))
        result = subprocess.run([sys.executable, '-m', 'attr_drift', 'before', 'after', '--repo', str(self.repo),
                                 '--attrs', 'eol'], cwd=ROOT, capture_output=True)
        self.assertNotIn(b'\x1b', result.stdout)
        self.assertIn(b'line\\nname', result.stdout)

    def test_symlink_gitlink_and_type_transition_are_identified(self):
        os.symlink('a.txt', self.repo / 'link.txt')
        self.git('update-index', '--add', '--cacheinfo', '160000,' + self.git('rev-parse', 'before').strip().decode() + ',module')
        self.git('add', 'link.txt')
        self.git('commit', '-qm', 'Track special modes')
        self.git('tag', '-f', 'before')
        (self.repo / 'a.txt').unlink()
        os.symlink('stable.md', self.repo / 'a.txt')
        self.git('add', 'a.txt')
        self.git('commit', '-qm', 'Replace file with a symlink')
        self.git('tag', '-f', 'after')
        code, report = self.cli()
        self.assertEqual(code, 0)
        self.assertTrue(report['complete'])
        modes = {x['path']: (x['before_mode'], x['after_mode']) for x in report['omissions']}
        self.assertEqual(modes, {'a.txt': ('100644', '120000'), 'link.txt': ('120000', '120000'),
                                 'module': ('160000', '160000')})

    def test_limits_are_incomplete_and_preserve_input(self):
        snapshot = self.snapshot()
        for option in [('--max-paths', '5'), ('--max-bytes', '100'), ('--timeout', '0.000001')]:
            with self.subTest(option=option):
                code, report = self.cli(*option)
                self.assertEqual(code, 2)
                self.assertFalse(report['complete'])
                self.assertEqual(report['status'], 'incomplete')
                self.assertTrue(report['errors'])
                self.assertIsNone(report['summary'])
                self.assertEqual(snapshot, self.snapshot())
        self.assertEqual(self.cli('--max-paths', '6')[0], 1)

    def test_invalid_revision_and_non_repository(self):
        snapshot = self.snapshot()
        code, report = self.cli(before='not-a-revision')
        self.assertEqual(code, 3)
        self.assertEqual(report['status'], 'input-error')
        self.assertEqual(snapshot, self.snapshot())
        self.assertEqual(compare(self.root, 'before', 'after', ['eol'])[1], 3)

    def test_missing_blob_and_attribute_blob_fail_closed(self):
        for path in ['a.txt', '.gitattributes', 'protected/.gitattributes']:
            with self.subTest(path=path):
                oid = self.git('rev-parse', 'before:' + path).strip().decode()
                target = self.repo / '.git/objects' / oid[:2] / oid[2:]
                blob = target.read_bytes()
                target.unlink()
                snapshot = self.snapshot()
                code, report = self.cli()
                self.assertEqual(code, 2)
                self.assertFalse(report['complete'])
                self.assertIn(oid, report['errors'][0])
                self.assertEqual(snapshot, self.snapshot())
                target.write_bytes(blob)

    def test_missing_root_tree_and_commit_are_incomplete(self):
        for revision in ['before^{tree}', 'before']:
            with self.subTest(revision=revision):
                oid = self.git('rev-parse', revision).strip().decode()
                target = self.repo / '.git/objects' / oid[:2] / oid[2:]
                content = target.read_bytes()
                target.unlink()
                snapshot = self.snapshot()
                code, report = self.cli()
                self.assertEqual(code, 2)
                self.assertFalse(report['complete'])
                self.assertEqual(report['status'], 'incomplete')
                self.assertEqual(snapshot, self.snapshot())
                target.write_bytes(content)

    def test_blob_revision_is_input_error(self):
        oid = self.git('rev-parse', 'before:a.txt').strip().decode()
        code, report = self.cli(before=oid)
        self.assertEqual(code, 3)
        self.assertFalse(report['complete'])
        self.assertIn('commit or tree', report['errors'][0])

    def test_attribute_blob_bytes_count_toward_budget(self):
        (self.repo / '.gitattributes').write_text('#' + 'x' * 200000 + '\n*.txt text eol=crlf\n')
        self.commit()
        code, report = self.cli('--max-bytes', '10000')
        self.assertEqual(code, 2)
        self.assertIn('Byte limit', report['errors'][0])
        self.assertFalse(report['complete'])

    def test_missing_tree_fails_closed(self):
        oid = self.git('rev-parse', 'before:docs').strip().decode()
        (self.repo / '.git/objects' / oid[:2] / oid[2:]).unlink()
        code, report = self.cli()
        self.assertEqual(code, 2)
        self.assertFalse(report['complete'])

    def test_git_without_source_support_is_not_empty_success(self):
        from attr_drift import core
        original = core.Git.run

        def unsupported(git, repo, *args, **kwargs):
            if args[0] == 'check-attr':
                raise Failure("Git check-attr: unknown option 'source'")
            return original(git, repo, *args, **kwargs)

        with patch.object(core.Git, 'run', unsupported):
            report, code = compare(self.repo, 'before', 'after', ['eol'])
        self.assertEqual(code, 2)
        self.assertIn('unknown option', report['errors'][0])
        self.assertFalse(report['complete'])

    def test_invalid_options_have_machine_readable_input_errors(self):
        for args in [('--attrs', ''), ('--attrs', 'eol,eol'), ('--attrs', '--all'), ('--attrs', 'builtin_objectmode'),
                     ('--max-paths', '0'), ('--timeout', 'nan'), ('--max-bytes', '-1')]:
            with self.subTest(args=args):
                code, report = self.cli(*args)
                self.assertEqual(code, 3)
                self.assertFalse(report['complete'])
                self.assertEqual(report['status'], 'input-error')

    def test_bare_repository_and_tree_oids(self):
        bare = self.root / 'bare.git'
        subprocess.check_call(['git', 'clone', '--bare', '-q', str(self.repo), str(bare)], env=self.env)
        before = self.git('rev-parse', 'before^{tree}').strip().decode()
        after = self.git('rev-parse', 'after^{tree}').strip().decode()
        report, code = compare(bare, before, after, ['eol'])
        self.assertEqual(code, 1)
        self.assertEqual(report['before_oid'], before)
        self.assertEqual(report['summary']['affected_unchanged_blobs'], 2)

    def test_sha256_repository(self):
        sha = self.root / 'sha256'
        subprocess.check_call(['git', 'init', '-q', '--object-format=sha256', str(sha)], env=self.env)
        self.repo = sha
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        (sha / 'a.txt').write_text('content\n')
        (sha / '.gitattributes').write_text('*.txt eol=lf\n')
        self.commit()
        self.git('tag', 'before')
        (sha / '.gitattributes').write_text('*.txt eol=crlf\n')
        self.commit()
        code, report = self.cli()
        self.assertEqual(code, 1)
        self.assertEqual(len(report['after_oid']), 64)
        self.assertEqual(report['summary']['affected_paths'], 1)

    def test_pinned_oids_survive_moving_refs(self):
        from attr_drift import core
        original = core.Git.run
        old_after = self.git('rev-parse', 'after').strip().decode()

        def move_ref(git, repo, *args, **kwargs):
            result = original(git, repo, *args, **kwargs)
            if args[0] == 'init':
                self.git('update-ref', 'refs/tags/after', self.git('rev-parse', 'before').strip().decode())
            return result

        with patch.object(core.Git, 'run', move_ref):
            report, code = compare(self.repo, 'before', 'after', ['eol'])
        self.assertEqual(code, 1)
        self.assertEqual(report['after_oid'], old_after)
        self.assertEqual(report['summary']['affected_paths'], 2)

    def test_git_warnings_do_not_hide_ignored_rules(self):
        (self.repo / '.gitattributes').write_text('*.txt invalid/name\n')
        self.commit()
        code, report = self.cli()
        self.assertEqual(code, 2)
        self.assertFalse(report['complete'])
        self.assertIn('invalid', report['errors'][0])

    def test_batches_over_256_paths(self):
        self.git('reset', '--hard', 'before')
        for index in range(260):
            (self.repo / ('batch-%03d.txt' % index)).write_text('stable\n')
        self.commit()
        self.git('tag', '-f', 'before')
        (self.repo / '.gitattributes').write_text('*.txt text eol=crlf\n')
        self.commit()
        code, report = self.cli()
        self.assertEqual(code, 1)
        self.assertEqual(report['summary']['compared_paths'], 266)
        self.assertEqual(report['summary']['affected_unchanged_blobs'], 262)
        self.assertIn('batch-259.txt', [d['path'] for d in report['differences']])

    def test_repository_path_with_spaces_and_newline(self):
        destination = self.root / 'repo with café\nand newline'
        self.repo.rename(destination)
        self.repo = destination
        code, report = self.cli()
        self.assertEqual(code, 1)
        self.assertEqual(report['summary']['affected_paths'], 2)

    def test_linked_worktree_reads_common_object_store(self):
        linked = self.root / 'linked'
        self.git('worktree', 'add', '--detach', str(linked), 'before')
        self.repo = linked
        code, report = self.cli()
        self.assertEqual(code, 1)
        self.assertEqual(report['summary']['affected_paths'], 2)

    def test_no_hooks_or_drivers_execute(self):
        marker = self.root / 'executed'
        command = 'touch ' + str(marker)
        for setting in ['core.fsmonitor', 'filter.probe.process', 'filter.probe.clean',
                        'filter.probe.smudge', 'diff.probe.command', 'diff.probe.textconv', 'merge.probe.driver']:
            self.git('config', setting, command)
        hooks = self.repo / '.git/hooks'
        hooks.mkdir()
        for hook in ['post-checkout', 'post-index-change', 'pre-commit']:
            target = hooks / hook
            target.write_text('#!/bin/sh\n' + command + '\n')
            target.chmod(0o755)
        (self.repo / '.gitattributes').write_text('*.txt filter=probe diff=probe merge=probe eol=crlf\n')
        self.git('hash-object', '-w', '--no-filters', '.gitattributes')
        snapshot = self.snapshot()
        code, report = self.cli()
        self.assertEqual(code, 1)
        self.assertFalse(marker.exists())
        self.assertEqual(snapshot, self.snapshot())

    def test_missing_promisor_object_does_not_contact_remote(self):
        requests = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(self.path)
                self.send_response(404)
                self.end_headers()

            def log_message(self, *args):
                pass

        server = HTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url = 'http://127.0.0.1:' + str(server.server_port)
        from urllib.request import urlopen
        from urllib.error import HTTPError
        with self.assertRaises(HTTPError):
            urlopen(url + '/control', timeout=2)
        self.assertEqual(requests, ['/control'])
        requests.clear()
        self.git('config', 'remote.origin.url', url + '/objects')
        self.git('config', 'remote.origin.promisor', 'true')
        self.git('config', 'remote.origin.partialclonefilter', 'blob:none')
        oid = self.git('rev-parse', 'before:a.txt').strip().decode()
        (self.repo / '.git/objects' / oid[:2] / oid[2:]).unlink()
        snapshot = self.snapshot()
        code, report = self.cli()
        self.assertEqual(code, 2)
        self.assertFalse(report['complete'])
        self.assertEqual(requests, [])
        self.assertEqual(snapshot, self.snapshot())

    def test_annotated_tag_peels_to_pinned_commit(self):
        self.git('tag', '-am', 'Baseline', 'annotated', 'before')
        code, report = self.cli(before='annotated')
        self.assertEqual(code, 1)
        self.assertEqual(report['before_oid'], self.git('rev-parse', 'before').strip().decode())


class Protocol(unittest.TestCase):
    def test_attributes_match_by_key_not_position(self):
        class FakeGit:
            def run(self, *args, **kwargs):
                return b'b\0eol\0crlf\0a\0eol\0lf\0'

            def guard(self):
                pass

        self.assertEqual(attributes(FakeGit(), '.', 'oid', [b'a', b'b'], ['eol']),
                         {(b'a', 'eol'): 'lf', (b'b', 'eol'): 'crlf'})

    def test_missing_duplicate_and_malformed_pairs_rejected(self):
        for raw in [b'a\0eol\0lf\0', b'a\0eol\0lf\0a\0eol\0crlf\0', b'a\0eol\0lf', b'c\0eol\0lf\0']:
            class FakeGit:
                def run(self, *args, **kwargs):
                    return raw

                def guard(self):
                    pass

            with self.subTest(raw=raw), self.assertRaises(Failure):
                attributes(FakeGit(), '.', 'oid', [b'a', b'b'], ['eol'])


if __name__ == '__main__':
    unittest.main()
