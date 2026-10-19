# Inspect a station using a prepared Owner

`robot-agent-inspection` is an experimental reference application. It uses the
existing private task loop, a caller-owned ROS camera and the public Harness
NavigationSession. A finite rule provider interprets the selected marker reading;
this command makes no model requests and does not accept a model option.

The task visits A and reads its status. Normal ends the task; abnormal permits
at most one visit to B for a recheck, retaining A's anomaly. Unknown or unusable
observations request help with no next action. The application cannot claim
physical repair or an independently evaluated task verdict.

## Prepare the environment

Use the exact Harness commit from [workspace.repos](../../workspace.repos) and
matching Linux Core/Agent installations. The [navigation preparation tutorial](../navigation/README.md#build-new-linux-installations)
explains those installations. Run this command in the same isolated Ubuntu
22.04/ROS 2 Humble environment as the prepared Owner and camera, with its ROS
setup sourced and the installed Agent/Harness packages on `PYTHONPATH`.

This increment supplies the application command. A supported camera-equipped
simulation scene and turnkey launcher are subsequent work; the stock navigation
scene alone does not supply the inspection camera or panels. Research scene
wrappers and existing recordings retain their original versions and scope.

The prepared environment must supply:

| Input | Required fixed contract |
|---|---|
| Owner | Public local `NavigationSession` endpoint, `scoped-two-context-nav2-shim-v1`, map `turtlebot3-world-v1` |
| Sites | map-frame A `(0.7, -0.5, 0)` and B `(-1.5, -0.5, 0)`; registered visual targets `indicator-A` / `indicator-B` |
| Image | Exactly one publisher on `/inspection/image_raw`, RGB8 640×480, step 1920, frame `inspection_optical` |
| Camera info | `/inspection/camera_info`, matching shape/frame, finite positive focal lengths and associated image timestamp |
| Clock and localization | Advancing `/clock`, `/amcl_pose` in `map`, image-time `map → base_link` TF |
| Camera mount | `base_link → inspection_optical`, translation `(0.1, 0, 0.3)` m; ROS optical orientation appropriate to the physical camera |

The current source keeps a five-second sampling window, at most 25 samples and
at least three usable samples. Source/frame freshness is at most one second;
closing a sampling window does not turn camera health off. Missing, ambiguous,
clipped or unreadable targets stay unknown. The controlled colored-panel reader
cannot authenticate arbitrary targets or infer general scene semantics.

## Run one task

Install this checkout's Agent package, then use a fresh output directory:

```sh
robot-agent-inspection --endpoint /absolute/prepared/navigation.sock \
  --output runs/inspection-01 --marker-reader located-bright-panel
```

The equivalent module entry is:

```sh
python3 -m robot_agent.inspection_cli --endpoint /absolute/prepared/navigation.sock \
  --output runs/inspection-02 --marker-reader located-bright-panel
```

Choose the reader explicitly; there is no automatic fallback:

| Selection | Intended fixture |
|---|---|
| `fixed-center` | Historical fixed central reading region |
| `located-white-panel` | Located controlled white-bordered panel, original brightness rule |
| `located-bright-panel` | Located emissive bright-white panel; neutral gray is not its border |

Read `report.json` for the task outcome, original request/operation identities,
checks, cancellation responses and local owner/camera closure. `application`
records the selected reader and `rules-no-model` provider. The report remains
`task_verdict=unassessed` and `native_cleanup=unknown`; successful local resource
closure does not establish complete native release or physical stopping.

Exit zero requires task completion, confirmed local resources closed and no
runtime error. Help, cancellation, runtime error or incomplete local close exits
nonzero; an expected negative example is still an unsuccessful application task.
Invalid options are rejected before creating task resources. Existing output is
refused rather than overwritten. SIGINT/SIGTERM request withdrawal through the
existing task; they are not emergency-stop or hard stop-latency guarantees.

The command does not start an Owner, camera, container or model, and does not
retry ambiguous submission. Its internal policy/coordinator/source classes are
private implementation, not a reusable Agent or Skill SDK. See [Testing](../../docs/TESTING.md#installed-inspection-command)
for software evidence and the remaining simulation qualifications.
