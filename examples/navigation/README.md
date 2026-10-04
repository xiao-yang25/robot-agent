# Run the navigation business application

This tutorial starts a real Humble/Gazebo A→B scene, the installed Harness owner,
and the installed public Agent CLI. Its three executable proposals are explicitly
controlled by default: **no model service, robot hardware or automatic recovery**
is used. An explicit host model mode is described below.
The Agent still checks fresh observations, proposal identity and deadlines, and
retains final pending settlement and unknown native cleanup.

Use Python3.10+ and pip on the host, Docker, and a new consumer directory. Linux
amd64 is the simulation target; Apple Silicon uses Docker Desktop emulation.
The runtime container has 2 CPU, 4 GiB, no network and a 420-second host limit.
Preparation needs disk/memory for the build and may download Python headers.
Run the host commands from this Agent checkout. Use the exact full Harness
revision in [workspace.repos](../../workspace.repos); the launcher rejects a
different or modified Harness checkout.

This tutorial uses the Agent `0.1.0a1` wheel built from your selected checkout,
and its pinned Harness source; it does not install Agent from a package index.
Record `git rev-parse HEAD` for that checkout before preparing the pair. A changed
Agent revision needs its own verification; existing videos retain their versions.

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
  --mount "type=bind,source=$PWD/navigation-consumer/dist/robot_agent-0.1.0a1-py3-none-any.whl,target=/robot_agent-0.1.0a1-py3-none-any.whl,readonly" \
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

## Run the checkpoint task

Build a new wheel and Linux installation from a checkout containing
`CheckpointNavigationTask` and this tutorial. The released `v0.1.0a1` tag predates
it. The default task and installed navigation CLI remain fixed A→B.
Install the same wheel into a host environment, since this explicit mode uses
the Agent's caller supervisor:

```sh
python3 -m venv navigation-checkpoint-host
navigation-checkpoint-host/bin/python -m pip install --no-index --no-deps navigation-consumer/dist/robot_agent-0.1.0a1-py3-none-any.whl
navigation-checkpoint-host/bin/python examples/navigation/run.py --task checkpoint \
  --instruction finish_at_a --instruction-delay 4 \
  --harness-source ../harness-navigation --python-prefix navigation-consumer/install \
  --agent-prefix navigation-consumer/agent-install --image robot-navigation-demo:humble \
  --output runs/checkpoint-finish-01
```

Use `--instruction continue_b` and a different output directory for the second
branch. This is a controlled business provider: the configured answer is delivered
once, after released A, with the task/checkpoint/session/map/epoch/frame identity.
It does not perform human intent recognition or inspect the scene. The optional
delay is 0–9 seconds inside the task's ten-second instruction window; collection,
the following proposal and validation share the original thirty-second deadline.
The default proposal is also controlled and makes no model requests.

To use a host model, add `--provider host-codex --model YOUR_MODEL --executable codex`
and a separate new `--host-output` to the same checkpoint command. The host worker
must be explicitly in checkpoint mode, forwards only the normalized bound
instruction and declared measurements, and requests at most two proposals for
finish-A or three for continue-B. Model credentials stay outside the container.
No business instruction is inferred from a model response.

Read `agent/instruction.jsonl` for the single request/answer and `agent/report.json`
for instruction acceptance, decisions and operation dispositions. Finish-A reports
`completed_sites: ['A']` and unknown native cleanup; prepared B resources may still
exist. Continue-B reports A released and B current/pending. A task result stays
unassessed. Caller close, owner exit and physical success are different outcomes.
Host mode also writes `agent-proposals/` relay records and private host model
records. The supervisor keeps its exact client bind file through Harness cleanup.
Use new run directories and retain failed diagnostics; no replay is provided.

## Run with a host model

Use the same wheel and Linux prefixes above. Install that wheel into a separate
host Python environment; the host worker needs only the package's standard-library
navigation modules. It must not import the Linux Core binary:

```sh
python3 -m venv navigation-host
navigation-host/bin/python -m pip install --no-deps navigation-consumer/dist/robot_agent-0.1.0a1-py3-none-any.whl
```

Install and authenticate your Codex CLI on the host using its own setup. Select an
explicit model that your service supports. This opt-in mode makes at most three
model requests, each within the original 30-second proposal budget:

```sh
navigation-host/bin/python examples/navigation/run.py --provider host-codex \
  --model YOUR_MODEL --executable codex --host-output runs/navigation-model-01-host \
  --harness-source ../harness-navigation --python-prefix navigation-consumer/install \
  --agent-prefix navigation-consumer/agent-install --image robot-navigation-demo:humble \
  --output runs/navigation-model-01
```

The host owns the model CLI, its network and credentials. The simulation stays
network-disabled. A local relay exchanges only this task's three phase proposals;
the host reconstructs task context and the declared map pose/time/sensor health,
then calls the existing text backend with tools disabled. Neither the model nor
the relay receives a robot interface. The Agent revalidates each reply and fresh
observation before any admission. There is no retry or fallback provider.

Choose new, separate scene and host directories. Private host output must also be
outside both installed prefixes and Harness's simulation directory; overlapping
paths are refused before startup. Host logs, prompts, answers and actual model/CLI
version stay in `--host-output`, which is never mounted into the container.
The scene's `agent/decisions` records the relay processes; the host's `decisions`
records actual model processes. `model-server.json` records phase exchange and
`processes.json` records owned worker/launcher reaping. Treat these as private
operator records rather than website assets.

The supervisor owns the host worker and the existing Harness launcher. Interrupts
notify the launcher, which retains Docker cleanup ownership. The generated
read-only client script survives through that cleanup. Teardown permits 110 seconds
for the launcher's bounded create/cleanup paths and 6 seconds for the model worker,
then kills surviving owned process groups; this does not extend task/motion budgets
or prove a hard stopping limit. Proposal withdrawal also notifies the host to reap
its local CLI child. Remote model-service termination and resource release remain
unknown. Check both process records and `container_removed` after interruptions.

## Report a problem or return to a previous pair

Use the [feedback instructions](../../CONTRIBUTING.md#feedback-and-changes).
Include the Agent commit/package version, Harness pin, selected image identity,
host architecture/Docker environment, failed stage and minimal redacted diagnostics.
Keep preparation failures separate from task reports and physical evaluation.

To return to a previously verified pair, check out its recorded Agent commit in a
separate clean clone. Read that commit's `workspace.repos`, select its matching
Harness source/image, and follow its tutorial using new consumer and run
directories. Do not overwrite installed prefixes or reuse an in-flight scene.
A container image tag alone does not identify a verified pair.

## Limits

The controlled executable is a tutorial fixture. Host model mode uses the existing
[text backend](../../docs/README.md#navigation-application); configured code and
controlled tests alone do not qualify a real model. See [recorded qualification](../../docs/TESTING.md#public-host-model-navigation-workflow)
for the actual tested combination. General routes, obstacles, owner failure/restart,
complete native cleanup, hard stop, hardware and broad model reliability remain
outside this tutorial. Navigation still has no installed physical evaluator.
