# Testing and qualification

The [task contract](../README.md#task-contract) defines application behavior.
A model assessment, a settled execution receipt and an independent task verdict
are different results.

## Automated checks

Python 3.10+. The full suite needs the `vision,evaluation` extras but no ACT,
MuJoCo, weights or authenticated model service:

```sh
python -m pip install '.[vision,evaluation]'
PYTHONPATH=src python -m unittest discover -s tests -v
```

[Ubuntu CI](../.github/workflows/agent.yml) checks task-control, preparation,
proposal subprocess and evaluator boundaries, plus installed CLI entry points.
Cases include stale observations/answers, cancelled or expired decisions, invalid
proposals, pending/failed settlement, ambiguous submission, no replay and explicit
reset for another task. Controlled subprocesses exercise late-answer rejection
and terminate/kill/reap behavior; they do not qualify a remote model service.

[Installed combination CI](../.github/workflows/combination.yml) installs Agent
and the real Harness dependency, then tests outside both source trees. Its
[three cases](../tests/combination/test_installed.py) cover normal transfer/hold
with distinct settled receipts, help after transfer and rejection of an old
hold answer. Camera/action/recording and policy providers are explicit no-physics
fixtures. Session, Host and Core are real; ACT, video, perception and physical
success are outside this check.

[Two navigation cases](../tests/combination/test_navigation_installed.py) consume
the installed public Unix Session and real trusted-owner requests/coordinator/Core.
A subprocess fixture supplies synthetic pose, native outcomes and settlement
facts; the controlled proposal backend receives only declared measurements.
The normal A→B path requires distinct native identities and fresh references,
A settled/released, B accepted/pending, and unknown close outcome. Final help
revokes and schedules stop for exactly B once, without inventing settlement.
Each case checks owner process exit and socket removal. Private Core/coordinator
imports are confined to this trusted-owner test fixture, not the business Agent.
These checks do not run ROS, Nav2, Gazebo or a model service, and do not establish
physical stop or task success. Discovery runs all five combination cases.

Agent changes use the Harness revision in [workspace.repos](../workspace.repos).
Harness changes call this reusable workflow with a fixed Agent revision and the
candidate Harness revision. See [Actions](https://github.com/xiao-yang25/robot-agent/actions)
for results of a specific commit. Configuring a workflow does not prove it passed.

## Independent evaluation

The package ships one [fixed predicate](../src/robot_agent/handoff_profile.json)
and [evaluator](../src/robot_agent/evaluate_handoff.py). In the same pinned
[ALOHA skill environment](../skills/aloha/README.md), after the task has closed:

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

## Qualified scope

| Recorded check | What it established |
|---|---|
| macOS arm64/MPS and Linux aarch64/CPU/OSMesa visual task | One seed-0 normal task per recorded environment, with camera-based proposals, 400+50 steps, two settled receipts, 451 decoded frames, independent finite-hold evaluation and observed process exit. |
| Linux simulator disturbance | One explicit cube relocation led the real visual backend to request help after transfer, with zero hold submissions. The whole-task evaluation remained unknown without a hold window. |
| Linux cancellation/late answer | Selected mixed-caller checks rejected a cancelled or expired follow-up proposal after transfer. These were not complete model-driven task successes. |
| Prior `0de9eb0` Harness combination | A fresh installed macOS/Linux test combination and deterministic Linux ACT/MuJoCo run passed normal consumption and the finite-hold evaluator. This did not repeat visual-model qualification. |

Earlier real visual checks used Harness `3acc9aa`; the current manifest pins
`6f32578f8d9157fa7c26c1f4e2ece13e05ec6211`. Do not generalize older results to
arbitrary dependency updates. New qualification must retain actual model inputs
and answers, same-run progression/video/trace, separate evaluation and external
process-exit evidence. Report help, failure or unknown honestly.

These results do not establish visual reliability, arbitrary weights, CUDA or
other architectures, physical-robot safety, Host restart recovery, continuous
control or a hard stopping deadline. Cleanup/settlement depends on a live,
polling owner and return from executing native calls. No general performance or
development-time advantage has been established.

Exploratory reports and raw evidence remain outside the product repository.
Public reports should state the tested combination, conditions, result and limits
without exposing private prompts, machine configuration or operator paths.


## Local M6 Harness candidate compatibility

The unchanged installed application also completed a deterministic CPU ACT / MuJoCo
normal task against the local M6 Harness candidate with the extracted execution
coordinator: 400+50 steps, observations 0/400/450, two accepted/settled/released
receipts, 451 decoded frames and observed process exit. The existing evaluator
ran once and reported finite-hold success; `task_verdict` remained `unassessed`.
The candidate's 56 Session/Core, this application's 41 checks and the three
installed no-physics combination cases passed locally. This is candidate
compatibility with the prior dependency, without new real visual-model
qualification. That check preceded the navigation increment and paired
[dependency update](../workspace.repos) recorded below; the ALOHA task contract
remains unchanged.


## Navigation candidate qualification

The local Agent candidate adds 15 application/proposal checks to the existing 41.
Final macOS and installed Linux ARM64 suites passed all 56; three installed ALOHA
combination checks also passed. Navigation cases reject mutated/stale/changed or
late/cancelled proposals, unknown submissions without retry, mismatched/revoked
native results and unresolved A settlement; final B help retains cancellation.
Actual child-process checks cover text-only output, tool refusal, timeout/reaping
and a hanging version probe. Startup time is included in the task budget.
The Ubuntu workflow discovers these tests and checks the installed CLI help.
Its result must be checked for the exact delivered Agent commit.

A fresh installed navigation application consumed the matching local Harness
candidate in isolated Ubuntu22.04/Humble amd64 simulation. Codex0.159.0 requested
`gpt-6-sol` / high for three actual text proposals: visit A, visit B and observation
complete. Model input was only task context and public map pose/time/sensor health.
The model ran on the host; the network-disabled 2 CPU/4 GiB simulation container
received no authentication material. The experiment relay is research-only.
The task finished in 87.722 seconds under the 420-second scene budget. One separate
physical evaluator confirmed A/B distances 0.205273/0.173651m. A settled/released
before B admission; B output accepted with settlement pending. All three proposal
CLI children and the model server exited and were reaped; the container exited0,
without OOM, and was removed. The application kept `task_verdict=unassessed`,
`execution_cleanup=pending` and `native_cleanup=unknown` after local connection close.

The first actual task timed out at its initial 30-second proposal budget, before
any navigation admission. Its logs and unknown close outcome remain; model child
and container were removed. A same-input, same-budget host proxy-path diagnostic
returned a proposal in 8.945 seconds, without any robot submission; a new isolated
task then passed. This supports using that tested path locally, not a proven exact
cause for the original timeout or a general model-service reliability guarantee.
No wait, freshness or physical criterion was loosened. First bare-interpreter
checks lacked the declared test extras; later fixture PATH failures were fixed by
using the actual test interpreter. All failed logs remain distinct from final checks.

The public manifest now pins merged Harness `6f32578`, including the public
navigation entry. Its fresh installed combination check covers navigation and
ALOHA separately from these earlier live model/simulation runs; the dependency
update does not repeat physical or model qualification. Hosted results belong to
the exact Agent commit in Actions. Navigation fault/model-abstention in real motion
and external reproduction retain their own next steps.
Independent code, raw-boundary evidence and focused final documentation reviews
received bounded approval; controlled tests and the single normal run
do not establish general task reliability or hardware safety.

An additional recording found the matching owner default final-close wait (10s)
was shorter than this application's proposal limit (30s): a roughly10.03-second
reply returned after the owner aborted. The failed needs-help/unknown report and
clean recording cleanup remain retained. The owner now offers explicit bounded
caller idle waits; this model consumer chooses45 seconds, including public RPC
allowance. Neither application budget nor native/freshness/physical limits changed.
A new installed Harness candidate passed60 Python/Core and10 owner checks; the
unchanged installed Agent then completed a recorded normal task in107.642 seconds,
with three actual proposals and A/B distances0.192253/0.166768m under one separate
same-run evaluation. A released, final B pending, task verdict unassessed and
cleanup unknown remain. This later recording has its own candidate scope and
[public presentation notes](https://github.com/xiao-yang25/robot-harness/blob/master/docs/assets/demo/README.md).
That recording does not itself establish hosted CI or paired public delivery.

## Paired installed delivery

The manifest pins Harness `6f32578f8d9157fa7c26c1f4e2ece13e05ec6211`.
The current application suite passed 56 checks on macOS; a fresh Agent wheel and
Harness optional bridge installation passed all five combination checks outside
both source trees. The owner fixture's process/socket cleanup was observed.
Ubuntu CI executes the same installed cases against this immutable dependency;
check Actions for the exact Agent commit's hosted result. These checks preserve
ALOHA and public navigation consumption without repeating ACT, model or physics
qualification. Real-motion fault scope and external reproduction remain separate.
