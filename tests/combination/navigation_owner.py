"""CI-only trusted owner: real Core, synthetic measurements/native facts, no ROS.

Private coordinator/framing imports are confined to this fixture, never the
business application. One subprocess is the sole Core writer. It progresses
without client status requests; A settles, final B deliberately remains pending.
"""
import json
import os
from pathlib import Path
import socket
import sys
import time
import uuid

from robot_harness import _core
from robot_harness._execution import ExecutionCoordinator, accepted
from robot_harness._transport import Channel
from robot_harness.navigation import NavigationRequests

SITES = {'A': [0.7, -0.5, 0.0], 'B': [-1.5, -0.5, 0.0]}


def main():
    endpoint, audit_path = map(Path, sys.argv[1:])
    prefix = Path(os.environ['COMBINATION_HARNESS_PREFIX']).resolve()
    for module in (_core, sys.modules[ExecutionCoordinator.__module__],
                   sys.modules[NavigationRequests.__module__]):
        if not Path(module.__file__).resolve().is_relative_to(prefix):
            raise RuntimeError('owner fixture consumed an uninstalled Harness')
    clock = time.monotonic_ns
    stamp = clock()
    gate = _core.Gate('scoped-nav2', 'exclusive-waffle-drive', 'navigation',
                      'ci-synthetic-owner', 1, stamp,
                      settlement_scope='native-outlet-quiet-and-next-context')
    listener, channel = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM), None
    execution = ExecutionCoordinator(gate, clock)
    pose, stops = [0., 0.], []
    stage = 'A'
    scope_id = uuid.uuid4().hex

    def observation():
        return dict(valid=True, epoch=0, map_id='turtlebot3-world-v1', frame='map',
                    pose=list(pose), sample_sim_seconds=1.,
                    sensor_health=dict(localization=True, clock_age=0.,
                                       streams=[[1., 0., 0.], [1., 0., 0.]]),
                    contacts=['synthetic truth must not reach decisions'])

    requests = NavigationRequests(execution, sites=SITES,
        profile='scoped-two-context-nav2-shim-v1', map_id='turtlebot3-world-v1',
        observation=observation, ready=lambda: True,
        context=lambda: dict(stage=stage, scope_id=scope_id, generation=1),
        request_stop=lambda record: stops.append(record['request_id']))
    try:
        for kind in ('idle', 'worker', 'sink'):
            accepted(gate.startup(kind, True, clock()))
        accepted(gate.capabilities(True, clock(), clock()+60_000_000_000))
        listener.bind(str(endpoint))
        listener.listen(1)
        listener.settimeout(5)
        channel = Channel(listener.accept()[0])
        deadline = time.monotonic()+15
        closing = False
        while time.monotonic() < deadline:
            execution.tick()
            record = execution.active
            if record is not None and record.get('goal_id') is None:
                if not execution.dispatch(record):
                    raise RuntimeError('fixture native dispatch refused')
                goal_id = uuid.uuid4().hex
                record['goal_id'] = goal_id
                accepted(execution.native(record, 'accepted', goal_id))
                accepted(execution.native(record, 'succeeded', goal_id))
                execution.dispose_result(record, dict(goal_id=goal_id, stage=record['site']), lambda: {})
                pose[:] = SITES[record['site']][:2]
                if record['site'] == 'A':
                    execution.settle(record)
                    execution.release(record)
                    stage = 'B'
                    scope_id = uuid.uuid4().hex
            for message in channel.pump():
                try:
                    result = requests.command(message)
                    reply = dict(rpc=message['rpc'], result=result)
                except (ValueError, KeyError) as error:
                    reply = dict(rpc=message['rpc'], error=str(error))
                channel.queue(reply)
                closing = closing or message['command'] == 'close'
            if closing and not channel.outgoing:
                return
            time.sleep(.001)
        raise TimeoutError('CI owner lifetime elapsed')
    except EOFError:
        # The cooperating client may leave after receiving its close reply.
        pass
    finally:
        requests.close()
        audit_path.write_text(json.dumps(dict(records=[requests.status(key) for key in execution.records],
                                             stops=stops), indent=2)+'\n')
        if channel is not None:
            channel.close()
        listener.close()
        endpoint.unlink(missing_ok=True)
        gate.close()


if __name__ == '__main__':
    main()
