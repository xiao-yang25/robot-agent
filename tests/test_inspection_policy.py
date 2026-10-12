"""Station business contracts and owned asynchronous handoffs, without ROS/actions."""
from dataclasses import FrozenInstanceError, replace
import threading
import time
import unittest

from robot_agent._inspection_policy import (Conditions, Control, DecisionKey, NavigationFact,
    Proposal, WindowClosed, advance, new_task, report)
from robot_agent._inspection_source import CheckRecord, Frame, InspectionSource, SITES
from robot_agent._task_events import EventInbox
from robot_agent._task_runtime import Coordinator, Owner
from robot_agent.navigation import NavigationBudget
from test_inspection_source import Clock


class Flow:
    def __init__(self, budget=NavigationBudget(task_seconds=90, decision_seconds=30, operation_seconds=40)):
        self.state=new_task('inspection',started_at=0.,budget=budget)
        self.conditions=Conditions(0.,7,True,True,True)
        self.intents=[]

    def step(self,event,**changes):
        changes.setdefault('now',self.conditions.now+.1)
        self.conditions=replace(self.conditions,**changes)
        transition=advance(self.state,event,self.conditions)
        self.state=transition.state  # Only the caller commits business state.
        self.intents.extend(transition.intents)
        return transition

    def start(self):
        return self.step(Control('start'))

    def arrival(self,site='A',**changes):
        values=dict(request_id=self.state.operations[-1].request_id,site=site,
                    operation_id=11 if site=='A' else 12,outcome='arrived',
                    pose_verified=True,reusable=site=='A')
        values.update(changes)
        return self.step(NavigationFact(**values))

    def check(self,classification='abnormal',**changes):
        site=self.state.operations[-1].site
        record=CheckRecord(f'window-{site}',7,site,f'indicator-{site}',1.2,1.6,3,classification)
        return self.step(WindowClosed(replace(record,**changes)),record_applicable=classification!='unknown')

    def proposal(self,action,reason='Controlled proposal'):
        return self.step(Proposal(self.state.decision,action,reason))

    def at_decision_a(self,classification='abnormal'):
        self.start(); self.arrival(); self.check(classification)

    def at_decision_b(self,classification='normal'):
        self.at_decision_a(); self.proposal('visit_b'); self.arrival('B'); self.check(classification)


