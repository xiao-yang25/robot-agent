"""One evaluator for the bounded simulated handoff; truth stays outside Agent input."""

import argparse
import json
import math
from pathlib import Path
from importlib.resources import files

import numpy as np

def load_profile():
    return json.loads(files('robot_agent').joinpath('handoff_profile.json').read_text())


def vector(value, size):
    result = np.asarray(value, dtype=float)
    if result.shape != (size,) or not np.isfinite(result).all():
        raise ValueError('missing or invalid numeric measurement')
    return result


def rotation(value):
    matrix = vector(value, 9).reshape(3, 3)
    if not np.allclose(matrix.T @ matrix, np.eye(3), atol=1e-6, rtol=0) or abs(np.linalg.det(matrix) - 1) > 1e-6:
        raise ValueError('invalid measured rotation')
    return matrix


def derive_frames(rows, profile):
    """Reconstruct kinematic poses from recorded qpos, without stepping dynamics."""
    from dm_control import mujoco
    from gym_aloha.constants import ASSETS_DIR
    physics = mujoco.Physics.from_xml_path(str(ASSETS_DIR / 'bimanual_viperx_transfer_cube.xml'))
    try:
        cube = physics.model.name2id('red_box', 'geom')
        hand = physics.model.name2id('vx300s_left/gripper_link', 'body')
        table = physics.model.name2id('table', 'geom')
        if not np.allclose(physics.model.geom_size[cube], profile['cube_half_size_m'], rtol=0, atol=1e-12):
            raise ValueError('model cube geometry differs from task profile')
        mesh = int(physics.model.geom_dataid[table])
        start, count = int(physics.model.mesh_vertadr[mesh]), int(physics.model.mesh_vertnum[mesh])
        frames = []
        for row in rows:
            if row.get('event') != 'step':
                continue
            physics.data.qpos[:] = vector(row.get('qpos'), physics.model.nq)
            physics.forward()
            hand_rotation = physics.data.xmat[hand].reshape(3, 3)
            cube_rotation = physics.data.geom_xmat[cube].reshape(3, 3)
            cube_position = physics.data.geom_xpos[cube]
            table_rotation = physics.data.geom_xmat[table].reshape(3, 3)
            vertices = physics.model.mesh_vert[start:start + count] @ table_rotation.T + physics.data.geom_xpos[table]
            table_top = float(vertices[:, 2].max())
            cube_bottom = float(cube_position[2] - np.abs(cube_rotation[2]) @ physics.model.geom_size[cube])
            frames.append({key: row[key] for key in ('step', 'phase', 'sim_seconds', 'action', 'contacts')})
            frames[-1].update(
                relative_position=(hand_rotation.T @ (cube_position - physics.data.xpos[hand])).tolist(),
                relative_rotation=(hand_rotation.T @ cube_rotation).ravel().tolist(),
                table_clearance_m=cube_bottom - table_top)
        return frames
    finally:
        physics.free()


