"""Private, local navigation proposal exchange; not a provider/control API."""
from contextlib import contextmanager
import json
import os
import stat
import uuid

from .navigation import ACTIONS, GOAL, SITES, REFERENCE_FIELDS, finite, measurements
from .navigation_checkpoint import CheckpointNavigationTask, IDENTITY_FIELDS

LIMIT = 65536
PHASES = tuple(ACTIONS)


@contextmanager
def directory(name, *, parent=None):
    descriptor = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    try:
        yield descriptor
    finally:
        os.close(descriptor)


def read_json(parent, name):
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    with os.fdopen(descriptor, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError('relay message must be a regular file')
        data = stream.read(LIMIT + 1)
    if len(data) > LIMIT:
        raise ValueError('relay message exceeds the local limit')
    return json.loads(data)


def write_json(parent, name, value):
    data = (json.dumps(value, allow_nan=False) + '\n').encode()
    if len(data) > LIMIT:
        raise ValueError('relay message exceeds the local limit')
    temporary = '.message-' + uuid.uuid4().hex
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
        os.replace(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
    finally:
        try:
            os.unlink(temporary, dir_fd=parent)
        except FileNotFoundError:
            pass


def cancelled(parent):
    try:
        os.stat('cancelled', dir_fd=parent, follow_symlinks=False)
        return True
    except FileNotFoundError:
        return False


def proposal_request(data, phase, model, *, task='fixed'):
    """Reconstruct only this application's permitted inputs before a host call."""
    nonce, budget, inputs = data['nonce'], data['remaining_seconds'], data['inputs']
    if (not isinstance(nonce, str) or len(nonce) != 32
            or any(c not in '0123456789abcdef' for c in nonce)
            or not finite(budget) or not 0 < budget <= 30 or not isinstance(inputs, dict)):
        raise ValueError('invalid local proposal identity or budget')
    if task not in ('fixed', 'checkpoint') or phase not in PHASES:
        raise ValueError('unsupported host navigation task or phase')
    goal = GOAL if task == 'fixed' else CheckpointNavigationTask.goal
    if (inputs.get('phase') != phase or inputs.get('model_requested') != model
            or inputs.get('goal') != goal or inputs.get('registered_sites') != SITES
            or not isinstance(inputs.get('task_id'), str) or not 0 < len(inputs['task_id']) <= 128):
        raise ValueError('local proposal does not match the declared navigation task/model')
    observation = inputs['measurement']
    reference = observation['reference']
    observation = measurements({**observation, 'valid': True, 'epoch': reference['epoch'],
                               'map_id': reference['map_id'], 'frame': reference['frame']})
    context_reference = {key: inputs['observation_reference'][key] for key in REFERENCE_FIELDS}
    if (type(context_reference['epoch']) is not int or context_reference != observation['reference']):
        raise ValueError('local proposal observation reference changed')
    allowed = list(ACTIONS[phase])
    instruction = None
    if task == 'checkpoint' and phase == 'after_a':
        command = inputs.get('checkpoint_instruction')
        if (not isinstance(command, dict) or command.get('task_id') != inputs['task_id']
                or not isinstance(command.get('checkpoint_id'), str) or not 0 < len(command['checkpoint_id']) <= 128
                or type(command.get('epoch')) is not int
                or any(command.get(key) != context_reference[key] for key in ('session_id','epoch','map_id','frame'))
                or command.get('action') not in ('continue_b', 'finish_at_a')):
            raise ValueError('host checkpoint instruction identity or action changed')
        instruction = {key: command[key] for key in (*IDENTITY_FIELDS, 'action')}
        allowed = ['visit_b' if instruction['action'] == 'continue_b' else 'finish_at_a', 'help']
    if inputs.get('allowed_actions') != allowed:
        raise ValueError('host proposal action set changed')
    context = dict(task_id=inputs['task_id'], phase=phase, goal=goal,
                   registered_sites=SITES, allowed_actions=allowed,
                   observation_reference=context_reference)
    if instruction is not None:
        context['checkpoint_instruction'] = instruction
    return nonce, budget, context, observation
