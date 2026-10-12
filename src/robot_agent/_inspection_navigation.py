"""Private inspection adaptation of the public navigation Session.

Use only in the existing I/O owner. Caller grants/revokes bounded submissions;
source state remains in InspectionSource and execution authority in Harness.
No thread, retry, task advancement or native release is introduced here.
"""
from copy import deepcopy
from dataclasses import dataclass
import math
import threading
import time

from ._inspection_policy import NavigationFact
from ._inspection_source import CheckRecord, InspectionSource
from ._navigation_contract import NavigationContract, SITES, finite


@dataclass(frozen=True)
class Admission:
    request_id: str
    site: str
    generation: int
    operation_deadline: float
    admission_deadline: float
    basis: CheckRecord | None = None


class InspectionNavigation:
    """Session methods run on one owner; only grant/revoke may cross threads.

    The short grant lock is never held during RPC or source calls. Guard checks
    immediately precede submit but cannot make a remote/global atomic cutoff.
    Preserve attempted requests even when the response or its facts are unknown.
    """
    def __init__(self, session_factory, source, *, task_deadline,
                 stop_requested=lambda: False, clock=time.monotonic):
        if not isinstance(source, InspectionSource) or not finite(task_deadline):
            raise ValueError('invalid inspection navigation dependencies')
        self.source, self.task_deadline = source, task_deadline
        self.stopped, self.now = stop_requested, clock
        self.contract = NavigationContract()
        self.lock = threading.Lock()
        self.grants, self.attempts, self.facts = {}, {}, {}
        self.revoked = set()
        self.closed = False
        self.session = session_factory()

    def authorize(self, admission):
        """Caller passes the original committed intent and actual source record."""
        if (not isinstance(admission, Admission) or admission.site not in SITES
                or not isinstance(admission.request_id, str) or not 0 < len(admission.request_id) <= 128
                or type(admission.generation) is not int or admission.generation != self.source.generation
                or not all(finite(v) for v in (admission.operation_deadline, admission.admission_deadline))
                or not self.now() < admission.admission_deadline <= admission.operation_deadline <= self.task_deadline
                or (admission.site == 'A' and admission.basis is not None)
                or (admission.site == 'B' and (not isinstance(admission.basis, CheckRecord)
                    or admission.basis.site != 'A' or admission.basis.target != 'indicator-A'
                    or admission.basis.classification != 'abnormal'))):
            raise ValueError('invalid original inspection admission')
        with self.lock:
            if self.closed or admission.request_id in self.grants or len(self.grants) >= 2:
                raise RuntimeError('admission cannot be replaced or extended')
            if any(old.site == admission.site for old in self.grants.values()):
                raise RuntimeError('site already reserved')
            self.grants[admission.request_id] = admission

    def revoke(self, request_id):
        with self.lock:
            if request_id not in self.grants:
                raise ValueError('foreign inspection admission')
            self.revoked.add(request_id)

    def _authorization(self, request_id):
        with self.lock:
            admission = self.grants.get(request_id)
            withdrawn = self.closed or request_id in self.revoked
        if (withdrawn or admission is None or self.stopped()
                or self.now() >= min(self.task_deadline, admission.admission_deadline, admission.operation_deadline)):
            raise InterruptedError('inspection admission withdrawn or expired')
        return admission

    def _grant(self, request_id):
        admission = self._authorization(request_id)
        if not self.source.refresh() or admission.generation != self.source.generation:
            raise ValueError('inspection source unavailable before submit')
        if admission.site == 'B':
            a = [fact for fact in self.facts.values() if fact.site == 'A']
            if (len(a) != 1 or not a[0].reusable or not self.source.applicable(admission.basis)):
                raise ValueError('B requires actual reusable A and applicable A anomaly')
        elif self.attempts:
            raise ValueError('initial A cannot follow another attempted operation')
        if self._authorization(request_id) is not admission:
            raise InterruptedError('inspection admission changed during source check')
        return admission

    def prepare(self, *, require_available=True):
        if self.closed or self.stopped() or self.now() >= self.task_deadline:
            raise InterruptedError('inspection navigation unavailable')
        cap = self.contract.validate_capabilities(self.session.capabilities(),
                                                   require_available=require_available)
        observation = self.contract.normalize_observation(self.session.observe())
        if self.stopped() or self.now() >= self.task_deadline:
            raise InterruptedError('inspection navigation preparation expired')
        return dict(available=cap.get('available') is True, observation=observation)

    def submit(self, request_id):
        if request_id in self.attempts:
            raise RuntimeError('ambiguous/previous inspection submission must not be replayed')
        admission = self._grant(request_id)
        # Fetch a fresh public reference and current permission on the actual
        # owner after claim, not an earlier caller/decision snapshot.
        prepared = self.prepare()
        observation = prepared['observation']
        if admission.site == 'B' and math.dist(observation['pose'], SITES['A'][:2]) > .3:
            raise ValueError('fresh map feedback does not confirm preceding A')
        if self._grant(request_id) is not admission:
            raise InterruptedError('inspection admission changed before submit')
        remaining = min(self.contract.maximum_deadline_ms,
                        int((admission.operation_deadline-self.now())*1000))
        if remaining < 1:
            raise TimeoutError('no original inspection operation budget remains')
        # Reserve correlation before crossing the Session boundary. An exception
        # after this point retains the possible original effect and forbids replay.
        attempt = dict(site=admission.site,
            reference=deepcopy(observation['reference']),
            sample_sim_seconds=observation['sample_sim_seconds'], operation_id=None, record=None)
        if self._authorization(request_id) is not admission:
            raise InterruptedError('inspection admission changed before Session boundary')
        self.attempts[request_id] = attempt
        record = self.session.submit(request_id, site=admission.site,
            expected_observation=observation['reference'], deadline_ms=remaining)
        return self._result(request_id, record)

    def _result(self, request_id, record):
        attempt = self.attempts[request_id]
        attempt['record'] = deepcopy(record)
        site, reference = attempt['site'], attempt['reference']
        if not isinstance(record, dict):
            raise ValueError('navigation result is not a record')
        if record.get('state') == 'rejected' and attempt['operation_id'] is None:
            if record.get('request_id') != request_id:
                raise ValueError('navigation rejection association changed')
            fact = NavigationFact(request_id, site, None, 'rejected')
        else:
            operation = record.get('operation_id')
            if type(operation) is not int or not 0 < operation < 2**64:
                raise ValueError('navigation admission identity missing')
            if attempt['operation_id'] is not None and operation != attempt['operation_id']:
                raise ValueError('original navigation operation changed')
            receipt = record.get('receipt', {})
            if not isinstance(receipt, dict):
                raise ValueError('invalid navigation receipt')
            failed = (receipt.get('authority_disposition') == 'revoked'
                      or receipt.get('native_outcome') in ('failed', 'cancelled'))
            if failed:
                self.contract.associated_receipt(record, request_id, site, operation, reference)
                done = False
            else:
                done = self.contract.validate_record(record, request_id, site, operation, reference)
            attempt['operation_id'] = operation
            verified = False
            if done:
                current = self.contract.normalize_observation(self.session.observe())
                verified = (current['sample_sim_seconds'] >= attempt['sample_sim_seconds']
                            and math.dist(current['pose'], SITES[site][:2]) <= .3)
                if not verified:
                    raise ValueError('fresh map feedback does not confirm navigation arrival')
            fact = NavigationFact(request_id, site, operation,
                'failed' if failed else 'arrived' if done else 'pending',
                pose_verified=verified, reusable=done and site == 'A')
        self.facts[request_id] = fact
        return fact

    def status(self, request_id):
        if request_id not in self.attempts:
            raise ValueError('no original inspection attempt to query')
        return self._result(request_id, self.session.status(request_id))

    def cancel(self, request_id):
        if request_id not in self.grants:
            raise ValueError('foreign inspection cancellation')
        self.revoke(request_id)
        if request_id not in self.attempts:
            return dict(request_id=request_id, submit_attempted=False, closure='not_submitted')
        response = self.session.cancel(request_id)
        record = response.get('record') if isinstance(response, dict) else None
        if record is not None:
            self._result(request_id, record)
        return response

    def close(self):
        with self.lock:
            self.closed = True
            self.revoked.update(self.grants)
        return self.session.close()