def evaluate(frames, profile):
    verdict = {'profile': profile['id'], 'verdict': 'unknown', 'reason': None,
               'simulation_only': True, 'metrics': {}}
    try:
        end = profile['policy_steps'] + profile['hold_steps']
        if len(frames) != end:
            raise ValueError('missing or extra execution samples')
        for index, frame in enumerate(frames):
            if type(frame.get('step')) is not int or frame['step'] != index + 1:
                raise ValueError('nonconsecutive execution samples')
            expected_phase = 'policy' if index < profile['policy_steps'] else 'hold'
            if frame.get('phase') != expected_phase:
                raise ValueError('execution phase does not match profile')
            vector(frame.get('action'), 14)
            stamp = float(frame['sim_seconds'])
            if not math.isfinite(stamp):
                raise ValueError('nonfinite simulation time')
            if index and abs(stamp - float(frames[index - 1]['sim_seconds']) - profile['control_dt_seconds']) > 1e-9:
                raise ValueError('simulation time did not advance by one control step')
        window = frames[profile['policy_steps'] - 1:]
        position = vector(window[0].get('relative_position'), 3)
        reference_rotation = rotation(window[0].get('relative_rotation'))
        reference_action = vector(window[0]['action'], 14)
        translations, angles, clearances = [], [], []
        contact_ok = True
        fingers = set(profile['left_fingers'])
        for index, frame in enumerate(window):
            if index and not np.array_equal(vector(frame['action'], 14), reference_action):
                raise ValueError('hold did not repeat the final target')
            pairs = frame.get('contacts')
            if not isinstance(pairs, list) or any(not isinstance(p, list) or len(p) != 2 or
                                                 any(not isinstance(v, str) for v in p) for p in pairs):
                raise ValueError('missing or invalid contacts')
            touched = set()
            for pair in pairs:
                if 'red_box' in pair:
                    touched.update(pair)
            touched.discard('red_box')
            contact_ok = contact_ok and touched == fingers
            translations.append(float(np.linalg.norm(vector(frame.get('relative_position'), 3) - position)))
            matrix = rotation(frame.get('relative_rotation'))
            cosine = float((np.trace(reference_rotation.T @ matrix) - 1) / 2)
            angles.append(math.degrees(math.acos(max(-1., min(1., cosine)))))
            clearance = float(frame['table_clearance_m'])
            if not math.isfinite(clearance):
                raise ValueError('invalid table clearance')
            clearances.append(clearance)
        verdict['metrics'] = {'window_steps': len(window) - 1,
                              'window_sim_seconds': window[-1]['sim_seconds'] - window[0]['sim_seconds'],
                              'exclusive_bilateral_contacts_all_samples': contact_ok,
                              'maximum_relative_translation_m': max(translations),
                              'maximum_relative_rotation_degrees': max(angles),
                              'minimum_table_clearance_m': min(clearances)}
        failures = []
        if not contact_ok:
            failures.append('cube_not_exclusively_held_by_both_left_fingers')
        if max(translations) > profile['relative_translation_limit_m']:
            failures.append('relative_translation_exceeded')
        if max(angles) > profile['relative_rotation_limit_degrees']:
            failures.append('relative_rotation_exceeded')
        if min(clearances) < profile['table_clearance_min_m']:
            failures.append('table_clearance_insufficient')
        verdict.update(verdict='failed' if failures else 'succeeded', reason=failures or 'bounded_handoff_hold_observed')
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        verdict['reason'] = f'incomplete_or_invalid_evidence: {error}'
    return verdict


def evaluate_run(run, trace_name='trace.jsonl'):
    """Evaluate a recorded trace once, independently of the task application."""
    run = Path(run)
    profile = load_profile()
    try:
        with (run / trace_name).open() as stream:
            rows = [json.loads(line) for line in stream]
        if any(not isinstance(row, dict) for row in rows):
            raise ValueError('trace record is not an object')
        frames = derive_frames(rows, profile)
        verdict = evaluate(frames, profile)
    except (OSError, ImportError, KeyError, TypeError, ValueError, OverflowError) as error:
        verdict = {'profile': profile['id'], 'verdict': 'unknown',
                   'reason': f'incomplete_or_invalid_evidence: {error}', 'simulation_only': True, 'metrics': {}}
    verdict.update(run=str(run), trace_name=trace_name, consumed_profile=profile,
                   pose_source='Recorded qpos plus pinned model forward kinematics; no dynamics step')
    return verdict


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True,
                        help='episode trace directory, not the task report directory')
    parser.add_argument('--output', type=Path, required=True,
                        help='new report path; existing output is never overwritten')
    parser.add_argument('--trace-name', default='trace.jsonl')
    args = parser.parse_args()
    try:
        with args.output.open('x') as stream:
            verdict = evaluate_run(args.run, args.trace_name)
            stream.write(json.dumps(verdict, indent=2, allow_nan=False) + '\n')
    except OSError as error:
        parser.error(f'cannot create evaluation report: {error}')
    print(json.dumps(verdict, indent=2))
    return {'succeeded': 0, 'failed': 1, 'unknown': 2}[verdict['verdict']]


if __name__ == '__main__':
    raise SystemExit(main())
