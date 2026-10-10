#!/usr/bin/env python3
"""Run the installed navigation business application using Harness's public launcher."""
import argparse
import math
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
    parser.add_argument('--record-evaluation', action='store_true',
                        help='passive truth collection for fixed normal A->B; evaluate offline separately')
    parser.add_argument('--provider', choices=('controlled', 'host-codex'), default='controlled')
    parser.add_argument('--model', help='required explicit host model for host-codex')
    parser.add_argument('--executable', default='codex', help='host-only model CLI')
    parser.add_argument('--host-output', type=Path, help='new private host directory, never mounted in the scene')
    parser.add_argument('--task', choices=('fixed', 'checkpoint', 'revision', 'recovery'), default='fixed')
    parser.add_argument('--assembly', choices=('legacy', 'experimental-coordination'), default='legacy',
                        help='explicit experimental coordinator; public task defaults remain legacy')
    parser.add_argument('--coordination-scenario', choices=('normal', 'final-decision-stop'))
    parser.add_argument('--terminal-query-seconds', type=float,
                        help='required finite (0, 10] Owner query budget for experimental coordination')
    parser.add_argument('--scene', choices=('normal','occupied-a'), default='normal',
                        help='occupied-a is a static map test and requires --task recovery')
    parser.add_argument('--instruction', choices=('continue_b', 'finish_at_a', 'none', 'stop', 'redirect_b'))
    parser.add_argument('--instruction-delay', type=float, default=None, help='business tutorial delay in [0, 9] seconds')
    args = parser.parse_args()
    coordinated = args.assembly == 'experimental-coordination'
    if coordinated:
        if (args.task != 'fixed' or args.provider != 'controlled' or args.scene != 'normal'
                or args.instruction is not None or args.instruction_delay is not None
                or args.model is not None or args.host_output is not None or args.executable != 'codex'):
            parser.error('experimental coordination requires fixed/controlled/normal without model or instruction options')
        if (args.coordination_scenario is None or args.terminal_query_seconds is None
                or not math.isfinite(args.terminal_query_seconds) or not 0 < args.terminal_query_seconds <= 10):
            parser.error('experimental coordination requires an explicit scenario and terminal query seconds in (0, 10]')
    elif args.coordination_scenario is not None or args.terminal_query_seconds is not None:
        parser.error('coordination options require --assembly experimental-coordination')
    if args.record_evaluation and (args.task != 'fixed' or args.scene != 'normal'):
        parser.error('--record-evaluation requires --task fixed and --scene normal')
    if args.scene != 'normal' and args.task != 'recovery':
        parser.error('occupied-a requires --task recovery')
    checkpoint = revision = recovery = None
    if args.task == 'recovery':
        recovery = dict(expected_map_id='turtlebot3-world-v1' if args.scene=='normal'
                        else 'turtlebot3-occupied-a-probe-v1')
    if args.task == 'checkpoint':
        from robot_agent.navigation_checkpoint_demo import TutorialInstruction
        if args.instruction is None:
            parser.error('checkpoint requires an explicit --instruction')
        delay = 4 if args.instruction_delay is None else args.instruction_delay
        try:
            TutorialInstruction(args.instruction, delay, args.output)
        except ValueError as error:
            parser.error(str(error))
        checkpoint = dict(instruction=args.instruction, delay=delay)
    elif args.task == 'revision':
        from robot_agent.navigation_revision_demo import TutorialPoll
        if args.instruction is None:
            parser.error('revision requires explicit --instruction none/stop/redirect_b')
        delay = 0 if args.instruction_delay is None else args.instruction_delay
        try:
            TutorialPoll(args.instruction, delay, args.output)
        except ValueError as error:
            parser.error(str(error))
        revision = dict(instruction=args.instruction, delay=delay)
    elif args.instruction is not None or args.instruction_delay is not None:
        parser.error('instruction options require --task checkpoint or revision')
    harness = args.harness_source.expanduser().resolve(strict=True)
    prefix = args.agent_prefix.expanduser().resolve(strict=True)
    python_prefix = args.python_prefix.expanduser().resolve(strict=True)
    refs = re.findall(r'^    version: ([0-9a-f]{40})$', (AGENT / 'workspace.repos').read_text(), re.M)
    actual = subprocess.check_output(['git', '-C', str(harness), 'rev-parse', 'HEAD'], text=True).strip()
    if len(refs) != 1 or actual != refs[0]:
        parser.error('Harness checkout must match workspace.repos; no dependency override')
    subprocess.run(['git', '-C', str(harness), 'diff', '--quiet', 'HEAD'], check=True)
    client = prefix / 'robot_agent/navigation_demo_client.py'
    if not client.is_file() or not (prefix / 'bin/robot-agent-navigation-controlled').is_file():
        parser.error('Agent prefix lacks the installed tutorial; prepare a new Linux installation')
    if checkpoint is not None and not (prefix/'robot_agent/navigation_checkpoint_demo.py').is_file():
        parser.error('prepare a new Agent installation including the checkpoint tutorial')
    if coordinated and not (prefix/'robot_agent/navigation_coordination_demo.py').is_file():
        parser.error('prepare a new Agent installation including the coordination tutorial')
    command = [sys.executable, str(harness / 'integrations/ros2/simulation/simulate.py'),
        'session', '--image', args.image, '--python-prefix', str(python_prefix),
        '--client-script', str(client), '--client-prefix', str(prefix), '--caller-wait-seconds', '45',
        '--output', str(args.output.expanduser().resolve())]
    if args.record_evaluation:
        command.append('--record-evaluation')
    if coordinated:
        command.extend(['--terminal-query-seconds', str(args.terminal_query_seconds)])
        from robot_agent._navigation_demo import run_controlled_client
        source = ('from robot_agent.navigation_coordination_demo import main\n'
                  f'raise SystemExit(main(scenario={args.coordination_scenario!r}))\n')
        return run_controlled_client(command, source)
    if revision is not None:
        if not (prefix/'robot_agent/navigation_revision_demo.py').is_file():
            parser.error('prepare a new Agent installation including the revision tutorial')
        from robot_agent.navigation_revision import PROFILE
        command.extend(['--profile', PROFILE])
    if recovery is not None:
        from robot_agent.navigation_recovery import PROFILE
        command.extend(['--profile', PROFILE, '--scene', args.scene])
    if args.provider == 'host-codex':
        if not args.model or not args.model.strip() or len(args.model) > 128 or args.host_output is None:
            parser.error('host-codex requires an explicit model and separate new --host-output')
        if not (prefix / 'bin/robot-agent-navigation-host-proposal').is_file():
            parser.error('prepare the matching relay installation')
        from robot_agent._navigation_demo import run_host
        return run_host(command, output=args.output.expanduser().resolve(),
            host_output=args.host_output.expanduser().resolve(), model=args.model, executable=args.executable,
            mounted_roots=(prefix, python_prefix, harness / 'integrations/ros2/simulation'), checkpoint=checkpoint, revision=revision, recovery=recovery)
    if args.model is not None or args.host_output is not None or args.executable != 'codex':
        parser.error('model/host-output/executable options require --provider host-codex')
    if recovery is not None:
        from robot_agent._navigation_demo import run_controlled_recovery
        return run_controlled_recovery(command, recovery['expected_map_id'])
    if checkpoint is not None or revision is not None:
        # Keep this exact trusted bind file alive until Harness finishes its cleanup.
        # Use the existing supervisor for signal forwarding and process-group reaping.
        from robot_agent._navigation_demo import run_controlled_checkpoint
        return run_controlled_checkpoint(command, checkpoint if checkpoint is not None else revision,
                                         revision=revision is not None)
    # Default selector remains replaced by Harness, preserving its signal path.
    os.execv(sys.executable, command)


if __name__ == '__main__':
    raise SystemExit(main())
