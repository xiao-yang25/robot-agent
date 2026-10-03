#!/usr/bin/env python3
"""Run the controlled installed business application using Harness's public launcher."""
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
    parser.add_argument('--python-prefix', type=Path, required=True, help='new Linux Harness install')
    parser.add_argument('--agent-prefix', type=Path, required=True, help='Linux pip --target installation')
    parser.add_argument('--image', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    harness = args.harness_source.expanduser().resolve(strict=True)
    prefix = args.agent_prefix.expanduser().resolve(strict=True)
    refs = re.findall(r'^    version: ([0-9a-f]{40})$', (AGENT / 'workspace.repos').read_text(), re.M)
    actual = subprocess.check_output(['git', '-C', str(harness), 'rev-parse', 'HEAD'], text=True).strip()
    if len(refs) != 1 or actual != refs[0]:
        parser.error('Harness checkout must match workspace.repos; no dependency override')
    subprocess.run(['git', '-C', str(harness), 'diff', '--quiet', 'HEAD'], check=True)
    client = prefix / 'robot_agent/navigation_demo_client.py'
    if not client.is_file() or not (prefix / 'bin/robot-agent-navigation-controlled').is_file():
        parser.error('Agent prefix lacks the installed tutorial; prepare a new Linux installation')
    # Replace this selector; Harness retains its existing signal and exact-container cleanup.
    os.execv(sys.executable, [sys.executable, str(harness / 'integrations/ros2/simulation/simulate.py'),
        'session', '--image', args.image, '--python-prefix', str(args.python_prefix.expanduser().resolve(strict=True)),
        '--client-script', str(client), '--client-prefix', str(prefix), '--caller-wait-seconds', '45',
        '--output', str(args.output.expanduser().resolve())])


if __name__ == '__main__':
    main()
