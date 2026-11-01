import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from attr_drift.core import Git, Failure


class Runner(unittest.TestCase):
    def run_fake(self, body, *, timeout=2, budget=4096):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / 'fake-git'
            executable.write_text('#!' + sys.executable + '\n' + body + '\n')
            executable.chmod(0o755)
            git = Git(root, budget, timeout)
            git.binary = str(executable)
            started = time.monotonic()
            with self.assertRaises(Failure) as caught:
                git.run(root, 'check-attr')
            self.assertLess(time.monotonic() - started, 4)
            return str(caught.exception)

    def test_timeout_terminates_real_process(self):
        message = self.run_fake('import time\ntime.sleep(10)', timeout=0.1)
        self.assertIn('Time limit', message)

    def test_output_flood_hits_byte_budget(self):
        message = self.run_fake('import os\nwhile True: os.write(1, b"x" * 65536)')
        self.assertIn('Byte limit', message)

    def test_stderr_flood_hits_same_byte_budget(self):
        message = self.run_fake('import os\nwhile True: os.write(2, b"x" * 65536)')
        self.assertIn('Byte limit', message)

    def test_real_unsupported_source_diagnostic(self):
        message = self.run_fake('import sys\nsys.stderr.write("unknown option source\\n")\nsys.exit(129)')
        self.assertIn('unknown option source', message)

    def test_missing_git_is_input_error(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'PATH': ''}):
            with self.assertRaises(Failure) as caught:
                Git(Path(directory), 4096, 2)
            self.assertEqual(caught.exception.code, 3)
