"""Deterministic handoff/lifecycle tests; Events choose the disputed order."""
import threading
import time
import unittest

from robot_agent._task_runtime import Coordinator, Exchange, Owner


class Resource:
    def __init__(self):
        self.calls = []
        self.closed = []

    def echo(self, value):
        self.calls.append((threading.get_ident(), value))
        return value

    def close(self):
        self.closed.append(threading.get_ident())
        return {'closed': True}


class RuntimeTests(unittest.TestCase):
    def owner(self, factory, *, close=lambda value: value.close()):
        exchange = Exchange('test-task')
        owner = Owner(exchange, 'io', factory, close=close)
        self.addCleanup(lambda: owner.finish(time.monotonic() + 2))
        return exchange, owner

    def test_stop_before_claim_calls_nothing_and_never_reactivates(self):
        resource = Resource()
        exchange, owner = self.owner(lambda: resource)
        call = exchange.publish('io', 'echo', ('old',), {}, time.monotonic() + 2)
        exchange.stop()
        with self.assertRaises(InterruptedError):
            exchange.wait('io', call, time.monotonic() + 2)
        self.assertFalse(exchange.collect('io').started)
        fresh = exchange.publish('io', 'echo', ('new',), {}, time.monotonic() + 2)
        self.assertEqual(fresh.state, 'completed')
        self.assertIsInstance(fresh.error, InterruptedError)
        owner.start()
        owner.finish(time.monotonic() + 2)
        self.assertFalse(resource.calls)

    def test_request_withdrawal_preserves_task_and_allows_next_call(self):
        resource = Resource()
        exchange, owner = self.owner(lambda: resource)
        old = exchange.publish('io', 'echo', ('old',), {}, time.monotonic() + 2)
        exchange.withdraw('io', old)
        self.assertFalse(exchange.stopped)
        self.assertFalse(exchange.collect('io').started)
        fresh = exchange.publish('io', 'echo', ('new',), {}, time.monotonic() + 2)
        owner.start()
        self.assertEqual(exchange.wait('io', fresh, time.monotonic() + 2), 'new')
        self.assertEqual([row[1] for row in resource.calls], ['new'])

    def test_completed_slot_is_bounded_and_cannot_block_close(self):
        resource, created = Resource(), []
        def factory():
            created.append(threading.get_ident())
            return resource
        exchange, owner = self.owner(factory)
        call = exchange.publish('io', 'echo', ({'data': [1]},), {}, time.monotonic() + 2)
        owner.start()
        with exchange.condition:
            self.assertTrue(exchange.condition.wait_for(lambda: call.state == 'completed', timeout=2))
        with self.assertRaises(RuntimeError):
            exchange.publish('io', 'echo', ('overwrite',), {}, time.monotonic() + 2)
        terminal = owner.finish(time.monotonic() + 2)
        self.assertTrue(terminal['thread_stopped'])
        self.assertEqual(terminal['close'], 'confirmed')
        self.assertEqual(resource.closed, created)
        self.assertEqual(resource.calls[0][0], created[0])
        self.assertNotEqual(created[0], threading.get_ident())
        self.assertEqual(exchange.collect('io').value, {'data': [1]})
        with self.assertRaises(RuntimeError):
            exchange.publish('io', 'echo', ('after-close',), {}, time.monotonic() + 2)

    def test_payload_aliases_and_expired_queued_call(self):
        resource = Resource()
        exchange, owner = self.owner(lambda: resource)
        data = {'value': [1]}
        call = exchange.publish('io', 'echo', (data,), {}, time.monotonic() + 2)
        data['value'][0] = 99
        owner.start()
        self.assertEqual(exchange.wait('io', call, time.monotonic() + 2), {'value': [1]})
        expired = exchange.publish('io', 'echo', ('expired',), {}, time.monotonic() - 1)
        with self.assertRaises(TimeoutError):
            exchange.wait('io', expired, time.monotonic() + 2)
        self.assertEqual(len(resource.calls), 1)

    def test_claimed_unknown_keeps_effect_and_closes_without_consumption(self):
        entered, release = threading.Event(), threading.Event()
        resource = Resource()
        def effect(value):
            resource.calls.append((threading.get_ident(), value))
            entered.set()
            if not release.wait(2):
                raise AssertionError('test did not release the in-flight call')
            raise RuntimeError('original response lost')
        resource.echo = effect
        exchange, owner = self.owner(lambda: resource)
        call = exchange.publish('io', 'echo', ('original-request',), {}, time.monotonic() + 2)
        owner.start()
        try:
            self.assertTrue(entered.wait(2))
            exchange.stop()
            with self.assertRaises(InterruptedError):
                exchange.wait('io', call, time.monotonic() + 2)
            exchange.close('io')
        finally:
            release.set()
        terminal = owner.finish(time.monotonic() + 2)
        self.assertTrue(terminal['thread_stopped'])
        result = exchange.collect('io')
        self.assertTrue(result.started)
        self.assertIsInstance(result.error, RuntimeError)
        self.assertEqual(resource.calls[0][1], 'original-request')
        self.assertEqual(len(resource.calls), 1)
        self.assertEqual(len(resource.closed), 1)

    def test_stop_during_initialization_closes_created_resource(self):
        entered, release = threading.Event(), threading.Event()
        resource = Resource()
        def factory():
            entered.set()
            if not release.wait(2):
                raise AssertionError('test did not release construction')
            return resource
        exchange, owner = self.owner(factory)
        call = exchange.publish('io', 'echo', ('request',), {}, time.monotonic() + 2)
        owner.start()
        try:
            self.assertTrue(entered.wait(2))
            exchange.stop()
            exchange.close('io')
            self.assertFalse(exchange.collect('io').started)
            preparing = owner.finish(time.monotonic())
            self.assertFalse(preparing['thread_stopped'])
            self.assertEqual(preparing['initialization'], 'preparing')
        finally:
            release.set()
        terminal = owner.finish(time.monotonic() + 2)
        self.assertTrue(terminal['thread_stopped'])
        self.assertEqual(terminal['close'], 'confirmed')
        self.assertFalse(resource.calls)
        self.assertEqual(len(resource.closed), 1)

    def test_initialization_and_close_errors_have_distinct_terminal_facts(self):
        def failure():
            raise ValueError('construction failed')
        exchange, owner = self.owner(failure)
        call = exchange.publish('io', 'echo', ('request',), {}, time.monotonic() + 2)
        owner.start()
        with self.assertRaisesRegex(RuntimeError, 'construction failed'):
            exchange.wait('io', call, time.monotonic() + 2)
        result = owner.finish(time.monotonic() + 2)
        self.assertEqual(result['initialization'], 'failed')
        self.assertEqual(result['close'], 'not_needed')
        def close_error(resource):
            resource.close()
            raise OSError('close reply lost')
        resource = Resource()
        exchange, owner = self.owner(lambda: resource, close=close_error)
        call = exchange.publish('io', 'echo', ('request',), {}, time.monotonic() + 2)
        owner.start()
        exchange.wait('io', call, time.monotonic() + 2)
        result = owner.finish(time.monotonic() + 2)
        self.assertTrue(result['thread_stopped'])
        self.assertEqual(result['close'], 'error')
        self.assertIn('close reply lost', result['close_error'])
        self.assertEqual(len(resource.closed), 1)

    def test_noncooperative_call_is_draining_and_later_joinable(self):
        entered, release = threading.Event(), threading.Event()
        resource = Resource()
        def echo(value):
            entered.set()
            if not release.wait(2):
                raise AssertionError('test did not release call')
            return value
        resource.echo = echo
        exchange, owner = self.owner(lambda: resource)
        exchange.publish('io', 'echo', ('value',), {}, time.monotonic() + 2)
        owner.start()
        try:
            self.assertTrue(entered.wait(2))
            result = owner.finish(time.monotonic())
            self.assertFalse(result['thread_stopped'])
            self.assertEqual(result['close'], 'draining')
            self.assertEqual(result['initialization'], 'ready')
            self.assertFalse(owner.thread.daemon)
        finally:
            release.set()
        self.assertTrue(owner.finish(time.monotonic() + 2)['thread_stopped'])


if __name__ == '__main__':
    unittest.main()
