import os
from pathlib import Path
import subprocess
import sys


def make_demo(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=False)
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)

    def git(*args):
        return subprocess.check_output(
            ['git', '-c', 'core.autocrlf=false', '-C', str(path), *args],
            env=env, stderr=subprocess.PIPE,
        ).decode().strip()

    git('init', '-q', '--template=')
    git('config', 'user.name', 'Fixture')
    git('config', 'user.email', 'fixture@example.invalid')
    files = {
        '.gitattributes': '*.txt text eol=lf\n',
        'protected/.gitattributes': '*.txt text eol=lf\n',
        'a.txt': 'alpha\n',
        'docs/b.txt': 'beta\n',
        'protected/c.txt': 'gamma\n',
        'stable.md': 'stable\n',
    }
    for name, content in files.items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    git('add', '.')
    git('commit', '-qm', 'Keep text files on LF')
    git('tag', 'before')
    (path / '.gitattributes').write_text('*.txt text eol=crlf\n')
    git('add', '.gitattributes')
    git('commit', '-qm', 'Change the root line ending policy')
    git('tag', 'after')
    return path


if __name__ == '__main__':
    make_demo(sys.argv[1])
