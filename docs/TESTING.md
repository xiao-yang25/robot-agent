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
physical stop or task success.

An additional [public CLI signal case](../tests/combination/test_navigation_cli_installed.py)
starts the installed `navigation_cli` process and sends SIGINT after the trusted
fixture accepts B. It requires explicit cancellation of exactly B, revoked
authority with pending settlement, two accepted proposals and no final proposal,
honest unknown cleanup, reaped children and owner/socket cleanup. The fixture
uses synthetic native/pose facts; this is a process and installed-interface check,
not a physics experiment. The signal check joins the original five cases; the
existing workflow discovers the new test without a separate CI job. The additional
[proposal fault cases](../tests/combination/test_navigation_proposal_installed.py)
exercise the installed CLI's actual prepare/after-A/final decision boundaries:
a tool event before A has zero admissions, help after A has no B admission, and
a final child that writes a valid answer while terminating after the original
30-second deadline cannot complete the task or release pending B. Native results
already accepted remain accepted after exact B revocation. All owned children,
owner and socket must be cleaned up. The additional
[controlled tutorial case](../tests/combination/test_navigation_demo_installed.py)
uses the installed tutorial proposal executable through the public CLI, requiring
three accepted decisions, A settled/released, B accepted/pending and reaped children.
Discovery includes ten combination cases; these controlled tests do not run
physics or a remote model service.

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
`13bc75e903f6005da3dd5d969f8242ce211d182f`. Do not generalize older results to
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

The M6b delivery pinned merged Harness `6f32578`, including the public
navigation entry. Its fresh installed combination check covers navigation and
ALOHA separately from these earlier live model/simulation runs; the dependency
update does not repeat physical or model qualification. Hosted results belong to
the exact Agent commit in Actions. Proposal failure at the actual decision call
sites were subsequently checked below; external reproduction retains its own next step. The bounded public
CLI motion-interruption candidate is recorded separately below.
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

## M6b paired installed delivery

That delivery pinned Harness `6f32578f8d9157fa7c26c1f4e2ece13e05ec6211`.
The delivered application suite passed 56 checks on macOS; a fresh Agent wheel and
Harness optional bridge installation passed all five combination checks outside
both source trees. The owner fixture's process/socket cleanup was observed.
That delivery's Ubuntu CI ran the same installed cases against the then-fixed
dependency; check Actions for that historical Agent commit's hosted result. These checks preserve
ALOHA and public navigation consumption without repeating ACT, model or physics
qualification. Additional fault scope and external reproduction remain separate.

## Public CLI interruption candidate

The local M6c candidate adds one installed CLI signal test; all six installed
combination checks passed on macOS against the prior `6f32578` Harness pin. The three
navigation combination checks also passed against installed packages in the
retained Ubuntu 22.04 amd64 environment. These were pre-delivery local checks;
hosted qualification belongs to the exact Agent commit in Actions.

Two separate Ubuntu 22.04 / Humble amd64 Gazebo runs consumed the installed public
Agent CLI with controlled executable proposals. A settled/released before B;
after B was natively accepted and moved over 0.5m, the CLI received one SIGINT.
Both runs observed explicit cancellation of exactly B, Core revocation, native
cancel scheduling, a sealed drive/wheel-zero ACK, and continuous rejection of old
B commands during an independently observed quiet window. Each run had one
offline evaluation; a focused independent review approved only this scope.

The recorded run's window contained 36 fresh odometry samples over 3.502 simulated
seconds; independent endpoint observations differed by approximately 0.000083 m
and 0.00247 rad. The Agent exited with status 1 and reported cancelled, without a
third proposal or new goal.
Both proposal children were reaped; the owned containers were removed. Subsequent
status/close connection failures remain in the report: task verdict unassessed,
native cleanup unknown and settlement pending. The first recording attempt
failed native preparation before any admission; its diagnostics remain retained.

