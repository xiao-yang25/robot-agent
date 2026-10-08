"""Private single-task handoff; business state stays with the caller.

Two bounded call slots share one condition. Owners create/use/close their own
resources; completion consumption cannot block owner close. No daemon workers.
"""
from copy import deepcopy
from dataclasses import dataclass
import threading
import time


@dataclass
class Call:
    identity: str
    method: str
    args: tuple
    kwargs: dict
    deadline: float
    cleanup: bool = False
    association: dict = None
    state: str = 'queued'
    withdrawn: bool = False
    started: bool = False
    value: object = None
    error: BaseException = None


class Exchange:
    def __init__(self, task_id):
        self.task_id = task_id
        self.condition = threading.Condition()
        self.stopped = False
        self.slots = {'decision': None, 'io': None}
        self.closing = {'decision': False, 'io': False}
        self.terminals = {}
        self.preparation = {'decision': 'not_started', 'io': 'not_started'}
        self.sequence = 0

    def _reject(self, call, error):
        call.error, call.state = error, 'completed'
        self.condition.notify_all()

    def stop(self):
        with self.condition:
            self.stopped = True
            for call in self.slots.values():
                if call is not None and call.state == 'queued' and not call.cleanup:
                    self._reject(call, InterruptedError('task stopped before claim'))
            self.condition.notify_all()

    def withdrawn(self, call):
        with self.condition:
            return call.withdrawn or (not call.cleanup and self.stopped)

    def owner_stopped(self, role):
        with self.condition:
            call = self.slots[role]
            return self.stopped or self.closing[role] or (call is not None and call.withdrawn)

    def withdraw(self, role, call):
        with self.condition:
            if self.slots[role] is not call:
                raise ValueError('withdrawal does not belong to the active call')
            call.withdrawn = True
            if call.state == 'queued':
                self._reject(call, InterruptedError('call withdrawn before claim'))
            self.condition.notify_all()

    def publish(self, role, method, args, kwargs, deadline, *, cleanup=False, association=None):
        # Isolate mutable aliases outside the short exchange lock.
        args, kwargs = deepcopy(args), deepcopy(kwargs)
        association = deepcopy({} if association is None else association)
        with self.condition:
            if self.closing[role] or role in self.terminals:
                raise RuntimeError('owner is closing or stopped')
            if self.slots[role] is not None:
                raise RuntimeError('previous completion must be consumed')
            self.sequence += 1
            call = Call(f'{self.task_id}-{role}-{self.sequence}', method, args,
                        kwargs, deadline, cleanup, association)
            self.slots[role] = call
            if self.stopped and not cleanup:
                self._reject(call, InterruptedError('task stopped before claim'))
            self.condition.notify_all()
            return call

    def claim(self, role):
        with self.condition:
            while True:
                call = self.slots[role]
                if call is not None and call.state == 'queued':
                    if (self.stopped or self.closing[role] or call.withdrawn) and not call.cleanup:
                        self._reject(call, InterruptedError('call withdrawn before claim'))
                    elif time.monotonic() >= call.deadline:
                        self._reject(call, TimeoutError('call expired before claim'))
                    else:
                        call.state, call.started = 'claimed', True
                        return call
                # Retaining an ordinary completion does not delay close.
                if self.closing[role]:
                    return None
                self.condition.wait()

    def complete(self, role, call, value, error):
        value = deepcopy(value)
        with self.condition:
            if self.slots[role] is not call or call.state != 'claimed':
                raise RuntimeError('completion does not belong to the claimed call')
            call.value, call.error, call.state = value, error, 'completed'
            self.condition.notify_all()

    def wait(self, role, call, deadline, *, stop_requested=lambda: False,
             interruptible=True):
        while True:
            # User callbacks are never called under the exchange lock.
            if interruptible and stop_requested():
                self.stop()
            with self.condition:
                if self.slots[role] is not call:
                    raise ValueError('wait does not belong to the active call')
                if interruptible and (self.stopped or call.withdrawn):
                    self.withdraw(role, call)
                    raise InterruptedError('call withdrawn; original completion retained')
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self.withdraw(role, call)
                    raise TimeoutError('call wait expired; original completion retained')
                if call.state == 'completed':
                    self.slots[role] = None
                    self.condition.notify_all()
                    if call.error is not None:
                        raise call.error
                    return call.value
                self.condition.wait(min(.01, remaining))

    def collect(self, role):
        with self.condition:
            call = self.slots[role]
            if call is not None and call.state == 'completed':
                self.slots[role] = None
                self.condition.notify_all()
                return call
            return None

    def close(self, role):
        with self.condition:
            self.closing[role] = True
            call = self.slots[role]
            if call is not None and call.state == 'queued' and not call.cleanup:
                self._reject(call, InterruptedError('owner closing before claim'))
            self.condition.notify_all()


