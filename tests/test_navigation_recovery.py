"""Single-backup business boundaries; synthetic native facts, no ROS qualification."""
from copy import deepcopy
import unittest

from robot_agent.navigation import NavigationBudget, SITES
from robot_agent.navigation_recovery import RecoveryNavigationTask, PROFILE, FAILURE_FIELDS
from test_navigation import SessionFixture


class Proposal:
    def __init__(self, callback=lambda context, answer: None):
        self.contexts, self.callback = [], callback

    def decide(self, context, observation, deadline, stopped):
        self.contexts.append(deepcopy(context))
        if set(observation) != {'reference', 'pose', 'sample_sim_seconds', 'sensor_health'}:
            raise AssertionError('undeclared simulator truth reached recovery model')
        answer = dict(task_id=context['task_id'], phase=context['phase'],
                      observation_reference=deepcopy(context['observation_reference']),
                      action=context['allowed_actions'][0], reason='controlled backup proposal')
        if 'failure_context' in context:
            answer.update({key: context['failure_context'][key] for key in FAILURE_FIELDS})
        self.callback(context, answer)
        return answer


class FailedSession(SessionFixture):
    def __init__(self, now):
        super().__init__()
        self.now, self.release_at, self.a_success, self.b_failure = now, .3, False, False
        self.status_callback = lambda record: None
        self.events = []

    def capabilities(self):
        return {**super().capabilities(), 'profile': PROFILE}

    def submit(self, request, **args):
        self.events.append(args['site']+'_submit')
        row = super().submit(request, **args)
        if row['state'] != 'rejected':
            stored = self.records[request]
            stored.update(stage=args['site'], scope_id=('c' if args['site']=='A' else 'd')*32, generation=1)
            stored['receipt']['authority']['admitted_at'] = 1000
            stored['receipt'].update(deadline=1000+args['deadline_ms']*1000000,
                                   expiry_observed_at=None, cancellation_requested_at=None,
                                   native_acceptance='pending')
            row = deepcopy(stored)
        return row

    def status(self, request):
        row = self.records[request]
        if row['site'] == 'B' or self.a_success:
            result = super().status(request)
            if self.b_failure and row['site'] == 'B':
                row['result'] = None
                row['receipt'].update(native_outcome='failed', output='pending')
                result = deepcopy(row)
        else:
            row.update(goal_id='a'*32, result=None)
            row['receipt'].update(native_identity='a'*32, native_acceptance='accepted',
                                  native_outcome='failed', settlement='pending', output='pending')
            if self.now() >= self.release_at:
                row['state'] = 'finished'
                row['receipt'].update(authority_disposition='released', settlement='settled',
                    output='not_delivered', output_non_delivery_reason='no_output', result_reference='')
                self.events.append('A_released')
            result = deepcopy(row)
        self.status_callback(result)
        return result


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.now, self.stopped = 0., False
        self.session = FailedSession(lambda: self.now)

    def task(self, proposal=None, **kwargs):
        def sleep(seconds): self.now += seconds
        return RecoveryNavigationTask(proposal or Proposal(), clock=lambda: self.now,
            sleep=sleep, stop_requested=lambda: self.stopped, **kwargs)

    def test_successful_a_finishes_only_a_without_recovery_proposal(self):
        self.session.a_success = True
        proposal = Proposal()
        report = self.task(proposal).run(self.session)
        self.assertEqual(report['status'], 'completed', report)
        self.assertEqual(report['completed_sites'], ['A'])
        self.assertEqual([c['phase'] for c in proposal.contexts], ['prepare','final'])
        self.assertEqual(proposal.contexts[-1]['completion_site'], 'A')
        self.assertEqual(len(self.session.submissions), 1)
        self.assertNotIn('recovery', report)

    def test_explicit_map_binding_requires_capability_and_observation_match(self):
        expected = 'turtlebot3-occupied-a-probe-v1'
        for mismatch in ('none', 'capability', 'observation', 'reference', 'changes_after_proposal'):
            with self.subTest(mismatch=mismatch):
                self.setUp()
                session = self.session
                cap, observe = session.capabilities, session.observe
                def capability():
                    return {**cap(), 'map_id': expected if mismatch != 'capability' else 'other-map'}
                def observation():
                    row = observe()
                    row['map_id'] = expected if mismatch != 'observation' else 'other-map'
                    row['reference']['map_id'] = expected if mismatch != 'reference' else 'other-map'
                    return row
                session.capabilities, session.observe = capability, observation
                def changed(context, answer):
                    if context['phase'] == 'after_failure' and mismatch == 'changes_after_proposal':
                        session.capabilities = lambda: {**capability(), 'map_id': 'other-map'}
                report = self.task(Proposal(changed), expected_map_id=expected).run(session)
                self.assertEqual(report['status'], 'completed' if mismatch == 'none' else 'needs_help', report)
                self.assertEqual(len(session.submissions), 2 if mismatch == 'none' else
                                 1 if mismatch == 'changes_after_proposal' else 0)
                if mismatch == 'none':
                    self.assertTrue(all(c['context']['observation_reference']['map_id'] == expected
                                        for c in report['decisions']))

    def test_invalid_map_identity_is_rejected_before_task_creation(self):
        for value in (None, '', ' map', 'map ', 'map\nchanged', 'a'*129):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.task(expected_map_id=value)

    def test_only_released_failure_allows_one_fresh_b_and_b_stays_pending(self):
        def require_release(context, answer):
            if context['phase'] == 'after_failure':
                self.assertIn('A_released', self.session.events)
                self.session.events.append('after_failure')
        proposal = Proposal(require_release)
        task = self.task(proposal)
        report = task.run(self.session)
        self.assertEqual(report['status'], 'completed', report)
        self.assertEqual(report['completed_sites'], ['B'])
        self.assertEqual([c['phase'] for c in proposal.contexts], ['prepare','after_failure','final'])
        self.assertLess(self.session.events.index('A_released'), self.session.events.index('after_failure'))
        self.assertLess(self.session.events.index('after_failure'), self.session.events.index('B_submit'))
        a, b = report['operations']
        self.assertEqual(a['receipt']['native_outcome'], 'failed')
        self.assertIsNone(a['result'])
        self.assertEqual(b['receipt']['settlement'], 'pending')
        self.assertEqual(b['observation_reference'], report['decisions'][1]['revalidated_observation']['reference'])
        self.assertNotEqual(b['observation_reference'], report['decisions'][1]['context']['observation_reference'])
        self.assertEqual(report['task_verdict'], 'unassessed')
        self.assertEqual(report['native_cleanup'], 'unknown')
        self.assertEqual(report['execution_cleanup'], 'pending')
        self.assertTrue(report['requires_connection_close'])
        self.assertFalse(self.session.cancellations)
        with self.assertRaises(ValueError): task.run(self.session)

    def test_failed_pending_a_never_invokes_recovery_and_cancels_exact_request(self):
        self.session.release_at = 100
        proposal = Proposal()
        report = self.task(proposal, budget=NavigationBudget(operation_seconds=.5)).run(self.session)
        self.assertEqual(report['status'], 'needs_help')
        self.assertEqual(len(proposal.contexts), 1)
        self.assertEqual(len(self.session.submissions), 1)
        self.assertEqual(self.session.cancellations, [self.session.submissions[0][0]])
        self.assertFalse(report['completed_sites'])

    def test_backup_failed_has_no_second_recovery_or_third_submission(self):
        self.session.b_failure = True
        proposal = Proposal()
        report = self.task(proposal).run(self.session)
        self.assertEqual(report['status'], 'needs_help')
        self.assertEqual([c['phase'] for c in proposal.contexts], ['prepare','after_failure'])
        self.assertEqual(len(self.session.submissions), 2)
        self.assertEqual(self.session.cancellations, [self.session.submissions[1][0]])
        self.assertFalse(report['completed_sites'])

    def test_abstention_after_release_is_zero_b_without_cancelling_released_a(self):
        proposal = Proposal(lambda c,a: a.update(action='help') if c['phase']=='after_failure' else None)
        report = self.task(proposal).run(self.session)
        self.assertEqual(report['status'], 'needs_help')
        self.assertEqual(len(self.session.submissions), 1)
        self.assertFalse(self.session.cancellations)
        self.assertFalse(report['completed_sites'])

    def test_ambiguous_a_or_b_submission_never_retries(self):
        for site in ('A','B'):
            with self.subTest(site=site):
                self.setUp()
                if site == 'A': self.session.ambiguous = True
                proposal = Proposal(lambda c,a: setattr(self.session,'ambiguous',True) if c['phase']=='after_failure' else None)
                report = self.task(proposal).run(self.session)
                self.assertEqual(report['status'], 'needs_help')
                self.assertEqual(len(self.session.submissions), 1 if site=='A' else 2)
                self.assertEqual(self.session.cancellations, [self.session.submissions[-1][0]])

    def test_incomplete_or_cancelled_release_never_proposes_b(self):
        mutations = [lambda r:r['receipt'].update(output_non_delivery_reason='authority_revoked'),
                     lambda r:r['receipt'].update(cancellation_requested_at=1),
                     lambda r:r['receipt'].update(expiry_observed_at=1),
                     lambda r:r['receipt'].update(native_acceptance='pending'),
                     lambda r:r['receipt'].update(native_outcome='cancelled'),
                     lambda r:r.update(result={'invented': True})]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self.setUp()
                self.session.status_callback = mutate
                proposal = Proposal()
                report = self.task(proposal).run(self.session)
                self.assertEqual(report['status'], 'needs_help', report)
                self.assertEqual(len(proposal.contexts), 1)
                self.assertEqual(len(self.session.submissions), 1)

    def test_changed_admission_deadline_scope_or_goal_cannot_release(self):
        for field in ('deadline','scope','goal','reference'):
            with self.subTest(field=field):
                self.setUp()
                def mutate(row):
                    if field=='deadline': row['receipt']['deadline'] += 1
                    if field=='scope': row['scope_id'] = 'e'*32
                    if field=='goal' and self.now >= .2:
                        row['goal_id']='f'*32; row['receipt']['native_identity']='f'*32
                    if field=='reference': row['observation_reference']['session_id']='foreign'
                self.session.status_callback = mutate
                proposal = Proposal()
                report = self.task(proposal).run(self.session)
                self.assertEqual(report['status'], 'needs_help', report)
                self.assertEqual(len(self.session.submissions), 1)
                self.assertEqual(len(proposal.contexts), 1)

    def test_failure_outcome_cannot_regress_to_pending_before_release(self):
        self.session.status_callback = lambda r:r['receipt'].update(native_outcome='pending') if self.now>=.2 else None
        report = self.task().run(self.session)
        self.assertEqual(report['status'], 'needs_help')
        self.assertEqual(len(self.session.submissions), 1)

    def test_foreign_model_failure_identity_or_phase_rejects_b(self):
        for field in ('recovery_id','request_id','operation_id','goal_id','phase','observation_reference'):
            with self.subTest(field=field):
                self.setUp()
                def mutate(c,a):
                    if c['phase']=='after_failure':
                        a[field] = True if field=='operation_id' else {} if field=='observation_reference' else 'foreign'
                report = self.task(Proposal(mutate)).run(self.session)
                self.assertEqual(report['status'], 'needs_help', report)
                self.assertEqual(len(self.session.submissions), 1)
                self.assertFalse(report['decisions'][-1]['accepted'])

    def test_late_or_cancelled_recovery_proposal_has_zero_b(self):
        for cancel in (False,True):
            with self.subTest(cancel=cancel):
                self.setUp()
                def delayed(c,a):
                    if c['phase']=='after_failure':
                        self.now += 31
                        self.stopped = cancel
                report = self.task(Proposal(delayed)).run(self.session)
                self.assertEqual(report['status'], 'cancelled' if cancel else 'needs_help')
                self.assertEqual(len(self.session.submissions), 1)
                self.assertFalse(report['decisions'][-1]['accepted'])

    def test_original_task_budget_is_not_refreshed_after_failure(self):
        def elapsed(c,a):
            if c['phase']=='after_failure': self.now=1.01
        report = self.task(Proposal(elapsed), budget=NavigationBudget(task_seconds=1)).run(self.session)
        self.assertEqual(report['status'], 'needs_help')
        self.assertEqual(len(self.session.submissions), 1)
        self.assertLessEqual(self.session.submissions[0][1]['deadline_ms'],1000)

    def test_post_proposal_loss_of_release_or_fresh_scene_admits_no_b(self):
        for changed in ('release','pose','epoch','input','ready'):
            with self.subTest(changed=changed):
                self.setUp()
                def mutate(c,a):
                    if c['phase']!='after_failure': return
                    if changed=='release':
                        self.session.status_callback=lambda r:r['receipt'].update(authority_disposition='revoked')
                    if changed=='pose': self.session.pose[0] += .1
                    if changed=='epoch': self.session.epoch += 1
                    if changed=='input': self.session.valid = False
                    if changed=='ready': self.session.available = False
                report = self.task(Proposal(mutate)).run(self.session)
                self.assertEqual(report['status'], 'needs_help', report)
                self.assertEqual(len(self.session.submissions),1)

    def test_old_profile_does_not_silently_enable_recovery(self):
        self.session.capabilities=SessionFixture().capabilities
        report=self.task().run(self.session)
        self.assertEqual(report['status'],'needs_help')
        self.assertFalse(self.session.submissions)

    def test_optional_metadata_is_not_authority_or_failure_context(self):
        self.session.status_callback=lambda r:r.update(optional_metadata={'unrecognized':True})
        proposal=Proposal(lambda c,a:a.update(optional_metadata='ignored'))
        report=self.task(proposal).run(self.session)
        self.assertEqual(report['status'],'completed',report)
        failure=proposal.contexts[1]['failure_context']
        self.assertEqual(set(failure), {*FAILURE_FIELDS,'observation_reference','native_outcome'})


if __name__=='__main__': unittest.main()