This establishes a finite business-signal consumption path under a live owner.
It does not qualify real model failures, complete native closure, Owner loss,
hard stopping deadlines, other robot embodiments or physical hardware. The
[same-run video](https://xiao-yang25.github.io/robot-harness/#agent-stop-demo)
was subsequently published; its recorded version and limits remain unchanged.

## Proposal failure candidate

Three additional installed public CLI cases exercise the actual decision calls:
prepare rejects tool-event output before any admission; after_a help retains
released A without submitting B; final exceeds the original 30-second deadline.
The last child returns a valid, matching answer while handling termination and
exits 0, but the expired proposal is not accepted. The task requests cancellation
of exactly the retained B. Its accepted native result survives revocation with
settlement pending. These are controlled executable providers, not remote model
failures or concurrent decisions during robot motion.

All nine installed combination cases passed on macOS against the prior
`6f32578` manifest pin. The three new proposal cases also passed in the retained Ubuntu
22.04 amd64 environment. The fixture's own lifetime is 45 seconds only for the
late-proposal case, to cover the unchanged application deadline. CLI, owner and
proposal children are owned and reaped; the socket is removed. Existing Ubuntu
combination discovery includes these cases; the candidate has no new hosted result.

A separate Humble/Gazebo run exercised final lateness with actual Nav2 A/B visits
and a matching local Harness owner fix. The first run exposed a defect: after
native sequence completion, explicit B cancellation was misclassified as an
authority error. The corrected owner passed 12 focused checks, including that
regression and preservation of normal terminal close. A new run passed one
same-run evaluation in 108.362 seconds, with independently observed A/B distances
0.198780/0.159009 m. Only two decisions were accepted; the valid late final answer
was rejected and all three proposal children exited 0 and were reaped. The Agent
exited 1 with needs_help; the owner and container exited 0. B remained native
succeeded/output accepted, authority revoked, settlement pending; task verdict
unassessed and native cleanup unknown. Subsequent status/close connection failures
remain in the report. The failed first run is retained without reevaluation.

The real simulation consumed the then-local Harness fix rather than the older
`6f32578` owner. That exact source tree is now delivered in Harness
[`ea7b1eb`](https://github.com/xiao-yang25/robot-harness/commit/ea7b1eb1a075cd91ef590475f2496a48d19ca52a).
Agent runtime source is unchanged; the updated pairing is checked below. A local 71.7-second same-run video retains the full
30-second wait; it is now [published](https://xiao-yang25.github.io/robot-harness/#late-proposal-demo).
This scope does not qualify model-service
reliability, Owner loss, complete native closure, hard stop or physical hardware.

## Updated fixed pairing

[workspace.repos](../workspace.repos) pins delivered Harness
`ea7b1eb1a075cd91ef590475f2496a48d19ca52a`, including the final cancellation fix.
A fresh macOS ARM64 Core build and optional-package install, together with a newly
built Agent wheel, passed all nine installed combination checks outside both
source trees. All 56 application checks also passed against that installed Agent.
The combination retains the three ALOHA and two normal/navigation-help cases,
adding the public CLI SIGINT case and three selected proposal faults. These use
controlled native/model edges and do not repeat physics or model qualification.

The existing Ubuntu combination workflow discovers all nine cases against this
immutable Harness dependency; the application workflow retains its 56 checks.
Actual hosted results must be checked for the exact delivered Agent revision.
The delivered `ffad065` application and combination workflows passed the 56/9
checks; these are software-boundary results, separate from the recorded simulation.
No reciprocal Harness Agent pin is changed. Subsequent comparison, reproduction
and presentation are recorded below, separately from these installed checks.

## M6c delivery audit

Selected live-owner interruption and proposal-failure paths, same-strategy native
normal/late-proposal comparisons, and a fresh installed public-version normal run
have bounded research evidence. The fresh run fetched this application's
`ffad065` version and its immutable Harness `ea7b1eb` dependency, used new Linux
build/install directories in an existing Ubuntu22.04/Humble image, and exercised
three controlled proposals through the installed CLI. It did not rebuild the
entire ROS image or repeat live-model qualification. Failed preparation and
evaluation attempts were retained separately. The published videos above are
distinct runs, rather than evidence for this new installation.

That reproduction used research-only launcher selection, controlled proposal
and passive-observer tools. The new [controlled business tutorial](../examples/navigation/README.md)
provides public preparation, launch and report inspection using the existing
Harness supervisor and installed Agent CLI. The fixed new installation and
controlled native run are qualified below; the host-to-container real-model path
remains pending. Navigation has no installed physical evaluator;
`robot-agent-evaluate-handoff` applies only to ALOHA. CLI completion and an owner's
process-completion verification file cannot prove physical task success.

Later Harness startup diagnostics in `03a357b` preserve the original service and
context budgets and report individual child failure. The new manifest includes
those diagnostics, trusted-client launcher and bounded B startup ordering in
`13bc75e`; older recorded
results retain their original versions and scope.
GetState preparation-timeout cause, Owner loss/restart, full native cleanup,
hard stop, hardware and general reliability remain unqualified. Application
license/contribution terms and a versioned preview remain pending separately.

## Public controlled navigation workflow

Fresh GitHub checkouts of Agent `721140b` and its fixed Harness
`13bc75e903f6005da3dd5d969f8242ce211d182f` exercised the published wheel, Linux
preparation and launch commands. New Core and Agent installations used an existing
qualified Ubuntu22.04/Humble amd64 image with Python3.10 headers; this did not
rebuild the entire ROS image or test the optional header-download branch.
The Linux Python Session check passed; exact-candidate hosted CI passed ten
installed combination and 56 application checks. The preceding installation also
passed ten local Linux combination cases, separately from physics.

The final controlled scene had three accepted/reaped proposals, A settled/released
before B admission, B accepted/pending, and unknown native cleanup. The public
launcher exited zero without OOM and removed its container. A separate passive
Gazebo observer and one offline evaluation measured A/B errors of 0.188/0.169m
against the unchanged 0.35m predicate. These observations never drove decisions
and do not change the application's unassessed task verdict.

Two earlier attempts failed safely with zero admissions during B startup discovery.
The fixed Owner now waits for its startup endpoint inside the original 70-second
context deadline before the original bounded RPC checks. An intermediate run
completed publicly but its research evaluation failed to import a helper; it was
retained as incomplete, rather than reevaluated as pass. The final run is separate.
No live model, hardware, general reliability or full native cleanup is qualified.
Published videos retain their own recorded versions; no new video is claimed
for this packaging increment. The public real-model path remains M6c delivery work.
