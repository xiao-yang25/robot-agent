"""Synthetic contract measurements, never a simulator qualification."""
from copy import deepcopy
import json
from pathlib import Path


def make_run(root):
    root=Path(root); (root/'agent').mkdir(parents=True)
    run_id='1'*32; name='robot-harness-sim-'+run_id
    context=dict(schema='nav2-passive-truth-v1',run_id=run_id,container_name=name,
        model='turtlebot3_waffle',clock='container-clock-monotonic',scene='normal',
        map_id='turtlebot3-world-v1',profile='scoped-two-context-nav2-shim-v1',alignment=dict(
        world='/opt/ros/humble/share/nav2_bringup/worlds/world_only.model',
        map_file='/opt/ros/humble/share/nav2_bringup/maps/turtlebot3_world.yaml',resolution=.05,
        origin=[-10.,-10.,0.],map_to_world_xy_yaw=[0.,0.,0.],
        spawn=dict(x=-2.,y=-.5,z=.01,R=0.,P=0.,Y=0.),initial_pose=dict(x=-2.,y=-.5,z=0.,yaw=0.)))
    host=dict(case='installed-nav2-session',run_id=run_id,container_name=name,
        scene='normal',profile=context['profile'],evaluation_collection=True,result='passed',container_removed=True)
    collection=dict(schema=context['schema'],run_id=run_id,container_name=name,status='completed',
        samples=['start','A','B'],errors=[],children=[dict(pid=i,returncode=0,reaped=True) for i in (101,102,103)])
    process=dict(pid=100,returncode=0,reaped=True,group_forced=False)
    events=[dict(event='ready',steady=105.,observation=dict(pose=[-2.,-.5])),
            dict(event='core_ready',steady=108.,profile='scoped-two-context-nav2-shim-v1')]
    samples=[dict(event='ready',stage='start',trigger=105.,started=105.01,finished=105.1,
        run_id=run_id,container_name=name,model='turtlebot3_waffle',xyz_rpy=[-2.,-.5,.01,0.,0.,0.],map_pose=[-2.,-.5])]
    operations=[]
    for index,(stage,target) in enumerate((('A',[.7,-.5,0.]),('B',[-1.5,-.5,0.]))):
        request='2'*32+('-prepare' if stage=='A' else '-after_a'); goal=str(index+3)*32
        operation=dict(skill='navigation.visit_site',site=stage,stage=stage,target=target,
            request_id=request,operation_id=index+1,scope_id=str(index+5)*32,generation=index+1,
            observation_reference=dict(session_id='7'*32,observation_id=str(index+8)*32,
                epoch=0,map_id='turtlebot3-world-v1',frame='map'),
            goal_id=goal,state='finished',result=dict(stage=stage,goal_id=goal),receipt=dict(
                authority=dict(operation_id=index+1,binding=dict(provider='scoped-nav2',domain='exclusive-waffle-drive',revision=1,generation=1)),
                native_identity=goal,result_reference=request,native_acceptance='accepted',native_outcome='succeeded',
                output='accepted',settlement='settled' if index==0 else 'pending',
                authority_disposition='released' if index==0 else 'current'))
        operations.append(operation)
        offset=40*index
        events.extend([dict(event='core_admitted',steady=109.+offset,stage=stage,record=deepcopy(operation)),
            dict(event='core_native_reserved',steady=110.+offset,stage=stage,goal_id=goal,operation_id=index+1),
            dict(event='native_result',steady=140.+offset,stage=stage,goal_id=goal,status=4,result_clock=20.+offset,result_tf_stamp=19.+offset),
            dict(event='arrival',steady=141.+offset,stage=stage,goal_id=goal,status=4,result_clock=20.+offset,result_tf_stamp=19.+offset,
                observation=dict(pose=target[:2],pose_stamp=20.+offset,clock=21.+offset)),
            dict(event='core_visit_closed',steady=143.+offset,stage=stage,record=deepcopy(operation))])
        samples.append(dict(event='arrival',stage=stage,goal_id=goal,trigger=141.+offset,started=141.01+offset,
            finished=141.1+offset,run_id=run_id,container_name=name,model='turtlebot3_waffle',xyz_rpy=target[:2]+[.01,0.,0.,0.]))
    report=dict(task_id='2'*32,goal='Visit registered site A, then site B, using fresh map feedback after each visit.',
        status='completed',task_verdict='unassessed',native_cleanup='unknown',operations=operations)
    data={'run.json':host,'navigation-scene.json':dict(scene='normal',map_id='turtlebot3-world-v1',map_file=context['alignment']['map_file']),
        'navigation-profile.json':dict(profile=context['profile'],controller=dict(
            plugin='nav2_rotation_shim_controller::RotationShimController',primary_controller='dwb_core::DWBLocalPlanner',
            angular_dist_threshold=.785,angular_disengage_threshold=.785,forward_sampling_distance=.5,
            rotate_to_heading_angular_vel=.8,max_angular_accel=3.2,simulate_ahead_time=1.,rotate_to_goal_heading=False,closed_loop=True)),
        'collection-context.json':context,
        'collection.json':collection,'collector-process.json':process,'agent/report.json':report,
        'caller.jsonl':events,'physical.jsonl':samples}
    write_run(root,data)
    return data


def write_run(root,data):
    for name,value in data.items():
        text = ''.join(json.dumps(row)+'\n' for row in value) if name.endswith('.jsonl') else json.dumps(value)+'\n'
        (Path(root)/name).write_text(text)
