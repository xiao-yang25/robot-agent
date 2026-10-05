"""Bounded text proposal backend; measurements only, no robot tools."""
import json

from .codex_decision import CodexDecision
from ._codex_proposal import run_proposal


class NavigationCodexDecision(CodexDecision):
    """Reuse proposal process ownership, with navigation-specific input/schema."""
    def decide(self, context, observation, deadline, stop_requested):
        self.count += 1
        run = self.output / f'decision-{self.count}'
        run.mkdir()
        inputs = {**context, 'measurement': observation, 'model_requested': self.model,
                  'reasoning_requested': 'high', 'codex_version': self.version}
        (run / 'input.json').write_text(json.dumps(inputs, indent=2, allow_nan=False) + '\n')
        prompt = (
            'You are only a decision backend for a bounded navigation simulation application. '
            'Return one proposal, without tools, commands, file reads, browsing or delegation. '
            'The application owns task state and all Harness calls; Nav2 owns navigation. '
            'Choose only an allowed action. At prepare choose visit_a if the supplied valid '
            'map pose/sensor health and registered sites are compatible with the goal, otherwise help. '
            'After A choose visit_b only if fresh measured map pose confirms A within 0.3m. '
            'When checkpoint_instruction is present, follow that one business instruction: '
            'continue_b permits visit_b; finish_at_a permits finish_at_a. '
            'For this checkpoint choose help if uncertain about the instruction or measurements. '
            'Echo its checkpoint_id in your answer; never replace or reinterpret the instruction. '
            'At after_revision follow revision_instruction: only redirect_b permits visit_b. '
            'A has been cancelled and released; do not require arrival at A. Echo revision_id. '
            'At after_failure, failure_context describes an accepted native failure of A '
            'whose resources the Owner confirmed released. This does not prove physical unreachability. '
            'Choose visit_b only if the business goal permits the registered backup and '
            'fresh map feedback is valid, otherwise help. Do not require arrival at failed A. '
            'Echo failure_context recovery_id, request_id, operation_id and goal_id exactly. '
            'Never retry A or recover again after B. '
            'At final when completion_site is supplied use that site (A or B) as the measured target. '
            'For the fixed task or checkpoint without completion_site use B. '
            'At final choose observed_complete only if fresh map pose confirms that final target within 0.3m; '
            'use not_met for contradictory feedback or help for uncertainty. '
            'You have no camera, obstacle geometry or physical-evaluator truth: do not invent it. '
            'An observation assessment does not prove task success, robot stop or resource settlement. '
            'Preserve task_id, phase and every observation_reference field exactly.\n'
            + json.dumps(inputs, allow_nan=False))
        (run / 'prompt.txt').write_text(prompt + '\n')
        reference_properties = {key: {'type': 'integer' if key == 'epoch' else 'string'}
                                for key in context['observation_reference']}
        properties = {'task_id': {'type': 'string'}, 'phase': {'type': 'string'},
            'observation_reference': {'type': 'object', 'properties': reference_properties,
                'required': list(reference_properties), 'additionalProperties': False},
            'action': {'type': 'string', 'enum': context['allowed_actions']},
            'reason': {'type': 'string'}}
        if 'checkpoint_instruction' in context:
            properties['checkpoint_id'] = {'type': 'string'}
        if 'revision_instruction' in context:
            properties['revision_id'] = {'type': 'string'}
        if 'failure_context' in context:
            for key in ('recovery_id', 'request_id', 'operation_id', 'goal_id'):
                properties[key] = {'type': 'integer' if key == 'operation_id' else 'string'}
        schema = {'type': 'object', 'properties': properties, 'required': list(properties),
                  'additionalProperties': False}
        (run / 'schema.json').write_text(json.dumps(schema) + '\n')
        return run_proposal(self.executable, self.model, run, prompt, deadline, stop_requested)
