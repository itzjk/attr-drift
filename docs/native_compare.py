import subprocess
import sys

repo, before, after = sys.argv[1:]


def git(*args, data=None):
    return subprocess.check_output(['git', '-C', repo, *args], input=data)


def paths(rev):
    return set(git('ls-tree', '-rz', '--name-only', rev).split(b'\0')[:-1])


common = sorted(paths(before) & paths(after))
data = b''.join(p + b'\0' for p in common)
values = []
for rev in (before, after):
    fields = git('check-attr', '--source=' + rev, '--stdin', '-z', 'eol', data=data).split(b'\0')[:-1]
    values.append({(p, a): v for p, a, v in zip(fields[::3], fields[1::3], fields[2::3])})
for key, old in values[0].items():
    new = values[1][key]
    if old != new:
        print(repr(key[0]), old.decode(), '->', new.decode())
