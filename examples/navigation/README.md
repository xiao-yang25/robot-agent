# Run the controlled navigation business application

This tutorial starts a real Humble/Gazebo A→B scene, the installed Harness owner,
and the installed public Agent CLI. Its three executable proposals are explicitly
controlled: **no model service, robot hardware or automatic recovery** is used.
The Agent still checks fresh observations, proposal identity and deadlines, and
retains final pending settlement and unknown native cleanup.

Use Python3.10+ and pip on the host, Docker, and a new consumer directory. Linux
amd64 is the simulation target; Apple Silicon uses Docker Desktop emulation.
The runtime container has 2 CPU, 4 GiB, no network and a 420-second host limit.
Preparation needs disk/memory for the build and may download Python headers.
Run the host commands from this Agent checkout. Use the exact full Harness
revision in [workspace.repos](../../workspace.repos); the launcher rejects a
different or modified Harness checkout.

## Prepare the fixed sources and image

Clone Harness beside Agent into a new directory, and check out the manifest's
immutable revision:

```sh
git clone https://github.com/xiao-yang25/robot-harness.git ../harness-navigation
```

```sh
HARNESS_REVISION=$(python3 -c 'import re; from pathlib import Path; r=re.findall(r"^    version: ([0-9a-f]{40})$", Path("workspace.repos").read_text(), re.M); assert len(r)==1; print(r[0])')
git -C ../harness-navigation checkout "$HARNESS_REVISION"
python3 ../harness-navigation/integrations/ros2/simulation/simulate.py build --image robot-navigation-demo:humble
```

The public image recipe supplies the native scoped drive, workers, scene and ROS
dependencies. An existing image built from that recipe can be selected instead;
record its identity and qualification separately. Do not substitute a generic
Nav2 stack or infer compatibility from a tag alone.

## Build new Linux installations

Build the Agent's pure-Python wheel on the host and download the public pip
bootstrap wheel. The subsequent Agent installation needs no package-index access:

```sh
mkdir navigation-consumer
python3 -m pip wheel --no-deps --wheel-dir navigation-consumer/dist .
python3 -m pip download --no-deps --only-binary=:all: --dest navigation-consumer/bootstrap pip==25.0.1
```

Run preparation with a writable new consumer directory and read-only source/tool
mounts. The script refuses existing build/install directories. Header installation,
if needed, affects only this disposable preparation container:

```sh
docker run --rm --platform linux/amd64 --cpus=2 --memory=4g --entrypoint bash \
  --env DEMO_UID="$(id -u)" --env DEMO_GID="$(id -g)" \
  --mount "type=bind,source=$(cd ../harness-navigation && pwd),target=/harness-source,readonly" \
  --mount "type=bind,source=$PWD/navigation-consumer,target=/consumer" \
  --mount "type=bind,source=$PWD/examples/navigation/prepare.sh,target=/prepare.sh,readonly" \
  --mount "type=bind,source=$PWD/navigation-consumer/dist/robot_agent-0.0.0-py3-none-any.whl,target=/robot_agent-0.0.0-py3-none-any.whl,readonly" \
  --mount "type=bind,source=$PWD/navigation-consumer/bootstrap/pip-25.0.1-py3-none-any.whl,target=/pip-25.0.1-py3-none-any.whl,readonly" \
  robot-navigation-demo:humble /prepare.sh
```

This builds and installs the real Core/Python bridge in Linux and installs the
Agent wheel into `agent-install`. The binary prefix must match the container's
Python ABI; a macOS prefix is not a substitute. `python_session` is a software
check, separate from the following actual native run.

## Run once and read the outcome

```sh
python3 examples/navigation/run.py --harness-source ../harness-navigation \
  --python-prefix navigation-consumer/install --agent-prefix navigation-consumer/agent-install \
  --image robot-navigation-demo:humble --output runs/navigation-controlled-01
```

Always choose a new result directory. The selector replaces itself with Harness's
existing launcher; that launcher owns container startup, limits, signals and exact
cleanup. The in-container selector replaces itself with the existing Agent CLI.
No new business or control loop is introduced. The owner explicitly permits
45 seconds of caller idle time; task/proposal budgets remain 240/30 seconds.

Inspect these different records:

| Record | Meaning |
|---|---|
| `run.json` | Container exit/OOM state and cleanup outcome; `passed` is process completion only |
| `verification.json` | Owner/client process-completion marker, not a physical task verdict |
| `agent/report.json` | Three controlled decisions, A/B operations, A settled/released, final B accepted/pending; task verdict unassessed and native cleanup unknown |
| `agent/decisions/decision-*/` | Declared model identifier `controlled-tutorial-no-model`, inputs/answers and reaped proposal process records |
| `caller.jsonl`, `caller.log`, `request-client.log` | Native/Core progress, preparation diagnostics and application errors |

There is no installed navigation physical evaluator. Research qualifications used
separate same-run Gazebo observations and an offline predicate; ground truth never
entered model/task decisions. These [published recordings](https://xiao-yang25.github.io/robot-harness/#failure-demos)
retain their own versions and scope, rather than qualifying every tutorial run.
The [ALOHA evaluator](../../docs/TESTING.md#independent-evaluation) cannot evaluate navigation.

If preparation or execution fails, retain the logs and use a new directory for a
separately diagnosed attempt. No automatic retry, reset or third admission is
provided. Interrupting the host launcher tears down the entire container; it is
not evidence of native stop or settlement. The public CLI's task cancellation is
separately tested. Confirm `container_removed`; reconcile the recorded container
identity if cleanup failed. Keep a required image and useful build/log directories;
remove only resources belonging to failed or superseded runs.

## Real models and limits

The controlled executable is a tutorial fixture, not Codex or another model.
The application supports its existing [text proposal backend](../../docs/README.md#navigation-application),
but this network-disabled workflow does not yet deliver the host-to-container real
model path. That path and a fresh-install actual-model run remain separate M6c
delivery work. No credential directory is mounted. General routes, obstacles,
owner failure/restart, complete native cleanup, hard stop, physical hardware and
broad model reliability are outside this tutorial.
