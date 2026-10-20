#!/usr/bin/env python3
"""Select the fixed installed inspection application and supported Harness scene."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys

AGENT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--harness-source', type=Path, required=True)
    parser.add_argument('--python-prefix', type=Path, required=True, help='matching Linux Harness installation')
    parser.add_argument('--agent-prefix', type=Path, required=True, help='matching Linux Agent pip --target installation')
    parser.add_argument('--image', required=True, help='qualified visual Humble image')
    parser.add_argument('--platform', choices=('linux/amd64', 'linux/arm64'), default='linux/amd64',
                        help='Linux image and installation architecture; default linux/amd64')
    parser.add_argument('--case', choices=('normal', 'recheck'), required=True)
    parser.add_argument('--output', type=Path, required=True, help='new result directory')
    parser.add_argument('--record-evaluation', action='store_true', help='passive pose collection, evaluated separately')
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    if output.exists():
        parser.error('output must be new')
    harness = args.harness_source.expanduser().resolve(strict=True)
    prefix = args.agent_prefix.expanduser().resolve(strict=True)
    python_prefix = args.python_prefix.expanduser().resolve(strict=True)
    refs = re.findall(r'^    version: ([0-9a-f]{40})$', (AGENT/'workspace.repos').read_text(), re.M)
    actual = subprocess.check_output(['git', '-C', str(harness), 'rev-parse', 'HEAD'], text=True).strip()
    if len(refs) != 1 or actual != refs[0]:
        parser.error('Harness checkout must match workspace.repos; no dependency override')
    status = subprocess.check_output(['git', '-C', str(harness), 'status', '--porcelain',
                                      '--untracked-files=normal'], text=True)
    if status.strip():
        parser.error('Harness tracked or untracked changes refused; use a clean checkout')
    client = prefix/'robot_agent/inspection_demo_client.py'
    if not all(path.is_file() for path in (client, prefix/'robot_agent/inspection_cli.py',
            prefix/'bin/robot-agent-inspection',
            python_prefix/'lib/robot-harness/python/robot_harness_nav2/_inspection.py')):
        parser.error('prepare matching new Linux Harness and Agent installations')
    command = [sys.executable, str(harness/'integrations/ros2/simulation/simulate.py'),
        'session', '--image', args.image, '--platform', args.platform, '--python-prefix', str(python_prefix),
        '--client-script', str(client), '--client-prefix', str(prefix),
        '--caller-wait-seconds', '45', '--inspection-case', args.case, '--output', str(output)]
    if args.record_evaluation:
        command.append('--record-evaluation')
    # Keep the existing launcher's signals, exit status and exact container owner.
    os.execv(sys.executable, command)


if __name__ == '__main__':
    main()
