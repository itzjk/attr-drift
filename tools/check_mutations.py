import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'attr_drift/core.py').read_text()
mutations = {
    'diff-only paths': (
        '                    common.append(path)',
        "                    if old['oid'] != new['oid']:\n                        common.append(path)",
    ),
    'current attributes instead of source tree': (
        "'check-attr', '--source=' + tree, '--stdin', '-z', *attrs,",
        "'check-attr', '--stdin', '-z', *attrs,",
    ),
    'lost nested exception': (
        "            unchanged = pairs = 0",
        "            new_values[b'protected/c.txt', 'eol'] = new_values[b'a.txt', 'eol']\n            unchanged = pairs = 0",
    ),
}
for name, (old, new) in mutations.items():
    if source.count(old) != 1:
        raise SystemExit('Mutation anchor changed: ' + name)
    with tempfile.TemporaryDirectory(prefix='attr-drift-mutation-') as directory:
        root = Path(directory)
        for folder in ('attr_drift', 'tests', 'tools'):
            shutil.copytree(ROOT / folder, root / folder, ignore=shutil.ignore_patterns('__pycache__'))
        (root / 'attr_drift/core.py').write_text(source.replace(old, new))
        env = dict(os.environ, PYTHONPATH=str(root / 'tests'))
        result = subprocess.run([sys.executable, '-m', 'unittest',
                                 'test_integration.Integration.test_main_case_exact_paths_values_and_native_oracle'],
                                cwd=root, env=env, capture_output=True, timeout=60)
        if result.returncode == 0 or b'AssertionError' not in result.stderr:
            sys.stderr.buffer.write(result.stderr)
            raise SystemExit('Mutation survived or failed for the wrong reason: ' + name)
        print('Detected: ' + name, flush=True)
