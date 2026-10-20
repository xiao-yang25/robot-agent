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

For the controlled simulator, use the [one-command tutorial](#run-the-controlled-simulation)
below. It selects Harness's optional camera/panel scene and this installed command;
ordinary navigation without that selection has no inspection camera. Existing
recordings retain their original versions; the tutorial's new moving qualification
and same-run recordings are separate from its software checks.

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


## Run the controlled simulation

Use Python 3.10+ on the host and Docker. The fixed simulation target is Ubuntu
22.04/ROS 2 Humble, Linux amd64; Apple Silicon uses Docker Desktop emulation.
Run these host commands from this Agent checkout. The runtime uses the existing
2 CPU / 4 GiB, offline container and 420-second host limit. No model is called.

### Prepare the fixed source and visual image

Clone into a new directory and select the exact immutable dependency:

```sh
git clone https://github.com/xiao-yang25/robot-harness.git ../harness-inspection
HARNESS_REVISION=$(python3 -c 'import re; from pathlib import Path; r=re.findall(r"^    version: ([0-9a-f]{40})$", Path("workspace.repos").read_text(), re.M); assert len(r)==1; print(r[0])')
git -C ../harness-inspection checkout "$HARNESS_REVISION"
python3 ../harness-inspection/integrations/ros2/simulation/simulate.py build \
  --visual --image robot-inspection-demo:humble
```

The current pin is Harness `542400c`; a different or modified source checkout is
rejected (tracked or nonignored untracked changes). This visual image is required for RGB rendering, even without a viewer.
It supplies Xvfb, native scoped workers/drive and the fixed ROS/Gazebo dependencies.
An existing compatible image may be selected explicitly; record its identity
and qualification. A tag alone does not prove compatibility.

The selector also accepts explicit `--platform linux/arm64` for a separately
prepared compatible visual image and matching ARM64 Linux installations. Use
the same platform for preparation and launch. The supplied Classic Dockerfile
still depends on amd64 binaries; the flag does not provide an ARM64 build recipe
or transfer existing amd64 scenario qualification to a native environment.

### Prepare new Linux installations

Use a new consumer directory. The existing navigation preparation script builds
Core/Python and installs this Agent wheel; it introduces no second runtime or
inspection-specific dependency. It may download Python headers in its disposable
preparation container if absent. The controlled marker reader uses image bytes;
no LLM, vision package extra, checkpoint or model credential is required.

```sh
mkdir inspection-consumer
python3 -m pip wheel --no-deps --wheel-dir inspection-consumer/dist .
python3 -m pip download --no-deps --only-binary=:all: \
  --dest inspection-consumer/bootstrap pip==25.0.1

docker run --rm --platform linux/amd64 --cpus=2 --memory=4g --entrypoint bash \
  --env DEMO_UID="$(id -u)" --env DEMO_GID="$(id -g)" \
  --mount "type=bind,source=$(cd ../harness-inspection && pwd),target=/harness-source,readonly" \
  --mount "type=bind,source=$PWD/inspection-consumer,target=/consumer" \
  --mount "type=bind,source=$PWD/examples/navigation/prepare.sh,target=/prepare.sh,readonly" \
  --mount "type=bind,source=$PWD/inspection-consumer/dist/robot_agent-0.1.0a1-py3-none-any.whl,target=/robot_agent-0.1.0a1-py3-none-any.whl,readonly" \
  --mount "type=bind,source=$PWD/inspection-consumer/bootstrap/pip-25.0.1-py3-none-any.whl,target=/pip-25.0.1-py3-none-any.whl,readonly" \
  robot-inspection-demo:humble /prepare.sh
```

The prefix must match Linux's Python ABI. A macOS installation cannot replace it.
The preparation refuses existing build/install/agent-install paths. Record the
Agent checkout revision before building; a wheel version alone does not identify
the source revision. `python_session` checks software, not physical arrival.

### Launch one inspection

```sh
python3 examples/inspection/run.py --harness-source ../harness-inspection \
  --python-prefix inspection-consumer/install --agent-prefix inspection-consumer/agent-install \
  --image robot-inspection-demo:humble --case normal --output runs/inspection-normal-01
```

For red A / green B, use `--case recheck` and a new output such as
`runs/inspection-recheck-01`. Expected task behavior is A normal → finish, or A
abnormal → at most one B recheck. Unknown images request help. The selector uses the case to configure the simulator. The inspection command
does not consume that selection or simulator truth as decision input; it uses
image observations. The fixture environment remains visible in the shared
container, so this is an input boundary, not security isolation. The installed client selects `located-bright-panel` explicitly.
Original sampling, freshness, proposal/task budgets and close semantics remain.

The host selector replaces itself with Harness's existing launcher; its installed
client replaces itself with the inspection CLI. No extra supervisor or task loop
is started. The Owner permits 45 seconds of caller idle time. Both native
controller tolerances are checked before public Session admission by Harness.

| Record | Meaning |
|---|---|
| `run.json` | Container exit/OOM and cleanup; `passed` is process completion |
| `verification.json` | Clean client/Owner/simulator process completion, not a physical task verdict |
| `agent/report.json` | Camera checks, decisions, original A/B identities, task status and local resource closure |
| `inspection-scene.json`, `caller.jsonl` | Scene selection and actual pre-admission controller-parameter facts |
| `display-process.json`, `launcher-processes.json` | Display/group force, remaining processes and reaping |

Read the Agent report alongside launcher results. Native cleanup stays unknown
and task verdict unassessed; completed task logic or closed OS resources cannot
prove physical success. Errors, help, cancellation or incomplete cleanup remain
nonzero exits. Ctrl-C on this host command asks Harness to tear down the whole
container; it is not the Agent CLI's task cancellation or an emergency stop.

You may append `--record-evaluation` for passive pose collection. It records
independent evidence only; the collector's original A/B observations are not an
inspection-task evaluator, and normal A-only is not a missing-B task failure.
Do not infer an inspection verdict from collection completion. This tutorial
starts no viewer or recorder. [Software verification and remaining qualification](../../docs/TESTING.md#inspection-simulation-tutorial)
keep fresh moving tests and same-run media distinct from the software delivery.
