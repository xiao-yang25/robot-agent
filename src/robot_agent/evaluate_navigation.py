"""Offline fixed A->B goal evaluation. Simulator truth never drives decisions."""
import argparse
from importlib.resources import files
import json
import math
from pathlib import Path
import re

from .navigation import GOAL


def load_profile():
    return json.loads(files('robot_agent').joinpath('navigation_profile.json').read_text())


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def finite(value):
    require(type(value) in (int,float) and math.isfinite(value), 'missing/nonfinite number')
    return value


def vector(value, size):
    require(isinstance(value,list) and len(value)==size, 'missing measurement vector')
    return [finite(item) for item in value]


def identity(value):
    require(isinstance(value,str) and re.fullmatch('[0-9a-f]{32}',value) is not None
            and value!='0'*32, 'missing/invalid identity')
    return value


def recorded_facts(value):
    """Keep diagnostic facts JSON-safe; validation still uses original inputs."""
    if isinstance(value,dict):
        return {key:recorded_facts(item) for key,item in value.items()}
    if isinstance(value,list):
        return [recorded_facts(item) for item in value]
    if isinstance(value,float) and not math.isfinite(value):
        return None
    return value


def object_file(path):
    value=json.loads(path.read_text())
    require(isinstance(value,dict), 'record is not an object')
    return value


def rows_file(path):
    rows=[json.loads(line) for line in path.read_text().splitlines()]
    require(all(isinstance(row,dict) for row in rows), 'event is not an object')
    return rows


def unique(rows,event,stage=None):
    found=[row for row in rows if row.get('event')==event
           and (stage is None or row.get('stage')==stage)]
    require(len(found)==1, f'missing/ambiguous {event} {stage}')
    finite(found[0]['steady'])
    return found[0]


def check_sample(sample,trigger,run,profile):
    require(sample['run_id']==run['run_id'] and sample['container_name']==run['container_name']
            and sample['model']==profile['model'], 'foreign sample')
    start,end,t=map(finite,(sample['started'],sample['finished'],sample['trigger']))
    require(sample['event']==trigger['event'] and t==finite(trigger['steady'])
            and t<=start<=end<=t+profile['trigger_window_seconds']
            and end-start<=profile['query_limit_seconds'], 'invalid/late query interval')
    return vector(sample['xyz_rpy'],6)


def check_operation(operation,stage,task_id,events,profile,realm):
    request=task_id+('-prepare' if stage=='A' else '-after_a')
    require(operation['skill']=='navigation.visit_site' and operation['site']==stage
            and operation['stage']==stage and operation['request_id']==request
            and vector(operation['target'],3)==profile['targets'][stage], 'foreign task/target')
    reference=operation['observation_reference']
    identity(reference['session_id']); identity(reference['observation_id'])
    require(type(reference['epoch']) is int and reference['epoch']==0
            and reference['map_id']==profile['map_id'] and reference['frame']=='map', 'foreign map/reference')
    current=(reference['session_id'],reference['epoch'],reference['map_id'],reference['frame'])
    require(realm is None or current==realm, 'mixed Sessions')
    op_id=operation['operation_id']; identity(operation['scope_id']); goal=identity(operation['goal_id'])
    require(type(op_id) is int and op_id>0 and type(operation['generation']) is int
            and operation['generation']==(1 if stage=='A' else 2), 'invalid operation/generation')
    receipt=operation['receipt']
    require(receipt['settlement'] in ('pending','settled')
            and receipt['authority_disposition'] in ('current','revoked','released','blocked_unknown'),
            'invalid Owner receipt enum')
    require(type(receipt['authority']['operation_id']) is int and receipt['authority']['operation_id']==op_id
            and receipt['native_identity']==goal and receipt['result_reference']==request
            and receipt['native_acceptance']=='accepted' and receipt['native_outcome']=='succeeded'
            and receipt['output']=='accepted', 'native result association incomplete')
    binding=receipt['authority']['binding']
    require(all(binding[key]==value for key,value in dict(
                provider='scoped-nav2',domain='exclusive-waffle-drive',revision=1,generation=1).items())
            and type(binding['revision']) is int and type(binding['generation']) is int,
            'unsupported authority binding')
    result=operation['result']
    require(result['stage']==stage and result['goal_id']==goal, 'result identity changed')
    admitted=unique(events,'core_admitted',stage)
    closed=unique(events,'core_visit_closed',stage)
    for record in (admitted['record'],closed['record']):
        require(type(record['operation_id']) is int and type(record['generation']) is int
            and vector(record['target'],3)==profile['targets'][stage]
            and type(record['observation_reference']['epoch']) is int
            and all(record[key]==operation[key] for key in (
            'request_id','operation_id','site','stage','target','scope_id','generation'))
            and all(record['observation_reference'][key]==reference[key] for key in (
                'session_id','observation_id','epoch','map_id','frame')),
            'Owner/report operation mismatch')
        authority=record['receipt']['authority']
        require(type(authority['operation_id']) is int and authority['operation_id']==op_id
                and type(authority['binding']['revision']) is int
                and type(authority['binding']['generation']) is int
                and all(authority['binding'][key]==binding[key] for key in (
                    'provider','domain','revision','generation')), 'Owner/report authority mismatch')
    closed_receipt=closed['record']['receipt']
    for key in ('native_identity','result_reference','native_acceptance','native_outcome',
                'output','settlement','authority_disposition'):
        require(closed_receipt[key]==receipt[key], 'Owner/report receipt mismatch')
    reserved=unique(events,'core_native_reserved',stage)
    terminal=unique(events,'native_result',stage)
    arrival=unique(events,'arrival',stage)
    for row in (reserved,terminal,arrival,closed):
        require((row.get('goal_id') if row is not closed else row['record']['goal_id'])==goal,
                'native goal association changed')
    require(type(reserved['operation_id']) is int and reserved['operation_id']==op_id
            and type(terminal['status']) is int and terminal['status']==4
            and type(arrival['status']) is int and arrival['status']==4
            and admitted['steady']<=reserved['steady']<=terminal['steady']<=arrival['steady']<=closed['steady'],
            'invalid native sequence')
    # Consume Owner's fresh-feedback facts; do not independently re-prove native closure.
    observation=arrival['observation']
    vector(observation['pose'],2)
    require(finite(observation['pose_stamp'])>finite(arrival['result_tf_stamp'])
            and finite(observation['clock'])>finite(arrival['result_clock'])
            and arrival['result_clock']==terminal['result_clock']
            and arrival['result_tf_stamp']==terminal['result_tf_stamp'], 'missing result-after feedback')
    return current,reserved,arrival,closed


