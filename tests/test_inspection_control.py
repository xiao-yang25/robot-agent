import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from robot_agent.inspection_control import LocalTaskControl, PROTOCOL, read_status, request_cancel


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.stopped = threading.Event()
        self.control = LocalTaskControl(self.root, self.stopped)
        self.control.start()
        self.addCleanup(self.control.finish, dict(status='cancelled', coordination={'resources_closed':True}))
        self.wait(lambda: (self.control.directory/'status.json').exists())

    def wait(self, predicate):
        until=time.monotonic()+3
        while not predicate() and time.monotonic()<until: time.sleep(.01)
        self.assertTrue(predicate())

    def test_bound_request_is_consumed_without_touching_task_state(self):
        self.control.publish(dict(task_id='task',phase='navigation_A',reason=None))
        response=request_cancel(self.control.directory)
        self.assertFalse(response['acknowledged'])
        self.wait(self.stopped.is_set)
        self.wait(lambda: read_status(self.control.directory)['cancel_requested'])
        value=read_status(self.control.directory)
        self.assertEqual(value['task']['phase'],'navigation_A')
        self.assertEqual(value['native_cleanup'],'unknown')
        request_cancel(self.control.directory)
        self.assertEqual(read_status(self.control.directory)['instance_id'],response['instance_id'])

    def test_stale_and_malformed_request_cannot_stop_current_task(self):
        for request in (dict(protocol=PROTOCOL,instance_id='0'*32,command='cancel'),{'command':'reset'}):
            (self.control.directory/'request.json').write_text(json.dumps(request))
            self.wait(lambda: read_status(self.control.directory)['request_error'] is not None)
            self.assertFalse(self.stopped.is_set())
        response=request_cancel(self.control.directory)
        self.wait(self.stopped.is_set)
        self.assertEqual(response['request'],'written')

    def test_terminal_rejects_cancel_and_final_status_keeps_limits(self):
        self.control.publish(dict(task_id='task',phase='completed',reason='normal'))
        self.wait(lambda: read_status(self.control.directory)['lifecycle']=='closing')
        with self.assertRaises(ValueError): request_cancel(self.control.directory)
        result=self.control.finish(dict(task_id='task',status='completed',native_cleanup='unknown',
            task_verdict='unassessed',coordination={'resources_closed':False}))
        self.assertTrue(result['worker_stopped'])
        status=read_status(self.control.directory)
        self.assertEqual(status['lifecycle'],'finished')
        self.assertFalse(status['coordination']['resources_closed'])
        self.assertEqual(status['native_cleanup'],'unknown')

    def test_write_failure_requests_stop_and_is_not_hidden(self):
        with patch('robot_agent.inspection_control._atomic',side_effect=OSError('disk unavailable')):
            self.wait(self.stopped.is_set)
        result=self.control.finish(dict(status='cancelled'))
        self.assertTrue(result['worker_stopped'])
        self.assertIn('disk unavailable',result['error'])

    def test_existing_control_directory_is_not_reused(self):
        with self.assertRaises(FileExistsError): LocalTaskControl(self.root, threading.Event())


if __name__=='__main__':unittest.main()
