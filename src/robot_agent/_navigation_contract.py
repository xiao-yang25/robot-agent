"""Private navigation fact validation shared by fixed tasks and inspection."""
from copy import deepcopy
import math

PROFILE = 'scoped-two-context-nav2-shim-v1'
MAP = 'turtlebot3-world-v1'
SITES = {'A': [0.7, -0.5, 0.0], 'B': [-1.5, -0.5, 0.0]}
REFERENCE_FIELDS = ('session_id', 'observation_id', 'epoch', 'map_id', 'frame')


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def measurements(raw, *, expected_map_id=MAP):
    """Expose only the public map measurement whitelist, never simulator truth."""
    ref = raw.get('reference', {})
    if (raw.get('valid') is not True or type(raw.get('epoch')) is not int or raw['epoch'] < 0
            or raw.get('map_id') != expected_map_id or raw.get('frame') != 'map'
            or not isinstance(ref, dict) or type(ref.get('epoch')) is not int
            or ref['epoch'] != raw['epoch'] or ref.get('map_id') != expected_map_id or ref.get('frame') != 'map'
            or any(not isinstance(ref.get(k), str) or not 0 < len(ref[k]) <= 128
                   for k in ('session_id', 'observation_id'))):
        raise ValueError('invalid navigation observation identity')
    pose, stamp, health = raw.get('pose'), raw.get('sample_sim_seconds'), raw.get('sensor_health', {})
    if (not isinstance(pose, list) or len(pose) != 2 or not all(finite(v) for v in pose)
            or not finite(stamp) or stamp <= 0 or not isinstance(health, dict)
            or health.get('localization') is not True or not finite(health.get('clock_age'))
            or not 0 <= health['clock_age'] <= 1):
        raise ValueError('invalid navigation measurement')
    streams = health.get('streams')
    if (not isinstance(streams, list) or len(streams) != 2 or any(
            not isinstance(row, (tuple, list)) or len(row) != 3 or not all(finite(v) for v in row)
            or row[0] <= 0 or not all(0 <= age <= 1 for age in row[1:]) for row in streams)):
        raise ValueError('invalid navigation sensor health')
    return {'reference': {key: ref[key] for key in REFERENCE_FIELDS},
            'pose': list(pose), 'sample_sim_seconds': stamp,
            'sensor_health': {'localization': True, 'clock_age': health['clock_age'],
                              'streams': deepcopy(streams)}}


class NavigationContract:
    profile = PROFILE
    expected_map_id = MAP

    def __init__(self):
        self.realm = self.binding = None
        self.maximum_deadline_ms = 147000

    def normalize_observation(self, raw):
        observation = measurements(raw, expected_map_id=self.expected_map_id)
        realm = tuple(observation['reference'][key] for key in ('session_id', 'epoch', 'map_id', 'frame'))
        if self.realm is not None and realm != self.realm:
            raise ValueError('navigation session/map/epoch changed')
        self.realm = realm
        return observation

    def validate_capabilities(self, cap, *, require_available):
        if (cap.get('skill') != 'navigation.visit_site' or cap.get('profile') != self.profile
                or cap.get('map_id') != self.expected_map_id or cap.get('frame') != 'map'
                or not isinstance(cap.get('sites'), list) or any(site not in cap['sites'] for site in SITES)
                or type(cap.get('maximum_deadline_ms')) is not int
                or not 0 < cap['maximum_deadline_ms'] <= 147000
                or (require_available and cap.get('available') is not True)):
            raise ValueError('qualified navigation capability unavailable')
        self.maximum_deadline_ms = cap['maximum_deadline_ms']
        return cap

    def associated_receipt(self, record, request, site, operation_id, reference):
        if (record.get('request_id') != request or record.get('site') != site
                or record.get('skill') != 'navigation.visit_site'
                or type(record.get('operation_id')) is not int or record['operation_id'] != operation_id
                or record.get('observation_reference') != reference):
            raise ValueError('navigation operation association changed')
        receipt = record.get('receipt', {})
        authority = receipt.get('authority', {})
        if type(authority.get('operation_id')) is not int or authority['operation_id'] != operation_id:
            raise ValueError('navigation receipt authority mismatch')
        binding = authority.get('binding')
        if (not isinstance(binding, dict) or binding.get('provider') != 'scoped-nav2'
                or binding.get('domain') != 'exclusive-waffle-drive'
                or any(type(binding.get(key)) is not int or binding[key] < 1 for key in ('revision', 'generation'))
                or (self.binding is not None and binding != self.binding)):
            raise ValueError('navigation authority binding changed')
        self.binding = deepcopy(binding)
        return receipt

    def validate_record(self, record, request, site, operation_id, reference):
        receipt = self.associated_receipt(record, request, site, operation_id, reference)
        if receipt.get('authority_disposition') == 'revoked' or receipt.get('native_outcome') in ('failed', 'cancelled'):
            raise ValueError('navigation operation failed or revoked')
        payload = record.get('result')
        if payload is None:
            return False
        goal_id = record.get('goal_id')
        if (not isinstance(payload, dict) or not isinstance(goal_id, str) or len(goal_id) != 32
                or any(c not in '0123456789abcdef' for c in goal_id)
                or receipt.get('native_identity') != goal_id or payload.get('goal_id') != goal_id
                or payload.get('stage') != site or receipt.get('result_reference') != request
                or receipt.get('native_acceptance') != 'accepted' or receipt.get('native_outcome') != 'succeeded'
                or receipt.get('output') != 'accepted' or record.get('target') != SITES[site]):
            raise ValueError('navigation result/native identity incomplete or mismatched')
        if site == 'A':
            return (record.get('state') == 'finished' and receipt.get('settlement') == 'settled'
                    and receipt.get('authority_disposition') == 'released')
        if (receipt.get('settlement') != 'pending' or receipt.get('authority_disposition') != 'current'):
            raise ValueError('unexpected final-context settlement')
        return True