def evaluate_run(run):
    run=Path(run)
    profile=load_profile()
    verdict=dict(profile=profile['id'],verdict='unknown',reason=None,simulation_only=True,
                 consumed_profile=profile,metrics={},execution={},process_cleanup={},run=str(run))
    try:
        host=object_file(run/'run.json'); scene=object_file(run/'navigation-scene.json')
        selected=object_file(run/'navigation-profile.json'); context=object_file(run/'collection-context.json')
        collection=object_file(run/'collection.json'); process=object_file(run/'collector-process.json')
        report=object_file(run/'agent/report.json'); events=rows_file(run/'caller.jsonl')
        samples=rows_file(run/'physical.jsonl')
        verdict['execution']=recorded_facts(dict(agent_status=report.get('status'),agent_task_verdict=report.get('task_verdict'),
            native_cleanup=report.get('native_cleanup'),operations=[dict(site=op.get('site'),
            native_outcome=op.get('receipt',{}).get('native_outcome'),
            owner_reported_settlement=op.get('receipt',{}).get('settlement'),
            owner_reported_authority=op.get('receipt',{}).get('authority_disposition')) for op in report['operations']]))
        verdict['process_cleanup']=recorded_facts(dict(launcher_result=host.get('result'),container_removed=host.get('container_removed'),
            container_state=host.get('container_state'),collector=process,queries=collection.get('children')))
        run_id=identity(host['run_id'])
        require(host['case']=='installed-nav2-session' and host['scene']==profile['scene']
                and host['profile']==profile['profile'] and host['evaluation_collection'] is True
                and host['container_name']=='robot-harness-sim-'+run_id, 'unsupported run')
        for key in ('scene','map_id','map_file'):
            require(scene[key]==profile[key], 'unsupported actual scene/map')
        require(selected['profile']==profile['profile'], 'unsupported selected profile')
        for key,expected in profile['controller'].items():
            actual=selected['controller'][key]
            if type(expected) in (int,float):
                require(finite(actual)==expected, 'unsupported controller value '+key)
            else:
                require(type(actual) is type(expected) and actual==expected, 'unsupported controller value '+key)
        require(unique(events,'core_ready')['profile']==profile['profile'], 'unsupported Owner profile')
        for key in ('schema','clock','scene','map_id','profile','model'):
            expected=profile['collection_schema'] if key=='schema' else profile[key]
            require(context[key]==expected, 'unsupported collection context')
        for value in (context,collection):
            require(value['run_id']==run_id and value['container_name']==host['container_name'], 'foreign collection')
        for key in ('world','map_file'):
            require(context['alignment'][key]==profile[key], 'unknown fixed map/world alignment')
        alignment=context['alignment']
        require(finite(alignment['resolution'])==profile['resolution']
                and vector(alignment['origin'],3)==profile['origin']
                and vector(alignment['map_to_world_xy_yaw'],3)==profile['map_to_world_xy_yaw'],
                'unknown fixed map/world geometry')
        for key in ('spawn','initial_pose'):
            require(all(finite(alignment[key][field])==value for field,value in profile[key].items()),
                    'unknown fixed initial configuration')
        require(collection['schema']==profile['collection_schema'] and collection['status']=='completed'
                and collection['samples']==['start','A','B'] and collection['errors']==[], 'incomplete collection')
        require(len(collection['children'])==3 and all(child['reaped'] is True
                and type(child['returncode']) is int and child['returncode']==0
                and type(child['pid']) is int and child['pid']>0 for child in collection['children']), 'query cleanup unknown')
        require(process['reaped'] is True and type(process['returncode']) is int and process['returncode']==0
                and type(process['pid']) is int and process['pid']>0 and process['group_forced'] is False,
                'collector exit unknown')
        require(len(samples)==3 and [row['stage'] for row in samples]==['start','A','B'], 'missing/duplicate samples')
        ready=unique(events,'ready')
        initial=check_sample(samples[0],ready,host,profile)
        map_pose=vector(samples[0]['map_pose'],2)
        require(map_pose==vector(ready['observation']['pose'],2), 'startup map sample changed')
        anchor=[profile['initial_pose']['x'],profile['initial_pose']['y']]
        initial_errors=[math.dist(initial[:2],anchor),math.dist(map_pose,anchor),math.dist(initial[:2],map_pose)]
        require(max(initial_errors)<=profile['initial_anchor_limit_m'], 'initial alignment anchor mismatch')
        verdict['metrics']['initial_anchor_errors_m']=initial_errors
        task_id=identity(report['task_id'])
        require(report['goal']==GOAL and len(report['operations'])==2, 'unsupported/incomplete task')
        require([row.get('stage') for row in events if row.get('event')=='core_native_reserved']==['A','B'],
                'unsupported native goal sequence')
        realm=None; sequence=[]; distances={}
        for index,stage in enumerate(('A','B')):
            operation=report['operations'][index]
            realm,reserved,arrival,closed=check_operation(operation,stage,task_id,events,profile,realm)
            require(samples[index+1]['goal_id']==operation['goal_id'], 'foreign physical native goal')
            pose=check_sample(samples[index+1],arrival,host,profile)
            distances[stage]=finite(math.dist(pose[:2],profile['targets'][stage][:2]))
            sequence.append((reserved,arrival,closed))
        a,b=report['operations']
        require(a['operation_id']!=b['operation_id'] and a['scope_id']!=b['scope_id']
                and a['goal_id']!=b['goal_id'], 'reused operation/scope/goal')
        require(samples[0]['finished']<sequence[0][0]['steady']
                and samples[1]['finished']<sequence[1][0]['steady']
                and sequence[0][2]['steady']<sequence[1][0]['steady'], 'missing pre-native-send sample order')
        require(a['receipt']['settlement']=='settled' and a['receipt']['authority_disposition']=='released',
                'Owner did not report release before B')
        verdict['metrics']['arrival_distance_m']=distances
        failures=[stage for stage,distance in distances.items() if distance>profile['arrival_limit_m']]
        verdict.update(verdict='failed' if failures else 'succeeded',
                       reason=dict(outside_arrival_limit=failures) if failures else 'associated_fixed_A_B_arrivals')
    except (OSError,KeyError,TypeError,ValueError,OverflowError,AttributeError) as error:
        verdict['reason']='incomplete_or_invalid_evidence: '+str(error)
    return verdict


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True,help='new offline report; existing output refused before evaluation')
    args=parser.parse_args()
    try:
        with args.output.open('x') as stream:
            verdict=evaluate_run(args.run)
            stream.write(json.dumps(verdict,indent=2,allow_nan=False)+'\n')
    except OSError as error:
        parser.error('cannot create evaluation report: '+str(error))
    print(json.dumps(verdict,indent=2,allow_nan=False))
    return {'succeeded':0,'failed':1,'unknown':2}[verdict['verdict']]


if __name__=='__main__':
    raise SystemExit(main())
