# Robot Agent

Bounded, observation-driven task applications for
[Robot Harness](https://github.com/xiao-yang25/robot-harness). Experimental project;
the first application is delivered through pull-request review. No release yet.

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

Python3.10+; lightweight task tests require only the standard library:

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
```

For the real task, follow [ACT / ALOHA setup](skills/aloha/README.md). It provides a
Mac arm64 dependency lock, bundled ACT worker, explicit pinned model download and
offline migration commands. [`workspace.repos`](workspace.repos) pins the Harness
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

Locally qualified: 17 task-control tests and five preparation-boundary tests,
plus focused independent code reviews, passed.
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
commit reviewed in the pull request alongside that exact revision. M5d delivery
is subject to review/merge; full clean-consumer and Linux model/render reproduction
belong to the next stage. No Linux ACT or physical robot
qualification, continuous robot safety, Host restart recovery or hard stop bound.

## License

License and contribution terms remain pending, matching the current Harness
status. Do not treat repository creation as a license grant or preview release.
