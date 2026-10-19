"""In-container selector; the existing inspection command owns the task."""
import argparse
import os
from pathlib import Path
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('endpoint')
    args = parser.parse_args(argv)
    import robot_agent
    import robot_harness
    for module, prefix in ((robot_agent, '/client-prefix'), (robot_harness, '/installed')):
        if not Path(module.__file__).resolve().is_relative_to(Path(prefix)):
            raise ValueError('tutorial did not import its declared installed packages')
    # The CLI does not consume fixture selection/truth as task inputs.
    os.execv(sys.executable, [sys.executable, '-m', 'robot_agent.inspection_cli',
        '--endpoint', args.endpoint, '--output', '/output/agent',
        '--marker-reader', 'located-bright-panel'])


if __name__ == '__main__':
    main()
