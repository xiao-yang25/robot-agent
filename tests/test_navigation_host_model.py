"""Actual local processes and exchange boundaries; no authenticated models."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import uuid

from robot_agent._navigation_demo import finish, run_host
from robot_agent._navigation_relay import directory, proposal_request, read_json, write_json
from robot_agent.navigation import ACTIONS, GOAL, SITES
from robot_agent.navigation_checkpoint import CheckpointNavigationTask
from robot_agent.navigation_revision import RevisionNavigationTask


def inputs(phase='prepare', model='fixture'):
    reference = dict(session_id='session', observation_id='observation', epoch=0,
                     map_id='turtlebot3-world-v1', frame='map')
    return dict(task_id='task', phase=phase, goal=GOAL, registered_sites=SITES,
                allowed_actions=list(ACTIONS[phase]), observation_reference=reference,
                model_requested=model, measurement=dict(reference=reference, pose=[-2., -.5],
                sample_sim_seconds=1., sensor_health=dict(localization=True, clock_age=0.,
                                                        streams=[[1., 0., 0.], [1., 0., 0.]])))


class HostModelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.scene = self.root/'scene'
        self.scene.mkdir()
        self.host = self.root/'host'
        self.host.mkdir()
        self.executable = self.root/'proposal'
        self.executable.write_text(f'#!{sys.executable}\n'+'''import json,os,sys,time
from pathlib import Path
if '--version' in sys.argv: print('controlled-test-no-model');raise SystemExit(0)
record=json.loads(sys.stdin.read().splitlines()[-1])
out=Path(sys.argv[sys.argv.index('--output-last-message')+1])
(out.parent/'child.pid').write_text(str(os.getpid()))
if record['model_requested']=='slow-fixture':time.sleep(10)
answer={k:record[k] for k in ('task_id','phase','observation_reference')}
answer.update(action={'prepare':'visit_a','after_a':'visit_b','final':'observed_complete'}[record['phase']],reason='fixture')
out.write_text(json.dumps(answer))
print(json.dumps({'item':{'type':'agent_message'}}))
''')
        self.executable.chmod(0o755)

    def wait_file(self, path, process=None, seconds=5):
        until = time.monotonic()+seconds
        while not path.exists() and (process is None or process.poll() is None) and time.monotonic()<until:
            time.sleep(.01)
        self.assertTrue(path.exists(), f'missing {path}')

    def server(self, model='fixture', task='fixed'):
        log = (self.host/'server.log').open('w')
        self.addCleanup(log.close)
        process = subprocess.Popen([sys.executable, '-m', 'robot_agent.navigation_host_model',
            '--exchange', str(self.scene), '--output', str(self.host), '--model', model,
            '--executable', str(self.executable), '--task', task], stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        self.addCleanup(lambda: finish(process, 1))
        self.wait_file(self.host/'ready.json', process)
        return process

    def request(self, phase='prepare', model='fixture'):
        slot = self.scene/'model-requests'/phase
        slot.mkdir(parents=True)
        record = dict(nonce=uuid.uuid4().hex, remaining_seconds=3, inputs=inputs(phase, model))
        record['inputs']['physical_ground_truth'] = 'not a model input'
        record['inputs']['measurement']['contacts'] = ['not a model input']
        with directory(slot) as fd:
            write_json(fd, 'request.json', record)
        return slot, record

    def test_host_reconstructs_whitelist_and_rejects_wrong_budget_model_or_reference(self):
        record=dict(nonce='a'*32, remaining_seconds=1, inputs=inputs())
        record['inputs']['physical_ground_truth'] = 'ignored optional metadata'
        record['inputs']['measurement']['contacts'] = ['ignored']
        _, _, context, observation = proposal_request(record, 'prepare', 'fixture')
        self.assertNotIn('contacts', observation)
        self.assertNotIn('physical_ground_truth', context)
        for budget in (True, float('nan'), 0, 31):
            with self.subTest(budget=budget), self.assertRaises(ValueError):
                proposal_request({**record, 'remaining_seconds':budget}, 'prepare', 'fixture')
        with self.assertRaises(ValueError):
            proposal_request(record, 'prepare', 'different-model')
        record['inputs']['observation_reference'] = {**record['inputs']['observation_reference'], 'epoch':True}
        with self.assertRaises(ValueError):
            proposal_request(record, 'prepare', 'fixture')

    def test_exchange_refuses_symlink_fifo_and_oversized_regular_file(self):
        target=self.root/'outside.json'
        target.write_text('{}')
        (self.scene/'link').symlink_to(target)
        os.mkfifo(self.scene/'fifo')
        (self.scene/'large').write_bytes(b'x'*65537)
        with directory(self.scene) as fd:
            for name in ('link','fifo','large'):
                with self.subTest(name=name), self.assertRaises((OSError,ValueError)):
                    read_json(fd,name)
        with self.assertRaises(OSError), directory(self.scene/'link'):
            pass

    def test_checkpoint_host_requires_explicit_task_and_preserves_only_bound_instruction(self):
        value = inputs('after_a')
        value.update(goal=CheckpointNavigationTask.goal, allowed_actions=['finish_at_a','help'])
        command = {key: value['observation_reference'][key] for key in ('session_id','epoch','map_id','frame')}
        command.update(task_id='task', checkpoint_id='current-checkpoint', action='finish_at_a', optional_metadata='ignored')
        value['checkpoint_instruction'] = command
        record = dict(nonce='a'*32, remaining_seconds=4, inputs=value)
        _, _, context, observation = proposal_request(record,'after_a','fixture',task='checkpoint')
        self.assertEqual(context['checkpoint_instruction']['action'],'finish_at_a')
        self.assertNotIn('optional_metadata', context['checkpoint_instruction'])
        with self.assertRaises(ValueError): proposal_request(record,'after_a','fixture')
        for key, wrong in (('epoch',True),('session_id','foreign'),('task_id','other'),('frame','odom'),('action','visit_b')):
            with self.subTest(key=key):
                command[key], original = wrong, command[key]
                with self.assertRaises(ValueError): proposal_request(record,'after_a','fixture',task='checkpoint')
                command[key] = original
        value['allowed_actions'] = ['visit_b','help']
        with self.assertRaises(ValueError): proposal_request(record,'after_a','fixture',task='checkpoint')

    def test_checkpoint_host_process_keeps_model_instruction_and_stops_after_two_phases(self):
        source=self.executable.read_text().replace("out.write_text(json.dumps(answer))", "if 'checkpoint_instruction' in record: answer.update(action=record['allowed_actions'][0],checkpoint_id=record['checkpoint_instruction']['checkpoint_id'])\nout.write_text(json.dumps(answer))")
        self.executable.write_text(source)
        process=self.server(task='checkpoint')
        for phase in ('prepare','after_a'):
            slot=self.scene/'model-requests'/phase;slot.mkdir(parents=True)
            value=inputs(phase);value['goal']=CheckpointNavigationTask.goal
            if phase == 'after_a':
                value['allowed_actions']=['finish_at_a','help']
                command={key:value['observation_reference'][key] for key in ('session_id','epoch','map_id','frame')}
                command.update(task_id='task',checkpoint_id='current',action='finish_at_a')
                value['checkpoint_instruction']=command
            with directory(slot) as fd: write_json(fd,'request.json',dict(nonce='b'*32,remaining_seconds=3,inputs=value))
            self.wait_file(slot/'response.json',process)
            response=json.loads((slot/'response.json').read_text())
            self.assertNotIn('error', response)
        self.assertEqual(response['answer']['checkpoint_id'],'current')
        self.assertEqual(response['answer']['action'],'finish_at_a')
        process.terminate();self.assertEqual(process.wait(timeout=5),0)
        records=json.loads((self.host/'model-server.json').read_text())
        self.assertEqual([row['phase'] for row in records['requests']],['prepare','after_a'])
        self.assertTrue(records['stop_observed'])

    def test_revision_host_whitelists_bound_instruction_and_explicit_completion_target(self):
        value = inputs()
        value.update(phase='after_revision', goal=RevisionNavigationTask.goal, allowed_actions=['visit_b','help'])
        command = dict(task_id='task',revision_id='revision',request_id='task-prepare',operation_id=1,
                       goal_id='a'*32,session_id='session',epoch=0,map_id='turtlebot3-world-v1',frame='map',
                       action='redirect_b', optional_metadata='ignored')
        value['revision_instruction'] = command
        record = dict(nonce='a'*32, remaining_seconds=4, inputs=value)
        _,_,context,_ = proposal_request(record,'after_revision','fixture',task='revision')
        self.assertNotIn('optional_metadata', context['revision_instruction'])
        for key, wrong in (('epoch',True),('operation_id',True),('action','stop'),('goal_id','bad'),('session_id','other')):
            with self.subTest(key=key):
                old = command[key]; command[key] = wrong
                with self.assertRaises(ValueError): proposal_request(record,'after_revision','fixture',task='revision')
                command[key] = old
        value = inputs('final'); value.update(goal=RevisionNavigationTask.goal, completion_site='A')
        record['inputs'] = value
        self.assertEqual(proposal_request(record,'final','fixture',task='revision')[2]['completion_site'], 'A')
        value['completion_site'] = 'C'
        with self.assertRaises(ValueError): proposal_request(record,'final','fixture',task='revision')

    def test_revision_host_serves_direct_final_without_waiting_for_redirect_phase(self):
        process = self.server(task='revision')
        for phase in ('prepare','final'):
            slot = self.scene/'model-requests'/phase; slot.mkdir(parents=True)
            value = inputs(phase); value['goal'] = RevisionNavigationTask.goal
            if phase == 'final': value['completion_site'] = 'A'
            with directory(slot) as fd: write_json(fd,'request.json',dict(nonce='c'*32,remaining_seconds=3,inputs=value))
            self.wait_file(slot/'response.json',process)
            self.assertNotIn('error',json.loads((slot/'response.json').read_text()))
        process.terminate(); self.assertEqual(process.wait(timeout=5),0)
        records = json.loads((self.host/'model-server.json').read_text())['requests']
        self.assertEqual([r['phase'] for r in records],['prepare','final'])

    def test_three_host_decisions_have_private_inputs_and_reaped_actual_children(self):
        process=self.server()
        for phase, action in zip(ACTIONS, ('visit_a','visit_b','observed_complete')):
            slot, record=self.request(phase)
            self.wait_file(slot/'response.json', process)
            reply=json.loads((slot/'response.json').read_text())
            self.assertEqual(reply['nonce'],record['nonce'])
            self.assertEqual(reply['answer']['action'],action)
        process.terminate()
        self.assertEqual(process.wait(timeout=5),0)
        for decision in (self.host/'decisions').glob('decision-*'):
            data=json.loads((decision/'input.json').read_text())
            self.assertNotIn('contacts',data['measurement'])
            self.assertNotIn('physical_ground_truth',data)
            child=json.loads((decision/'process.json').read_text())
            self.assertTrue(child['reaped'])
            with self.assertRaises(ProcessLookupError):os.kill(child['pid'],0)

    def test_cancel_marker_reaps_running_host_proposal_without_publishing_reply(self):
        process=self.server('slow-fixture')
        slot,_=self.request(model='slow-fixture')
        self.wait_file(self.host/'decisions/decision-1/child.pid',process)
        with directory(slot) as fd:write_json(fd,'cancelled',{})
        self.wait_file(self.host/'decisions/decision-1/process.json',process)
        self.assertFalse((slot/'response.json').exists())
        child=json.loads((self.host/'decisions/decision-1/process.json').read_text())
        self.assertTrue(child['reaped'])
        with self.assertRaises(ProcessLookupError):os.kill(child['pid'],0)
        process.terminate()
        self.assertEqual(process.wait(timeout=5),0)

    def relay(self, *, model='fixture', budget=5):
        answer=self.root/'answer.json'
        code='from pathlib import Path;from robot_agent.navigation_host_proposal import main;'+f'main(exchange=Path({str(self.scene)!r}))'
        log=(self.root/'relay.log').open('w')
        self.addCleanup(log.close)
        process=subprocess.Popen([sys.executable,'-c',code,'--output-last-message',str(answer)],
            stdin=subprocess.PIPE,stdout=log,stderr=subprocess.STDOUT,text=True,
            env=dict(os.environ,ROBOT_AGENT_PROPOSAL_REMAINING_SECONDS=str(budget)),start_new_session=True)
        self.addCleanup(lambda:finish(process,1))
        process.stdin.write(json.dumps(inputs(model=model))+'\n');process.stdin.close()
        slot=self.scene/'model-requests/prepare'
        self.wait_file(slot/'request.json',process)
        return process,slot,answer

    def test_relay_rejects_wrong_nonce_and_notifies_host_withdrawal(self):
        process,slot,answer=self.relay()
        with directory(slot) as fd:write_json(fd,'response.json',dict(nonce='0'*32,answer={}))
        self.assertNotEqual(process.wait(timeout=5),0)
        self.assertFalse(answer.exists())
        self.assertTrue((slot/'cancelled').is_file())

    def test_relay_signal_publishes_cancellation_without_an_answer(self):
        process,slot,answer=self.relay()
        process.terminate()
        self.assertNotEqual(process.wait(timeout=5),0)
        self.assertFalse(answer.exists())
        self.assertTrue((slot/'cancelled').is_file())

    def test_original_relay_deadline_withdraws_slow_host_child_without_an_answer(self):
        host = self.server('slow-fixture')
        relay, slot, answer = self.relay(model='slow-fixture', budget=.5)
        self.wait_file(self.host/'decisions/decision-1/child.pid', host)
        self.assertNotEqual(relay.wait(timeout=5), 0)
        self.assertTrue((slot/'cancelled').is_file())
        self.assertFalse(answer.exists())
        self.wait_file(self.host/'decisions/decision-1/process.json', host)
        self.assertFalse((slot/'response.json').exists())
        child = json.loads((self.host/'decisions/decision-1/process.json').read_text())
        self.assertTrue(child['reaped'])
        with self.assertRaises(ProcessLookupError): os.kill(child['pid'], 0)

    def test_host_wrapper_forwards_signal_and_keeps_bind_through_launcher_cleanup(self):
        self.scene.rmdir();self.host.rmdir()
        launch=self.root/'launcher.py'
        cleanup=self.root/'launcher-cleanup.json'
        launch.write_text('import json,signal,sys,time\nfrom pathlib import Path\n'+
            'out=Path(sys.argv[sys.argv.index("--output")+1]);out.mkdir()\n'+
            'client=Path(sys.argv[sys.argv.index("--client-script")+1])\n'+
            'def stop(*_):\n'+f' Path({str(cleanup)!r}).write_text(json.dumps(dict(bind_exists=client.is_file())))\n'+
            ' raise SystemExit(0)\n'+
            'signal.signal(signal.SIGINT,stop);signal.signal(signal.SIGTERM,stop)\n'+
            '(out/"ready").touch()\nwhile True:time.sleep(.01)\n')
        command=[sys.executable,str(launch),'--client-script','placeholder','--output',str(self.scene)]
        code='from pathlib import Path;from robot_agent._navigation_demo import run_host;'+f'raise SystemExit(run_host({command!r},output=Path({str(self.scene)!r}),host_output=Path({str(self.host)!r}),model="fixture",executable={str(self.executable)!r}))'
        log=(self.root/'wrapper.log').open('w');self.addCleanup(log.close)
        process=subprocess.Popen([sys.executable,'-c',code],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        self.addCleanup(lambda:finish(process,1))
        self.wait_file(self.scene/'ready',process)
        process.send_signal(signal.SIGINT)
        self.assertEqual(process.wait(timeout=10),130)
        self.assertTrue(json.loads(cleanup.read_text())['bind_exists'])
        record=json.loads((self.host/'processes.json').read_text())
        for name in ('launcher','host_model'):
            self.assertTrue(record[name]['reaped'])
            self.assertFalse(record[name]['group_forced'])
            with self.assertRaises(ProcessLookupError):os.killpg(record[name]['pid'],0)

    def test_failed_model_preparation_never_starts_scene_and_reaps_host_group(self):
        self.host.rmdir()
        self.scene.rmdir()
        with self.assertRaisesRegex(RuntimeError,'preparation failed'):
            run_host([sys.executable,'nonexistent-scene.py','--client-script','placeholder'],
                     output=self.scene, host_output=self.host, model='fixture', executable='missing-proposal-cli')
        self.assertFalse(self.scene.exists())
        record=json.loads((self.host/'processes.json').read_text())
        self.assertNotIn('launcher',record)
        self.assertTrue(record['host_model']['reaped'])
        with self.assertRaises(ProcessLookupError):os.killpg(record['host_model']['pid'],0)

    def test_private_output_rejects_mount_overlap_before_creating_files_or_processes(self):
        for name in ('agent-prefix', 'python-prefix', 'simulation'):
            mount = self.root/name
            mount.mkdir()
            for private in (mount/'private-host', mount):
                with self.subTest(mount=name, private=private), self.assertRaisesRegex(ValueError, 'container mount'):
                    run_host([], output=self.root/'new-scene', host_output=private,
                             model='fixture', executable='unused', mounted_roots=(mount,))
            self.assertEqual(list(mount.iterdir()), [])

    def test_forced_shutdown_reaps_only_the_owned_process_group(self):
        ready=self.root/'ready'
        process=subprocess.Popen([sys.executable,'-c',
            'import signal,time;from pathlib import Path;signal.signal(signal.SIGTERM,signal.SIG_IGN);'
            f'Path({str(ready)!r}).touch();time.sleep(30)'],start_new_session=True)
        self.addCleanup(lambda:process.poll() is None and process.kill())
        self.wait_file(ready,process)
        record=finish(process,.05)
        self.assertTrue(record['group_forced'])
        self.assertEqual(record['returncode'],-signal.SIGKILL)
        with self.assertRaises(ProcessLookupError):os.killpg(process.pid,0)


if __name__ == '__main__':unittest.main()