class PolicyTests(unittest.TestCase):
    def test_normal_a_finishes_without_b_or_physical_verdict(self):
        flow=Flow(); flow.at_decision_a('normal'); result=flow.proposal('report_normal','Physical repair verified')
        self.assertEqual(result.state.phase,'completed')
        self.assertEqual(result.state.outcome,'normal_observed')
        self.assertEqual([i.site for i in flow.intents if i.kind=='navigate'],['A'])
        self.assertEqual(report(flow.state)['task_verdict'],'unassessed')
        self.assertEqual(report(flow.state)['native_cleanup'],'unknown')
        self.assertEqual(report(flow.state)['reason'],'A status observed normal')
        self.assertFalse(result.intents)
        with self.assertRaises(FrozenInstanceError):
            flow.state.phase='navigation_b'

    def test_abnormal_a_allows_one_b_preserves_b_pending_and_both_histories(self):
        for b_status in ('normal','abnormal'):
            with self.subTest(b=b_status):
                flow=Flow(); flow.at_decision_b(b_status); flow.proposal('report_recheck')
                self.assertEqual(flow.state.phase,'completed')
                self.assertEqual(flow.state.outcome,f'recheck_{b_status}')
                self.assertEqual([i.site for i in flow.intents if i.kind=='navigate'],['A','B'])
                self.assertEqual([c.classification for c in flow.state.checks],['abnormal',b_status])
                self.assertFalse(flow.state.operations[-1].reusable)
                self.assertEqual(flow.state.operations[-1].outcome,'arrived')
                result=flow.step(Proposal(DecisionKey('other',0,'B','other',7),'visit_b','late'))
                self.assertFalse(result.intents)
                self.assertEqual(result.state.phase,'completed')

    def test_unknown_a_or_b_never_starts_another_navigation(self):
        for site in ('A','B'):
            flow=Flow()
            if site=='A':
                flow.start(); flow.arrival()
            else:
                flow.at_decision_a(); flow.proposal('visit_b'); flow.arrival('B')
            flow.check('unknown')
            self.assertEqual(flow.state.phase,'needs_help')
            self.assertEqual(len([i for i in flow.intents if i.kind=='navigate']),1 if site=='A' else 2)
            self.assertEqual(flow.state.checks[-1].classification,'unknown')

    def test_a_must_release_and_actual_pose_must_be_confirmed_before_observe(self):
        flow=Flow(); flow.start()
        result=flow.arrival(reusable=False)
        self.assertEqual(result.state.phase,'navigation_a')
        self.assertFalse(result.intents)
        result=flow.arrival()
        self.assertEqual([i.kind for i in result.intents],['observe'])
        flow=Flow(); flow.start(); flow.arrival(pose_verified=False)
        self.assertEqual(flow.state.phase,'needs_help')
        self.assertFalse(any(i.kind=='observe' for i in flow.intents))

    def test_record_generation_site_target_and_identity_mismatch_block_b(self):
        for changes in ({'generation':8},{'generation':True},{'site':'B'},
                        {'target':'foreign-indicator'},{'reference':''}):
            with self.subTest(changes=changes):
                flow=Flow(); flow.start(); flow.arrival(); flow.check(**changes)
                self.assertEqual(flow.state.phase,'needs_help')
                self.assertFalse(flow.state.checks)
                self.assertEqual([i.site for i in flow.intents if i.kind=='navigate'],['A'])

    def test_duplicate_arrival_and_window_cannot_repeat_sampling_or_deciding(self):
        flow=Flow(); flow.start(); flow.arrival(); count=len(flow.intents)
        self.assertFalse(flow.arrival().intents)
        self.assertEqual(len(flow.intents),count)
        flow.check()
        self.assertFalse(flow.step(WindowClosed(flow.state.checks[-1])).intents)
        self.assertEqual(len([i for i in flow.intents if i.kind=='decide']),1)

    def test_old_released_a_duplicate_cannot_cancel_or_reopen_current_b(self):
        flow=Flow(); flow.at_decision_a(); original=flow.state.operations[0]
        flow.proposal('visit_b'); active=flow.state.operations[-1]
        result=flow.step(NavigationFact(original.request_id,'A',11,'arrived',True,True))
        self.assertEqual(result.state.phase,'navigation_b')
        self.assertEqual(result.state.operations[-1],active)
        self.assertFalse(result.intents)
        self.assertEqual(len([i for i in flow.intents if i.kind=='observe']),1)

    def test_camera_loss_latches_without_cancelling_independent_navigation(self):
        for site in ('A','B'):
            flow=Flow()
            if site=='A':
                flow.start()
            else:
                flow.at_decision_a(); flow.proposal('visit_b')
            request=flow.state.operations[-1].request_id
            flow.step(NavigationFact(request,site,11 if site=='A' else 12,'pending'))
            failure=flow.step(Control('tick'),source_valid=False,record_applicable=False)
            self.assertEqual(failure.state.phase,f'navigation_{site.lower()}')
            self.assertFalse(failure.intents)
            self.assertEqual(failure.state.operations[-1].request_id,request)
            flow.step(Control('tick'),source_valid=True)
            result=flow.arrival(site)
            self.assertEqual(result.state.phase,'needs_help')
            self.assertFalse(any(i.kind=='observe' for i in result.intents))
            self.assertEqual([i.site for i in flow.intents if i.kind=='navigate'],['A'] if site=='A' else ['A','B'])

    def test_camera_fault_before_acceptance_withdraws_handoff_without_resubmitting(self):
        flow=Flow(); flow.at_decision_a(); flow.proposal('visit_b')
        original=flow.state.operations[-1]
        result=flow.step(Control('tick'),source_valid=False)
        self.assertEqual(result.state.phase,'needs_help')
        self.assertEqual([(i.kind,i.request_id) for i in result.intents],
                         [('withdraw_submission',original.request_id),('cancel',original.request_id)])
        self.assertFalse(flow.step(Control('start'),source_valid=True).intents)
        self.assertIsNone(flow.state.operations[-1].operation_id)

    def test_explicit_stop_and_navigation_failure_cancel_exact_original_request(self):
        for stop in (True,False):
            flow=Flow(); flow.start(); request=flow.state.operations[-1].request_id
            flow.step(NavigationFact(request,'A',11,'pending'))
            result=flow.step(Control('stop' if stop else 'tick'),navigation_valid=stop)
            self.assertEqual(result.state.phase,'cancelled' if stop else 'needs_help')
            self.assertEqual([(i.kind,i.request_id) for i in result.intents],[('cancel',request)])
            self.assertFalse(flow.step(Control('stop')).intents)

    def test_camera_fault_during_model_wait_withdraws_basis_without_b(self):
        flow=Flow(); flow.at_decision_a(); key=flow.state.decision
        result=flow.step(Control('tick'),source_valid=False,record_applicable=False)
        self.assertEqual(result.state.phase,'needs_help')
        self.assertEqual(result.intents[0].kind,'withdraw')
        self.assertEqual(result.intents[0].decision,key)
        self.assertFalse(any(i.kind=='cancel' for i in result.intents))  # Released A.
        late=flow.step(Proposal(key,'visit_b','late answer'),source_valid=True,record_applicable=True)
        self.assertFalse(late.intents)
        self.assertEqual(len(flow.state.operations),1)

    def test_proposal_task_revision_generation_reference_and_branch_are_revalidated(self):
        mutations=({'task_id':'other'},{'revision':1},{'revision':False},
                   {'generation':8},{'generation':True},{'check_reference':'other'},{'site':'B'})
        for changes in mutations:
            with self.subTest(changes=changes):
                flow=Flow(); flow.at_decision_a()
                result=flow.step(Proposal(replace(flow.state.decision,**changes),'visit_b','foreign'))
                self.assertEqual(result.state.phase,'needs_help')
                self.assertEqual(len(flow.state.operations),1)
        for status,action in (('normal','visit_b'),('abnormal','report_normal')):
            flow=Flow(); flow.at_decision_a(status); flow.proposal(action)
            self.assertEqual(flow.state.phase,'needs_help')
        flow=Flow(); flow.at_decision_b(); flow.proposal('visit_b')
        self.assertEqual(flow.state.phase,'needs_help')
        self.assertEqual(len(flow.state.operations),2)

    def test_b_admission_requires_current_readiness_and_basis_even_after_good_answer(self):
        for changes in ({'can_submit':False},{'navigation_valid':False},
                        {'record_applicable':False},{'generation':8}):
            flow=Flow(); flow.at_decision_a()
            result=flow.step(Proposal(flow.state.decision,'visit_b','try'),**changes)
            self.assertEqual(result.state.phase,'needs_help')
            self.assertEqual(len(flow.state.operations),1)

    def test_task_decision_and_operation_deadlines_do_not_restart_or_retry(self):
        flow=Flow(); flow.start(); deadline=flow.state.operations[-1].deadline
        flow.step(NavigationFact(flow.state.operations[-1].request_id,'A',11,'pending'))
        flow.step(Control('tick'),source_valid=False,now=deadline-.01)
        flow.step(Control('tick'),source_valid=True,now=deadline)
        self.assertEqual(flow.state.phase,'needs_help')
        self.assertEqual(len(flow.state.operations),1)
        flow=Flow(); flow.at_decision_a(); key=flow.state.decision; deadline=flow.state.decision_deadline
        result=flow.step(Proposal(key,'visit_b','too late'),now=deadline)
        self.assertEqual(result.state.phase,'needs_help')
        flow=Flow(); flow.start(); result=flow.step(Control('tick'),now=flow.state.deadline)
        self.assertEqual(result.state.phase,'needs_help')
        self.assertTrue(any(i.kind=='cancel' for i in result.intents))
        flow=Flow(); flow.start(); flow.step(Control('tick'),now=0.)
        self.assertEqual(flow.state.phase,'needs_help')

    def test_first_turn_before_started_at_cannot_extend_original_budget(self):
        state=new_task('inspection',started_at=10.)
        result=advance(state,Control('start'),Conditions(9.,7,True,True,True))
        self.assertEqual(result.state.phase,'needs_help')
        self.assertFalse(result.intents)
        self.assertFalse(result.state.operations)

    def test_progress_cannot_erase_arrival_and_unknown_current_execution_requires_help(self):
        flow=Flow(); flow.at_decision_b(); original=flow.state.operations[-1]
        result=flow.step(NavigationFact(original.request_id,'B',12,'pending'))
        self.assertEqual(result.state.phase,'decision_b')
        self.assertEqual(result.state.operations[-1].outcome,'arrived')
        self.assertFalse(result.intents)
        result=flow.step(NavigationFact(original.request_id,'B',None,'unknown'))
        self.assertEqual(result.state.phase,'needs_help')
        self.assertEqual(result.state.operations[-1].operation_id,12)
        self.assertEqual(result.state.operations[-1].outcome,'arrived')
        self.assertEqual(result.intents[-1].request_id,original.request_id)
        flow=Flow(); flow.at_decision_b(); flow.proposal('report_recheck')
        original=flow.state.operations[-1]
        result=flow.step(NavigationFact(original.request_id,'B',12,'pending'))
        self.assertEqual(result.state.phase,'completed')
        self.assertEqual(result.state.operations[-1].outcome,'arrived')
        self.assertFalse(result.intents)

    def test_ambiguous_or_foreign_execution_cannot_retry_or_erase_original_identity(self):
        for changed in ({'operation_id':None,'outcome':'unknown'},
                        {'request_id':'foreign'}, {'operation_id':True}, {'site':'B'}):
            flow=Flow(); flow.start(); original=flow.state.operations[-1].request_id
            fact=NavigationFact(original,'A',11,'pending')
            result=flow.step(replace(fact,**changed))
            self.assertEqual(result.state.phase,'needs_help')
            self.assertEqual(result.state.operations[-1].request_id,original)
            self.assertEqual(len(flow.state.operations),1)
        flow=Flow(); flow.start()
        flow.step(NavigationFact(flow.state.operations[-1].request_id,'A',11,'pending'))
        flow.arrival(operation_id=99)
        self.assertEqual(flow.state.operations[-1].operation_id,11)
        self.assertEqual(flow.state.phase,'needs_help')

    def test_late_execution_effect_is_retained_after_stop_without_restarting_business(self):
        flow=Flow(); flow.start(); request=flow.state.operations[-1].request_id
        flow.step(Control('stop'))
        result=flow.step(NavigationFact(request,'A',17,'arrived',True,True))
        self.assertEqual(result.state.phase,'cancelled')
        self.assertEqual(result.state.operations[-1].operation_id,17)
        self.assertTrue(result.state.operations[-1].reusable)
        self.assertFalse(result.intents)
        self.assertFalse(flow.step(Control('start')).intents)

    def test_goal_change_and_missing_initial_conditions_do_not_reset_the_task(self):
        flow=Flow(); flow.at_decision_a(); key=flow.state.decision
        result=flow.step(Control('goal_changed'))
        self.assertEqual(result.state.phase,'needs_help')
        self.assertEqual(result.intents[0].decision,key)
        self.assertEqual(result.state.task_id,'inspection')
        for changes in ({'source_valid':False},{'can_submit':False},{'navigation_valid':False}):
            flow=Flow(); result=flow.step(Control('start'),**changes)
            self.assertEqual(result.state.phase,'needs_help')
            self.assertFalse(result.state.operations)
        with self.assertRaises(ValueError):
            Conditions(True,7,True,True,True)

    def test_real_source_history_stays_usable_after_ten_seconds_and_forged_copy_does_not(self):
        clock=Clock(); source=InspectionSource(7,clock=clock)
        source.health(7,0.); source.open_window('A','indicator-A')
        for seq in range(3):
            clock.value=(seq+1)*.2; source.health(7,clock.value)
            source.ingest(Frame(7,seq,'A','indicator-A',clock.value,clock.value,SITES['A'],bytes(640*480*3)))
            reference=source.events.take()[2].reference; reader=source.borrow(reference)
            source.record(reader,'normal'); reader.release()
        for i in range(1,6):
            clock.value=.6+i*.88; self.assertTrue(source.health(7,clock.value))
        record=source.finish_window()
        flow=Flow(); flow.start(); flow.arrival()
        flow.step(WindowClosed(record),now=5.,record_applicable=source.applicable(record))
        for i in range(1,21):
            clock.value=5.+i*.5; self.assertTrue(source.health(7,clock.value))
            flow.step(Control('tick'),now=clock.value,record_applicable=source.applicable(record))
        self.assertEqual(flow.state.phase,'decision_a')
        flow.step(Proposal(flow.state.decision,'report_normal','Old window, current source'),
                  now=15.1,record_applicable=source.applicable(record))
        self.assertEqual(flow.state.phase,'completed')
        self.assertIs(flow.state.checks[0],record)
        forged=replace(record); self.assertFalse(source.applicable(forged))
        flow=Flow(); flow.start(); flow.arrival()
        flow.step(WindowClosed(forged),now=5.,record_applicable=source.applicable(forged))
        self.assertEqual(flow.state.phase,'needs_help')
        self.assertFalse(flow.state.checks)
        source.close()


