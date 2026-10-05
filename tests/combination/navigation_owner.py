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
    endpoint, audit_path = map(Path, sys.argv[1:3])
    hold_b = sys.argv[3:] == ['--hold-b']
    wait_proposal = sys.argv[3:] == ['--wait-proposal']
    revision = sys.argv[3:] in (['--revision'], ['--revision-race'], ['--revision-missing-close'])
    revision_mode = sys.argv[3] if revision else None
    failure = sys.argv[3:] in (['--failure'], ['--failure-normal'], ['--failure-missing-close'], ['--failure-b-failed'])
    failure_mode = sys.argv[3] if failure else None
    if sys.argv[3:] and not (hold_b or wait_proposal or revision or failure):
        raise ValueError('unsupported fixture mode')
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
    pose, stops, events = [0., 0.], [], []
    visit_started = cancel_started = None
    stage = 'A'
    scope_id = uuid.uuid4().hex

    def observation():
        return dict(valid=True, epoch=0, map_id='turtlebot3-world-v1', frame='map',
                    pose=list(pose), sample_sim_seconds=1.+time.monotonic() if revision or failure else 1.,
                    sensor_health=dict(localization=True, clock_age=0.,
                                       streams=[[1., 0., 0.], [1., 0., 0.]]),
                    contacts=['synthetic truth must not reach decisions'])

    requests = NavigationRequests(execution, sites=SITES,
        profile='scoped-two-context-nav2-failure-recovery-v1' if failure else
                'scoped-two-context-nav2-revision-v1' if revision else 'scoped-two-context-nav2-shim-v1', map_id='turtlebot3-world-v1',
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
        # Only the real 30-second proposal expiry case needs a longer fixture
        # lifetime. Application budgets and the normal fixture stay unchanged.
        deadline = time.monotonic()+(45 if wait_proposal else 15)
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
                if hold_b and record['site'] == 'B':
                    # This mode leaves real Core/native acceptance pending so
                    # the external test can signal the actual application CLI.
                    ready = audit_path.with_suffix('.running.json')
                    temporary = ready.with_suffix('.tmp')
                    temporary.write_text(json.dumps(execution.snapshot(record)))
                    temporary.replace(ready)
                    continue
                if revision and record['site'] == 'A':
                    visit_started = time.monotonic()
                    events.append('A_native_accepted')
                    continue
                if failure and ((record['site'] == 'A' and failure_mode != '--failure-normal')
                        or (record['site'] == 'B' and failure_mode == '--failure-b-failed')):
                    visit_started = time.monotonic()
                    accepted(execution.native(record, 'failed', goal_id))
                    execution.dispose_result(record, None, lambda: {})
                    events.append(record['site']+'_failed')
                    continue
                accepted(execution.native(record, 'succeeded', goal_id))
                execution.dispose_result(record, dict(goal_id=goal_id, stage=record['site']), lambda: {})
                pose[:] = SITES[record['site']][:2]
                if record['site'] == 'A':
                    execution.settle(record)
                    execution.release(record)
                    stage = 'B'
                    scope_id = uuid.uuid4().hex
            if (failure and failure_mode != '--failure-normal' and record is not None
                    and record.get('goal_id') and record['site'] == 'A'
                    and failure_mode != '--failure-missing-close'
                    and time.monotonic()-visit_started >= .2):
                # Controlled native closure evidence: real Core no-output then
                # settlement/release. This fixture never asserts ROS stop facts.
                execution.settle(record)
                execution.release(record)
                events.append('A_released')
                stage, scope_id = 'B', uuid.uuid4().hex
            if revision and record is not None and record.get('goal_id') and record['site'] == 'A':
                elapsed = time.monotonic()-visit_started
                if record['request_id'] in stops:
                    if cancel_started is None:
                        cancel_started = time.monotonic()
                        events.append('A_cancel')
                    if revision_mode != '--revision-missing-close' and time.monotonic()-cancel_started >= .2:
                        outcome = 'succeeded' if revision_mode == '--revision-race' else 'cancelled'
                        accepted(execution.native(record, outcome, record['goal_id']))
                        candidate = None if outcome == 'cancelled' else dict(goal_id=record['goal_id'], stage='A')
                        execution.dispose_result(record, candidate, lambda: {})
                        execution.settle(record)
                        execution.release(record)
                        events.append('A_released')
                        stage, scope_id = 'B', uuid.uuid4().hex
                elif elapsed >= 2:
                    accepted(execution.native(record, 'succeeded', record['goal_id']))
                    execution.dispose_result(record, dict(goal_id=record['goal_id'], stage='A'), lambda: {})
                    pose[:] = SITES['A'][:2]
                    execution.settle(record)
                    execution.release(record)
                    events.append('A_released')
                    stage, scope_id = 'B', uuid.uuid4().hex
                else:
                    pose[:] = [-.8+.3*elapsed, -.5]
            for message in channel.pump():
                try:
                    result = requests.command(message)
                    if (revision or failure) and message['command'] == 'submit' and message.get('site') == 'B':
                        events.append('B_submit')
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
                                             stops=stops, events=events), indent=2)+'\n')
        if channel is not None:
            channel.close()
        listener.close()
        endpoint.unlink(missing_ok=True)
        gate.close()


if __name__ == '__main__':
    main()
