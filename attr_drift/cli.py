import argparse
import json
import math
import re
import sys

from . import __version__
from .core import compare


class Parser(argparse.ArgumentParser):
    def error(self, message):
        if '--json' in sys.argv:
            print(json.dumps({'schema_version': 1, 'status': 'input-error', 'complete': False,
                              'errors': [message]}))
        else:
            self.print_usage(sys.stderr)
            print('attr-drift: ' + message, file=sys.stderr)
        raise SystemExit(3)


def positive_int(value):
    try:
        result = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError('must be a positive integer')
    if result <= 0:
        raise argparse.ArgumentTypeError('must be a positive integer')
    return result


def positive_float(value):
    try:
        result = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError('must be a positive number')
    if not math.isfinite(result) or result <= 0:
        raise argparse.ArgumentTypeError('must be a positive finite number')
    return result


def selected_attributes(value):
    attrs = value.split(',')
    if len(attrs) > 64 or len(attrs) != len(set(attrs)) or any(
        not re.fullmatch(r'[A-Za-z0-9_.][A-Za-z0-9_.-]{0,127}', attr) or attr.startswith('builtin_')
        for attr in attrs
    ):
        raise argparse.ArgumentTypeError('select 1-64 unique attribute names; builtin_* is outside versioned scope')
    return attrs


def display(value):
    return json.dumps(value, ensure_ascii=True)


def render(report):
    if not report['complete']:
        return '\n'.join(['attr-drift: ' + report['status'].upper(),
                          *('  ' + display(error) for error in report['errors']),
                          'No complete comparison is available.'])
    count = report['summary']
    lines = [f"attr-drift: {count['affected_paths']} affected paths ({count['affected_unchanged_blobs']} unchanged blobs)",
             f"{count['compared_paths']} compared | {count['stable_paths']} stable | {count['added_paths']} added | {count['removed_paths']} removed | {count['omitted_paths']} omitted",
             'Sources: versioned .gitattributes only',
             'Before: ' + report['before_oid'], 'After:  ' + report['after_oid']]
    for item in report['differences']:
        lines.append('\n' + display(item['path']) + (' [blob changed]' if item['blob_changed'] else ' [blob unchanged]'))
        for change in item['changes']:
            lines.append('  ' + change['attribute'] + ': ' + display(change['before']) + ' -> ' + display(change['after']))
    for item in report['inventory']:
        if item['status'] != 'common':
            entry = item['after'] or item['before']
            lines.append(item['status'] + ': ' + display(item['path']) + ' (mode ' + entry['mode'] + ')')
    for item in report['omissions']:
        lines.append('omitted: ' + display(item['path']) + ' (modes ' + str(item['before_mode']) + ' -> ' + str(item['after_mode']) + ')')
    return '\n'.join(lines)


def main(argv=None):
    parser = Parser(description='Find attribute changes on tracked files, including unchanged blobs.')
    parser.add_argument('before', help='local revision or tree before the policy change')
    parser.add_argument('after', help='local revision or tree after the policy change')
    parser.add_argument('--repo', default='.', help='local repository (default: .)')
    parser.add_argument('--attrs', required=True, type=selected_attributes, help='comma-separated attributes, e.g. text,eol')
    parser.add_argument('--json', action='store_true', help='emit JSON schema version 1')
    parser.add_argument('--max-paths', type=positive_int, default=100000, help='union path limit (default: 100000)')
    parser.add_argument('--max-bytes', type=positive_int, default=67108864, help='Git I/O and attribute blob byte budget (default: 67108864)')
    parser.add_argument('--timeout', type=positive_float, default=30, help='comparison deadline in seconds (default: 30)')
    parser.add_argument('--version', action='version', version='attr-drift ' + __version__)
    args = parser.parse_args(argv)
    report, code = compare(args.repo, args.before, args.after, args.attrs,
                           args.max_paths, args.max_bytes, args.timeout)
    try:
        print(json.dumps(report, ensure_ascii=True, indent=2) if args.json else render(report))
    except BrokenPipeError:
        return code
    return code