class OwnedHandoffTests(unittest.TestCase):
    def test_claimed_submission_survives_withdrawal_as_original_possible_effect(self):
        flow=Flow(); flow.at_decision_a(); flow.proposal('visit_b')
        original=flow.state.operations[-1]
        entered=threading.Event(); release=threading.Event(); submissions=[]; cancellations=[]
        coordinator=Coordinator('inspection',lambda:False,1)
        class Io:
            def submit(self,request):
                entered.set()
                if not release.wait(2):
                    raise AssertionError('claimed submit gate not released')
                submissions.append(request)  # Claim may already have an effect despite withdrawal.
                return NavigationFact(request,'B',12,'pending')
            def cancel(self,request):
                cancellations.append(request)
                return {'request_id':request,'closure':'unknown'}
        owner=Owner(coordinator.exchange,'io',Io); owner.start()
        try:
            call=coordinator.begin('io','submit',(original.request_id,),{},deadline=time.monotonic()+2,
                                   association={'request_id':original.request_id})
            self.assertTrue(entered.wait(1))
            intents=flow.step(Control('tick'),source_valid=False).intents
            coordinator.exchange.withdraw('io',call)
            release.set()
            with coordinator.exchange.condition:
                self.assertTrue(coordinator.exchange.condition.wait_for(lambda:call.state=='completed',timeout=1))
            collected=coordinator.poll()['io']
            self.assertTrue(collected.started)
            self.assertTrue(collected.withdrawn)
            flow.step(collected.value,source_valid=False)
            self.assertEqual(flow.state.phase,'needs_help')
            self.assertEqual(flow.state.operations[-1].operation_id,12)
            cancel=next(i for i in intents if i.kind=='cancel')
            coordinator.call('io','cancel',(cancel.request_id,),{},cleanup=True,deadline=time.monotonic()+1)
            self.assertEqual(submissions,[original.request_id])
            self.assertEqual(cancellations,[original.request_id])
            self.assertFalse(flow.step(Control('start'),source_valid=True).intents)
        finally:
            release.set()
            self.assertTrue(owner.finish(time.monotonic()+2)['thread_stopped'])

    def test_camera_fault_before_io_claim_has_zero_submissions_and_preserves_original_id(self):
        flow=Flow(); flow.at_decision_a(); flow.proposal('visit_b')
        original=flow.state.operations[-1]
        entered=threading.Event(); release=threading.Event(); submissions=[]
        coordinator=Coordinator('inspection',lambda:False,1)
        class Io:
            def submit(self,request):
                submissions.append(request)
        def factory():
            entered.set()
            if not release.wait(2):
                raise AssertionError('preparation gate not released')
            return Io()
        owner=Owner(coordinator.exchange,'io',factory); owner.start()
        try:
            self.assertTrue(entered.wait(1))
            call=coordinator.begin('io','submit',(original.request_id,),{},deadline=time.monotonic()+2,
                                   association={'request_id':original.request_id})
            result=flow.step(Control('tick'),source_valid=False)
            intent=next(i for i in result.intents if i.kind=='withdraw_submission')
            self.assertEqual(intent.request_id,call.association['request_id'])
            coordinator.exchange.withdraw('io',call)
            release.set()
            collected=coordinator.poll()['io']
            self.assertFalse(collected.started)
            self.assertIsInstance(collected.error,InterruptedError)
            self.assertEqual(flow.state.operations[-1].request_id,original.request_id)
            self.assertFalse(submissions)
        finally:
            release.set()
            self.assertTrue(owner.finish(time.monotonic()+2)['thread_stopped'])

    def test_blocked_model_does_not_drop_original_io_or_prevent_original_cancel(self):
        flow=Flow(); flow.at_decision_b('abnormal')
        key=flow.state.decision; original=flow.state.operations[-1]
        inbox=EventInbox(); entered=threading.Event(); release=threading.Event(); io_release=threading.Event()
        cancellations=[]; effects=[]
        def event(kind,value):
            if kind=='invalidated':
                effects.extend(flow.step(Control('tick'),source_valid=False,record_applicable=False).intents)
        coordinator=Coordinator('inspection',lambda:False,1,events=inbox,on_event=event)
        class Model:
            def decide(self):
                entered.set()
                if not release.wait(3):
                    raise AssertionError('model gate not released')
                return Proposal(key,'report_recheck','late result')
        class Io:
            def status(self,request):
                if not io_release.wait(3):
                    raise AssertionError('I/O gate not released')
                return NavigationFact(request,'B',12,'arrived',True,False)
            def cancel(self,request):
                cancellations.append(request)
                return {'request_id':request,'closure':'unknown'}
        owners=[Owner(coordinator.exchange,'decision',Model),Owner(coordinator.exchange,'io',Io)]
        for owner in owners:
            owner.start()
        try:
            deadline=time.monotonic()+3
            decision=coordinator.begin('decision','decide',(),{},deadline=deadline,
                                       association={'check_reference':key.check_reference})
            self.assertTrue(entered.wait(1))
            io=coordinator.begin('io','status',(original.request_id,),{},deadline=deadline,
                                 association={'request_id':original.request_id})
            inbox.invalidate('inspection path lost'); coordinator.poll()
            self.assertTrue(decision.withdrawn)
            self.assertFalse(io.withdrawn)
            self.assertEqual(flow.state.phase,'needs_help')
            io_release.set()
            with coordinator.exchange.condition:
                self.assertTrue(coordinator.exchange.condition.wait_for(lambda:io.state=='completed',timeout=1))
            completed=coordinator.poll()['io']
            flow.step(completed.value,source_valid=False,record_applicable=False)
            self.assertEqual(flow.state.operations[-1].operation_id,12)
            cancel=next(intent for intent in effects if intent.kind=='cancel')
            result=coordinator.call('io','cancel',(cancel.request_id,),{},cleanup=True,deadline=time.monotonic()+1)
            self.assertEqual(result['closure'],'unknown')
            self.assertEqual(cancellations,[original.request_id])
            self.assertFalse(release.is_set())
            release.set()
            with coordinator.exchange.condition:
                self.assertTrue(coordinator.exchange.condition.wait_for(lambda:decision.state=='completed',timeout=1))
            late=coordinator.poll()['decision']
            self.assertTrue(late.withdrawn)
            self.assertFalse(flow.step(late.value,source_valid=True,record_applicable=True).intents)
            self.assertEqual([c.classification for c in flow.state.checks],['abnormal','abnormal'])
            self.assertEqual(len(flow.state.operations),2)
        finally:
            release.set(); io_release.set()
            for owner in owners:
                self.assertTrue(owner.finish(time.monotonic()+2)['thread_stopped'])


if __name__=='__main__':
    unittest.main()
