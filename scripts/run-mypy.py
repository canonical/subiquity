#!/usr/bin/env python3

import argparse
import contextlib
import os
import subprocess
import tempfile
from typing import TextIO


def run_mypy(cwd: str | None, stdout: TextIO | None) -> None:
    ''' Execute mypy and if requested, redirects the output to a file. '''
    mypy_cmd = [
        'python3', '-m', 'mypy',
        '--ignore-missing-imports', '--check-untyped-defs',
        'subiquity', 'subiquitycore', 'console_conf',
        'scripts/replay-curtin-log.py',
    ]

    subprocess.run(mypy_cmd, check=False, text=True, cwd=cwd, stdout=stdout)


@contextlib.contextmanager
def worktree(rev: str) -> str:
    ''' When entered, deploy a git-worktree at the specified revision. Upon
    exiting, remove the worktree. '''
    try:
        with tempfile.TemporaryDirectory(suffix='.subiquity-worktree') as wt_dir:
            subprocess.run([
                'git', 'worktree', 'add', wt_dir,
                '--detach', rev,
            ], check=True)
            subprocess.run([
                'git', 'clone', 'probert', f'{wt_dir}/probert',
            ], check=True)
            subprocess.run([
                'scripts/update-part.py', 'probert',
            ], check=True, cwd=wt_dir)
            subprocess.run([
                'git', 'clone', 'curtin', f'{wt_dir}/curtin',
            ], check=True)
            subprocess.run([
                'scripts/update-part.py', 'curtin',
            ], check=True, cwd=wt_dir)
            yield wt_dir
    finally:
        subprocess.run(['git', 'worktree', 'remove', '--force', wt_dir])


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument('--diff-against', metavar='git-revision')
    parser.add_argument('--checkout-head', action='store_true')

    args = parser.parse_args()

    if args.checkout_head:
        cm_wd_head = worktree('HEAD')
    else:
        cm_wd_head = contextlib.nullcontext(enter_result=os.getcwd())

    if args.diff_against is not None:
        cm_wd_base = worktree(args.diff_against)
        cm_stdout_head = tempfile.NamedTemporaryFile(suffix='.out')
        cm_stdout_base = tempfile.NamedTemporaryFile(suffix='.out')
    else:
        cm_wd_base = contextlib.nullcontext()
        cm_stdout_head = contextlib.nullcontext()
        cm_stdout_base = contextlib.nullcontext()

    # Setup the output file(s) and worktree(s).
    with (
      cm_wd_head as cwd_head,
      cm_wd_base as cwd_base,
      cm_stdout_head as stdout_head,
      cm_stdout_base as stdout_base):
        # Execute mypy on the head revision
        run_mypy(stdout=stdout_head, cwd=cwd_head)

        if args.diff_against is None:
            return

        run_mypy(stdout=stdout_base, cwd=cwd_base)

        subprocess.run([
            'diff', '--color=always', '--unified=0',
            '--', stdout_base.name, stdout_head.name,
        ])


if __name__ == '__main__':
    main()
