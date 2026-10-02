# Robot Agent

Bounded, observation-driven task applications for
[Robot Harness](https://github.com/xiao-yang25/robot-harness). Experimental project;
the selected Mac and Linux normal consumer increments are merged. No release yet.

The first application attempts an ALOHA cube transfer followed by one simulated
second of holding. Its task state and visual decisions live here; ACT supplies
joint targets, while Harness owns execution and resources. Existing Codex/MCP
tool consumers remain a separate way of using Harness.

## Task contract

1. Read the initial camera/joints. The qualified reset starts with the cube on the
   table, with empty grippers; the ACT skill includes right-arm pickup and transfer.
   A visual backend proposes attempting transfer or requesting help.
2. Submit the qualified 400-step transfer. Require its own correlated delivered
   result and settled receipt before continuing.
3. Read the new observation at sequence400 in the same epoch. The backend proposes
   hold or help based on the new image; the application may submit a separate
   50-step hold only after revalidating that proposal and current capability.
4. Read sequence450 and request a final visual assessment. Report that assessment
   separately from execution and independent task evaluation.

At most one transfer, one hold and three decisions per task. No automatic reset,
retry or recovery. Every answer binds task ID, phase, epoch and observation
sequence. Unsupported, stale, cancelled or expired proposals cannot start an
operation. Another task requires an operator-controlled explicit episode reset
and a new task object. A new task while the scene requires reset is refused.

The caller owns Session startup/close. The task borrows it and serializes calls;
the model adapter has no Session or raw-action interface. The command-line caller
creates the Session and closes it on all reported exit paths. SIGINT requests task
cancellation; a native call already executing cannot be undone. Cleanup failure
is retained separately, and never relabeled successful cleanup.

Budget: 300 seconds including startup (90 maximum), 60 per visual decision and
60 per operation; operation deadlines use remaining task time. Budget checks
before/after synchronous calls do not make those calls interruptible or provide
a hard stopping latency. No additional observation/retry loop is implemented.
The stepped simulator pauses between operations; rereading a frame is revalidation,
not another physical observation or proof of holding duration.

`visual_assessment=observed_success` is a model's interpretation of the final
image. `task_verdict` remains `unassessed`; an independent evaluator may assess
the recorded physical trace afterward. Contacts/cube poses and evaluator output
are excluded from every model input and do not authorize hold.

## Run

Python3.10+. The task/preparation tests use the standard library; the full suite
also exercises real camera-PNG/subprocess boundaries with `vision` and the
independent task predicate with the optional NumPy-based `evaluation` extra. ACT, MuJoCo and authenticated Codex are not needed for these tests:

```sh
python -m pip install '.[vision,evaluation]'
PYTHONPATH=src python -m unittest discover -s tests -v
```

For the real task, follow [ACT / ALOHA setup](skills/aloha/README.md). It provides a
Mac arm64 and Linux aarch64 dependency lock, bundled ACT worker, explicit pinned
model download and offline migration commands. [`workspace.repos`](workspace.repos) pins the Harness
dependency; weights remain operator-prepared assets outside Git.

The visual adapter requires Pillow (install the `vision` extra when preparing
a new environment), the operator's authenticated Codex CLI, and an explicitly
selected model. It invokes an ephemeral CLI with user configuration ignored,
tools disabled, a structured response and a maximum60-second decision window.
This is a cooperating visual proposal backend, not a security sandbox or a
general robot agent framework. It does not read credentials or edit CLI settings.

```sh
# Set PYTHONPATH to the installed Harness Python directory after setup.
skills/aloha/.venv/bin/robot-agent-handoff --output /path/to/fresh-run \
  --checkpoint /path/to/migrated-checkpoint --device mps --seed 0 \
  --model YOUR_AVAILABLE_MODEL
```

`report.json` keeps task state, decisions, operation receipts and cleanup outcome.
`decisions/` retains the exact camera PNG, measurement/context, prompt, raw CLI
events, answer and process exit for each decision. `episodes/` is the Harness
trace/video. These can contain local operator paths and are not publication assets.
The CLI exits successfully only after all stages complete and cleanup is confirmed;
its exit status does not establish independently verified business success.

## Evaluate the recorded task independently

The package ships one [fixed predicate](src/robot_agent/handoff_profile.json)
and [evaluator](src/robot_agent/evaluate_handoff.py). In the same pinned
[ALOHA skill environment](skills/aloha/README.md), after the task has closed:

```sh
skills/aloha/.venv/bin/robot-agent-evaluate-handoff \
  --run /path/to/fresh-run/episodes --trace-name episode-0.jsonl \
  --output /path/to/fresh-run/task-evaluation.json
```

The evaluator reconstructs cube/hand/table poses from recorded `qpos` using the
pinned model's forward kinematics, without advancing dynamics. It checks the
400-step transfer followed by 50 repeated targets and the anchor-plus-one-second
window: both left fingers alone contact the cube, relative movement ≤5mm,
rotation ≤15 degrees, and table clearance ≥5mm. This is a finite simulation
predicate, not a physical safety guarantee or a general grasp detector.

A complete passing trace reports `succeeded`; a complete trace that violates
these physical conditions reports `failed`. Incomplete/invalid evidence or missing
model dependencies reports `unknown`. Exit codes are 0/1/2 respectively; command
usage/output errors also exit2. The report retains the consumed predicate and
measurements. An existing output is refused before evaluation; evaluate each run
once and retain the report. This separate report does not mutate `report.json`,
change `task_verdict=unassessed`, or feed simulator truth into task decisions.
The `evaluation` extra supplies NumPy only; real trace reconstruction requires
the existing pinned skill environment/assets, not an additional model download.

## Installed combination CI

[Combination CI](.github/workflows/combination.yml) builds/installs the real
Harness dependency from `workspace.repos`, installs Agent, then runs the
[three boundary cases](tests/combination/test_installed.py) outside both source
trees: normal transfer/hold with distinct settled Core receipts, help after
transfer, and an old answer that cannot start hold. It verifies import locations,
recorded action effects and Host/worker exit. Session, Host and Core are real;
only camera/action/recording and policy providers are explicit no-physics
fixtures. No ACT, MuJoCo, video, perception or physical-success claim follows.

Agent PRs check their candidate against the fixed Harness version. The reusable
workflow also accepts a full candidate Harness commit and a fixed known Agent
commit, so a Harness PR can call the same tests after this Agent workflow has
been published and qualified. The Harness-side caller is a subsequent delivery
step; neither configuring this workflow nor local tests mean hosted CI passed.
See [GitHub reusable workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows)
for the job-level caller mechanism. Actual ACT/model/physics qualification remains
explicit and separate from this lightweight check.

## Acceptance and delivery

The first increment must reject hold after an old answer, episode change, invalid
observation, deadline, cancellation, failed/refused operation or pending settlement.
Changed measurement proposals must change whether hold is submitted. Tests also
cover ambiguous submission, no replay and explicit reset for another task.

The fixture tests exercise application control flow, not visual perception or
native resource cleanup. Real qualification must retain actual model input and
answer,400→450 progression, same-run video/trace, an independent task evaluation,
and process exit evidence. Report help/failure honestly if the model abstains.
Lightweight Ubuntu CI checks these boundaries and installed entry points. See
[Actions](https://github.com/xiao-yang25/robot-agent/actions) for revision-specific
remote results; it does not run ACT, MuJoCo or a visual model.

Locally qualified: 17 task-control, five preparation-boundary and eight real
subprocess-control tests passed. The subprocess cases cover cancellation/expiry
before launch, late answers written during termination, completed-process races,
and a child that ignores termination and needs kill/reap. They use controlled
local executables, not the model service. Ordinary Ubuntu CI also runs eight task-predicate and three evaluation-command
regressions with the `vision,evaluation` extras; fixture tests do not establish visual-model qualification.
One final macOS/MPS seed0 run used three real visual proposals at sequences0/400/450,
completed400+50 steps in the same episode, delivered two settled Core receipts and
retained451 video frames. The fixed independent evaluator passed the one-second
window; all native/model processes exited. This single-seed normal result does
not establish visual reliability or physical-robot support.

The installed application also completed a new macOS/MPS seed0 run from outside
the source checkouts, using the bundled default worker, a new locked skill
environment and newly downloaded/migrated weights. It completed400+50 steps,
retained451 frames, passed the same independent task evaluator and reaped all
five native/model processes. This reused the qualified Harness installation;
it is not a clean-machine or Linux reproduction. Migration preserved all234
learned tensor keys/values. The preparation path uploads nothing.

[`workspace.repos`](workspace.repos) pins the Harness dependency. Use the Agent
commit alongside that exact revision. The dependency now includes strict candidate
identity validation: consumed JSON fields must match both type and value, while
unrelated optional metadata is allowed.
A fresh installed combination of the unchanged Agent runtime source (`3482858`)
and Harness `0de9eb0` passed all30 application tests on macOS and Linux. A new
offline Ubuntu22.04 ARM64 CPU/OSMesa task used the bundled default ACT worker and
explicit deterministic proposals. It completed400+50 steps, two delivered/settled/
released receipts,451 decoded frames and observed process cleanup in38.853 seconds.
The same-run fixed physical evaluator passed the bounded one-second hold; the
application task verdict remained `unassessed`. This verifies normal consumption
of the new pin, not a new visual-model qualification or a performance benchmark.
Earlier visual results below used Harness `3acc9aa` and retain their original scope.

The first normal-task increment is merged as `06cbee4`; M5e adds a Linux consumer
environment. Its deterministic ACT/MuJoCo
path passed a fresh Linux environment/build, seed0 normal execution,451-frame
recording, same-run fixed physical evaluation and native process reaping. This
deterministic result remains separate from the visual application. A later
installed Linux CPU/OSMesa visual run completed three real camera-based proposals,
400+50 steps, two settled receipts,451 decoded frames and process exits; its
same-run fixed physical evaluation passed. See the
[Linux scope](skills/aloha/README.md#linux-consumer-path). No physical-robot
qualification, continuous robot safety, Host restart recovery or hard stop bound.

A seed0 Linux research counterexample then relocated only the cube to the table
before native step 400, preserving robot state and simulation time. Actual MuJoCo
rendering supplied the new image; fault labels/physics truth were excluded from
the model input. The same visual backend chose `help`, and the task reported
`needs_help` after 48.657 seconds, with one settled 400-step transfer, zero hold
submissions/steps, 401 decoded frames and observed process cleanup. The fixed
whole-task evaluator remained `unknown` without an executed hold window;
`task_verdict` remained `unassessed`. This is one explicit simulator disturbance,
not a naturally occurring drop or a general perception/safety guarantee. Two
prior fixture setup failures are retained separately. The trusted research
fixture is outside this repository and is not a supported plugin API. Slow,
cancelled/late decisions have separate selected checks below. The
[selected native comparison](https://github.com/xiao-yang25/robot-harness/blob/0de9eb0ee9de670adc22abc34ae294ea6a486dcd/docs/TESTING.md#m5f-task-owner-comparison)
covers the declared task/control scope; broader fault qualification remains open.

Two later Linux seed0 temporal cases each used a declared deterministic initial
transfer proposal and the real ACT/MuJoCo runtime, then exercised the decision at
sequence 400. An actual Codex0.159.0 client emitted `turn.started` and was cancelled;
the task reported `cancelled` after 36.628 seconds and reaped the client. This
establishes local client cancellation, not remote model acceptance or termination;
an optional Code Mode host error was retained, and no model turn completed.
A separate controlled CLI exceeded a one-second decision budget, wrote a valid
bound `hold` answer while handling termination, and exited normally. That answer
was retained without being accepted, and the task reported `needs_help` after
35.574 seconds. Each case retained one delivered/settled/released 400-step transfer,
zero hold submissions or hold steps, 401 decoded frames, and no remaining sampled
related processes. They are temporal-boundary checks with mixed callers, not two
complete model-driven tasks or whole-task successes; `task_verdict` stayed
`unassessed` and no complete-hold physical evaluation was run.

The proposal adapter checks cancellation and expiry again after process exit;
process completion cannot restore a withdrawn proposal. These remain cooperative
checks with terminate/kill/reap, not a hard physical stop deadline, guaranteed
termination of every descendant, or recovery from a dead Host. The selected
comparison found overlapping wall-time ranges and reusable execution/task
responsibilities, without establishing general speed, memory or net development
time benefits. The pinned combination merged through PR5 as `c3b291c`, with a tree
identical to reviewed `8f38cd0` and passing main Ubuntu30-test/installed-entry checks.
M5f and the selected M5 task scope are delivered; broader qualification remains
open. The next phase selects one heterogeneous combination and tests reuse.

## License

License and contribution terms remain pending, matching the current Harness
status. Do not treat repository creation as a license grant or preview release.