class Owner:
    def __init__(self, exchange, role, factory, *, close=None):
        self.exchange, self.role = exchange, role
        self.factory, self.close_resource = factory, close
        self.thread = threading.Thread(target=self._run, name=f'agent-{role}', daemon=False)
        self.started = False

    def start(self):
        self.thread.start()
        self.started = True

    def _run(self):
        resource = None
        terminal = {'initialization': 'not_started', 'close': 'not_needed'}
        try:
            with self.exchange.condition:
                create = not self.exchange.stopped and not self.exchange.closing[self.role]
            if not create:
                return
            with self.exchange.condition:
                self.exchange.preparation[self.role] = 'preparing'
            resource = self.factory()
            terminal['initialization'] = 'ready'
            with self.exchange.condition:
                self.exchange.preparation[self.role] = 'ready'
            while True:
                call = self.exchange.claim(self.role)
                if call is None:
                    break
                value, error = None, None
                try:
                    value = getattr(resource, call.method)(*call.args, **call.kwargs)
                except Exception as caught:
                    error = caught
                self.exchange.complete(self.role, call, value, error)
        except BaseException as error:
            terminal.update(owner_error=f'{type(error).__name__}: {error}')
            if resource is None:
                terminal['initialization'] = 'failed'
            with self.exchange.condition:
                self.exchange.preparation[self.role] = terminal['initialization']
                call = self.exchange.slots[self.role]
                if call is not None and call.state in ('queued', 'claimed'):
                    self.exchange._reject(call, RuntimeError(terminal['owner_error']))
        finally:
            if resource is not None and self.close_resource is not None:
                try:
                    terminal['close_response'] = self.close_resource(resource)
                    terminal['close'] = 'confirmed'
                except BaseException as error:
                    terminal.update(close='error', close_error=f'{type(error).__name__}: {error}')
            with self.exchange.condition:
                self.exchange.terminals[self.role] = terminal
                self.exchange.condition.notify_all()

    def finish(self, deadline):
        self.exchange.close(self.role)
        if self.started:
            self.thread.join(max(0., deadline - time.monotonic()))
        with self.exchange.condition:
            result = dict(self.exchange.terminals.get(self.role, {
                'initialization': self.exchange.preparation[self.role],
                'close': 'draining' if self.started else 'not_needed'}))
        result = deepcopy(result)
        result['thread_stopped'] = not self.thread.is_alive()
        return result


class Coordinator:
    """Caller-owned exchange consumption and closing budget; no domain verdicts."""
    def __init__(self, task_id, stop_requested, cleanup_seconds):
        self.exchange = Exchange(task_id)
        self.stop_requested = stop_requested
        self.cleanup_seconds = cleanup_seconds
        self.cleanup_deadline = None
        self.pending = {'decision': None, 'io': None}
        self.late = []

    def stopped(self):
        if self.stop_requested():
            self.exchange.stop()
        with self.exchange.condition:
            return self.exchange.stopped

    def cleanup_until(self):
        if self.cleanup_deadline is None:
            self.cleanup_deadline = time.monotonic() + self.cleanup_seconds
        return self.cleanup_deadline

    def retain(self, role, call):
        with self.exchange.condition:
            record = {'role': role, 'command_id': call.identity, 'method': call.method,
                      'started': call.started, 'state': call.state, 'value': call.value,
                      'association': call.association}
            error = call.error
        record['error'] = None if error is None else f'{type(error).__name__}: {error}'
        self.late.append(record)

    def call(self, role, method, args, kwargs, *, deadline, claim_deadline=None,
             cleanup=False, association=None):
        previous = self.pending[role]
        if previous is not None:
            if not cleanup:
                raise RuntimeError('abandoned call requires closing before another business command')
            try:
                self.exchange.wait(role, previous, deadline, interruptible=False)
            except Exception:
                if previous.state != 'completed':
                    raise
                self.exchange.collect(role)
            self.retain(role, previous)
            self.pending[role] = None
        call = self.exchange.publish(role, method, args, kwargs,
                                     deadline if claim_deadline is None else claim_deadline,
                                     cleanup=cleanup, association=association)
        self.pending[role] = call
        try:
            value = self.exchange.wait(role, call, deadline,
                                       stop_requested=self.stop_requested, interruptible=not cleanup)
        except Exception:
            with self.exchange.condition:
                if self.exchange.slots[role] is None:
                    self.pending[role] = None
            raise
        self.pending[role] = None
        return value
