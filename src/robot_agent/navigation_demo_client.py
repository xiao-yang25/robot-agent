"""In-container tutorial selector for the installed public navigation CLI."""
import os
from pathlib import Path
import sys


def main(*, provider="controlled", model="controlled-tutorial-no-model"):
    import robot_agent
    import robot_harness
    for module, prefix in ((robot_agent, '/client-prefix'), (robot_harness, '/installed')):
        if not Path(module.__file__).resolve().is_relative_to(Path(prefix)):
            raise ValueError('tutorial did not import its declared installed packages')
    executable = {'controlled': 'robot-agent-navigation-controlled',
                  'host-codex': 'robot-agent-navigation-host-proposal'}[provider]
    os.execv(sys.executable, [sys.executable, '-m', 'robot_agent.navigation_cli',
        '--endpoint', sys.argv[1], '--output', '/output/agent', '--model', model,
        '--executable', '/client-prefix/bin/' + executable])


if __name__ == '__main__':
    main()
