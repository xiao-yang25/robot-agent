# Testing and qualification

## Proposal input and exit checks

The private proposal transport accepts at most 1 MiB of UTF-8 prompt data before
launching a child. Nonblocking, partial pipe writes preserve the full input and
EOF while checking cancellation and the original deadline under backpressure.
The owner retains terminate, timed wait, kill and reap responsibility. Proposal
acceptance checks cancellation and expiry again after JSON decoding.

[Local subprocess regressions](../tests/test_proposal_input.py) exercise a delayed
reader with Unicode input, a child that never reads a large prompt, oversized
UTF-8 rejection before launch, and cancellation/expiry at completed decoding.
They check actual child reaping as well as the returned result. The existing
Ubuntu application workflow discovers these tests; configuration alone is not
an executed Ubuntu result. These checks do not establish a hard exit bound for
process launch, filesystem operations, parsing, descendants or robot motion.

The local macOS/Python 3.12 run passed all six new regressions and 154 application
tests. Focused independent review approved this repair and separately ran the
six regressions plus fourteen existing proposal-adapter tests. This is a local
software result; no new model, robot or Ubuntu qualification is implied.

## Automated platform coverage

[Application CI](../.github/workflows/agent.yml) retains the Ubuntu 22.04/Python
3.10 `test` job and adds macOS 15/Python 3.12 `macos-test`. Both discover the full
application suite, including controlled proposal input, signal and process cleanup
checks; both jobs have a ten-minute execution limit. This limit bounds CI work,
not robot stopping. The Ubuntu job also checks installed command entry points.

[Installed combination CI](../.github/workflows/combination.yml) remains the
separate Ubuntu check for the pinned Harness Core and Session plus installed
Agent consumption outside both source trees. Application tests do not replace
that installation boundary or physical/model qualification. Hosted Ubuntu and
macOS application checks passed for the prerequisite input repair;
subsequent implementation changes require their own accurate-revision checks.
The private coordinator adds deterministic handoff/navigation regressions below.
ALOHA adds its normal, budget and cleanup cases below;
workflow configuration alone does not establish coordinator behavior.

## Private event consumption

The private one-source [event inbox](../src/robot_agent/_task_events.py) retains
one latest immutable metadata reference, one stop latch and the first failure.
Duplicate/older updates cannot roll its identity back; a generation change
invalidates this task rather than restarting it. It stores no frame bytes and
does not establish source freshness, clock relationships or payload borrowing.

`Coordinator.begin/poll` provide nonblocking enqueue/consumption on the caller.
A finite turn processes control/faults before completions and at most one latest
update. Policies interpret completions and perform action admission; a collected
call is not automatically an accepted proposal. The optional fixed-navigation
adapter pumps these turns while its model or I/O owner waits. Its event source
represents navigation context; failures cause help and original-request cancel.
A camera independent of navigation needs the inspection policy's separate
dependency handling, which is not implemented here.

[Event tests](../tests/test_task_events.py) include two actual blocked owners,
independent I/O completion, metadata bursts, stop/fault priority, generation and
association invalidation, completed-but-unconsumed proposal withdrawal, deadline
expiry, callback failure preserving accepted effects, and original navigation
cancellation before a blocked model exits. They do not measure sustained video
throughput or a real-time bound. Local macOS and Linux/Python 3.12 application
regressions each passed 208 tests, including 13 new cases; focused independent
implementation review found no remaining blockers in this software slice.

The [installed navigation checks](../tests/combination/test_navigation_runtime_installed.py)
also consume a newly installed Agent outside source trees with the retained pinned
Harness, actual Core/Session/socket and synthetic native facts. All five selected
checks passed, including event invalidation with exact B request/operation/goal
identity, revoked authority, pending settlement and unknown native cleanup.
This is not a new full combination build or physical cancellation qualification.
Existing application and combination CI discover these additions automatically;
accurate-revision delivery results are listed below. Public commands and the dependency pin
remain unchanged. A separate offline Humble/Gazebo stationary-source probe captured
25 actual RGB640×480 samples in each normal-A/abnormal-B scene, with recorded
clock/CameraInfo/AMCL and image-time map/base TF. Fixed quality checks rejected
the earlier grey-border fixture; invalid focal lengths are rejected after review.
This research feasibility does not exercise this Agent task or its public API,
arrival, source health during model waits, frame borrowing or cancellation.
Later source/binding software checks appear below; complete camera inspection
task qualification remains pending.

## Private inspection history and health

[Source tests](../tests/test_inspection_source.py) exercise the private
[inspection source](../src/robot_agent/_inspection_source.py), existing inbox and
actual gated Model Owner. Controlled clocks distinguish a normal closed window
plus10-second decision wait from real source silence/paused clock/generation or
association invalidation. Source failure withdraws the old proposal but preserves
original independent I/O. Tests cover immutable producer snapshots, read expiry
and release, conflicting/unknown results, maximum-two-window behavior, old-frame
rejection and malformed/overflow inputs. They do not run a real model or prove
live source health, throughput, action admission or a hard stopping bound.

Final focused17 checks, macOS/Linux Python3.12 application225 checks each, and17
checks against a freshly installed package from outside source trees passed.
Independent review reproduced and closed pose snapshot/input-failure defects,
including numeric overflow; final scoped software approval is separate from ROS
integration. Existing application CI discovers these checks automatically;
accurate-revision CI results are recorded in the delivery summary below. Public entry points,
Harness pin and prior task consumers remain unchanged. Subsequent private ROS
source binding is qualified below; complete inspection policy remains pending.

## Private fixed-navigation coordinator

The experimental `python -m robot_agent._navigation_runtime` entry uses the
private coordinator/owners and original fixed-navigation policy. Public task
commands, checkpoint/revision/recovery paths and the Harness dependency pin are
unchanged. ALOHA reuse and its domain-specific close are described below.

[Handoff tests](../tests/test_task_runtime.py) choose claim/stop/withdraw/close
ordering with Events and the exchange Condition. They exercise zero invocation
before claim, retained effects after claim, request withdrawal without task
restart, bounded completion retention, close independent of consumption, mutable
input isolation, initialization/close errors and draining non-daemon owners.
[Navigation tests](../tests/test_navigation_runtime.py) preserve normal A→B,
stale-observation refusal, original-request unknown/cancel, original budget,
partial initialization and close error. Closing regressions include an exception
before disposal and a lost reply after fixture disposal. Both retain the error,
report connection disposal as unknown and keep resources_closed false; thread
exit alone cannot establish disposal. Normal close still reports local_closed
while native cleanup remains unknown. The two error cases failed on the previous
report mapping and passed after its correction. These are software fixtures,
without sockets, remote shutdown or physics. Existing application CI discovers
the regression automatically.
An unfinished submit retains its original
request ID, site and observation reference even when closing wait expires.
A blocked final decision stays blocked
while the business coordinator requests the original B cancellation.

[Installed checks](../tests/combination/test_navigation_runtime_installed.py)
consume the new Agent package outside source trees through the real public
NavigationSession and Core. Native facts and proposals are controlled fixtures,
without ROS, a model or physics. They cover normal A release/B pending and the
actual module CLI under SIGINT while its final proposal child ignores TERM;
the child is killed/reaped and Owner/session/thread cleanup is observed.

Local macOS/Python 3.12 checks passed 17 new unit scenarios, 171 application tests
and two new installed scenarios. The local installed run used a new Agent wheel
with the retained Mac Harness installation; it is not a fresh native build
qualification. Existing application and installed-combination workflows discover
these tests automatically. Hosted checks, selected simulation/video and any
public-default migration remain separate requirements. No physical stop,
arbitrary-plugin exit, restart recovery or new model qualification is implied.

## Private ALOHA reuse

The experimental `python -m robot_agent._handoff_runtime` path reuses the same
handoff, call facade, Session binding and owner assembly as fixed navigation.
HandoffTask retains its original policy and camera/joint whitelist. Both actual
task policies still consume their distinct observations and release criteria;
public commands, other task variants and the fixed Harness pin remain unchanged.

[ALOHA regressions](../tests/test_handoff_runtime.py) cover400/50 steps with both
releases, changed episode/new measurement zero-hold, pending transfer zero-hold,
stop while a decision is blocked, effect-before-stopped-response, short closing
expiry retaining original request/skill/steps/observation, original operation
budget including caller delay, prestart stop/expiry and initialization/close
errors. A stopped observation returning late must still produce a JSON report: its
binary RGB is explicitly omitted and labelled, while observation and call identity
remain available. This report record is not a reusable model observation.
Resource factories/methods/close execute in their sole owners. A released
transfer requires no cancellation at the decision boundary; an unfinished
submission is reconciled/cancelled only through its original request.

[Installed checks](../tests/combination/test_handoff_runtime_installed.py) use
actual Session/Host/Core with controlled action/environment and proposal fixtures.
They check450 actual recorded steps and correlated released receipts, stale
answer zero-hold, and actual module SIGTERM during image decision: zero hold,
TERM-ignoring proposal child killed/reaped, and Host/worker PIDs absent after
close. PNG preparation uses the existing vision extra; combination CI now installs
`.[vision,evaluation]` and automatically discovers these tests plus navigation.

These are software/installation checks. No MuJoCo dynamics, ACT inference,
business model, simulation video or hardware stopping is qualified. Selected
actual execution/video and public-default migration remain separate gates.
The30-second ALOHA closing wait is a software budget; unfinished owners stay
non-daemon and explicitly draining, and cleanup failure cannot become confirmed.

Local macOS/CPython3.12.14 passed182 application tests (eleven new ALOHA cases) and
five selected installed cases: three new ALOHA plus two navigation regressions
after the shared extraction. A new Agent package was installed outside source;
the local Core binary is retained, not a fresh native build qualification.
Independent implementation review approved the limited software slice and ran
27 focused cases plus five installed cases, then separately approved and ran
the additional late-RGB regression. Hosted accurate-revision checks remain
separate from these local results.

## Selected shared-coordinator physics checks

A local Linux run consumed Agent `f708afa` source-package installations and the
fixed Harness `4b4bc5b` dependency, with retained native installations. It ran
controlled business proposals against actual CPU ACT/MuJoCo and
Ubuntu 22.04/Humble/Nav2/Gazebo; no LLM or VLM was invoked.

Three selected scenes passed their original checks: ALOHA transfer400/hold50,
ALOHA stop during the post-transfer decision with zero hold, and navigation A→B.
The two normal scenes each used their existing offline physical evaluator once.
ALOHA held the cube for one simulated second; navigation arrival errors were
0.204 m at A and 0.153 m at B, within the fixed 0.25 m threshold. Same-run normal
videos were fully decoded and representative frames inspected. ALOHA stop closed
its Session before the late decision returned; sampled consumer-family processes
were absent after exit. These are limited simulation observations, not model
reliability or hardware stopping guarantees.

The navigation final-decision stop scene **did not pass** its closing gate.
Cancellation acknowledged the original B request and revoked its authority;
settlement stayed pending and native cleanup unknown. In the existing default
profile, cancellation enters Owner shutdown. The subsequent status query lost
its connection, and Session close raised a connection error. The report retained
those errors and `resources_closed=false`; no new operation was submitted and
the late decision was not accepted. Container removal does not upgrade this
result to confirmed cleanup. The four-scene batch and public-default migration
remain open pending review of domain-specific cancellation/closing semantics.
No retry or acceptance-predicate relaxation followed this failure.

The initial navigation recording attempt used an image without `xvfb-run` and
failed before physics. Its evidence was retained; an existing recording image
passed a new prerequisite check before the fresh navigation scenes. All owned
containers were removed, with no new images, dependencies or credentials.

## Single-backup software checks

The opt-in `RecoveryNavigationTask` consumes Harness `9278fea` from
[workspace.repos](../workspace.repos). The preview tag and its older dependency
stay immutable. The initial software batch added the Python task and text-proposal
schema without a public recovery simulation command or new model/physics pair.

Application checks cover A-only success, pending versus confirmed failed-A
no-output release, one fresh backup, help, backup failure without another
recovery, foreign failure/proposal identity, changed scope/goal/original deadline,
missing/cancelled/expired facts, failed-outcome regression, ambiguous submission,
input/readiness loss, global stop and unrefreshed budgets. A real controlled
proposal child exercises the failure context/schema and is reaped. Other
navigation and ALOHA tests remain enabled.

Installed checks use the actual public Unix Session and newly compiled Core,
with a CI-only Owner providing synthetic measurements/native closure. They verify
real Core failed/no-output/pending versus settled/released, one B after release,
help/foreign identity with no B, A-only success, exact B cancellation after
backup failure and caller connection/process teardown. These checks do not prove
ROS closure, physical arrival or a hard stop. Both Ubuntu workflows already
discover these cases; no duplicate job is needed.

Local macOS application checks passed 122 cases, including 15 new recovery
cases; the fresh wheel/Core installation passed all 31 combination cases.
The same wheel and a fresh Core install in the retained Ubuntu 22.04/Humble amd64
image passed all 31 combinations and the 15 recovery application cases offline.
The first container invocation used the wrong default scene entry; the next
precheck unnecessarily requested unavailable Pillow for these no-image checks.
Both preparation failures remain recorded; no test assertion was relaxed.

The map-binding increment keeps that default dependency and scene identity.
Its explicit `expected_map_id` checks reject capability/measurement/reference
mismatches and a map change after the failure proposal. All 124 macOS application
checks and 31 installed combinations pass; the offline Humble image passes 31
installed combinations and 17 recovery application checks. These software
results do not by themselves establish arbitrary-map or physical qualification.

Seven controlled operator scenes then exercised the installed task and public
Session with the fixed Harness in Ubuntu 22.04/Humble/Nav2 1.1.20. A-only success
finished 0.205m from A; accepted/failed A was actually closed and released before
one B, which finished 0.228m from B. Released-A help, actual paused successor
readiness, foreign failure proposal and global stop all issued zero B. A separate
static map with both goals occupied and explicitly zero planner tolerance produced
native B failure without another recovery. Static occupancy does not prove a real
physical obstruction or general unreachability. Each scene had one evaluation;
initial evaluation/startup/fault-preparation failures remain separate incomplete
records. This qualifies controlled proposals in those scenes, not an actual model,
host relay, public recovery command, video, hardware or a hard stopping limit.
Full Ubuntu application checks and exact-candidate hosted results are separate
delivery checks. A new paired task/model/video must be recorded separately.

The model transport increment adds explicit installed CLI recovery mode and a
host worker bound to that task/map. Whitelist checks reject foreign task/failure
request/operation/goal/outcome and reference identity; optional metadata is
ignored. The prepared-owner wrapper forwards task/map/client selection and reaps
its actual host/launcher groups. New installed host/relay/CLI/Core cases cover
normal A-only and failed-A release before one B, with controlled proposals.
Local macOS application checks passed 127 cases; all 33 installed combinations
passed on macOS and Ubuntu 22.04 amd64. The offline image also passed all 18
host/relay application cases. Full Ubuntu application results belong to the
exact candidate in the existing Actions workflow.

The same new wheel was installed into separate host and Linux prefixes and
compared directly with current runtime sources. Two new real Humble/Nav2 runs
used the fixed Harness `9278fea`, the existing qualified amd64 recording image,
and actual host `gpt-6-sol`/high proposals through Codex0.159.0. Normal A-only used
two decisions and finished 0.209m from A. A static occupied-A map produced an
associated accepted native failure; the installed Owner actually closed its
native work, established successor readiness and released A before the failure
proposal selected one B. Backup completed 0.230m from B using three
proposals overall. No A arrival was required to propose the backup.

Each run had one physical evaluation and bounded proposal-association checks;
Gazebo truth never reached Agent/model inputs. The host model/launcher groups
and local proposal children exited and were reaped without forced group cleanup.
Container relay children retain their own reaped records; Linux PIDs are not
interpreted as host PIDs. Exact scene containers were removed with no OOM. The
normal run's live mounts/network/resource inspection confirmed 2CPU/4GiB,
network none, and no private host output mount. The first attempt never started
its scene because a nested mount could not create a path inside a read-only
bind; its failure remains recorded and was not evaluated or relabelled.

Both successful runs retain same-run raw recordings and original-speed exports,
with startup/teardown trimmed and approximate event captions. Full decoding and
selected frame checks passed. These original artifacts are
[published as homepage players](https://xiao-yang25.github.io/robot-harness/#recovery-demos). The normal path uses
the existing map; the backup's static occupancy fixture does not establish a
physical obstacle or general unreachability. Scene map preparation remains
research-specific; the actual task run does not qualify a public recovery scene
command. Its installed public CLI is covered by the controlled combination
checks. Subsequent public scene/tutorial reproduction uses the newer fixed pair
described below; it does not change the original recording qualification. Task verdict stays unassessed, native/remote cleanup unknown and final
B settlement pending. Hardware, Owner restart, general recovery, broad model
reliability and a hard stopping limit are outside this increment.

## In-motion revision qualification

The installed Agent `1891459` / immutable Harness `7279cd1` pair has bounded
Ubuntu 22.04/Humble/Nav2/Gazebo qualification for the explicit revision profile.
Installed Python packages were compared directly to those source revisions;
the fresh Core/Agent installations from the software batch and retained amd64
image were reused. This is not a complete image rebuild or a broad reliability
result. Each of the first seven completed, zero-delay scenes had one offline
physical evaluation:

| Input / scene | Observed result |
|---|---|
| No instruction | Only A completed; independent A error0.204m |
| Stop during A motion | Exact A cancelled, no output, settled/released in about5.745s; `stopped_by_instruction`, no completed site or B request |
| Controlled redirect | A released in about5.018s before the B proposal/admission; only B completed, error0.232m |
| Actual B lifecycle pause | Fresh B state2 refused reuse; A cancelled/pending/revoked, needs-help, zero B or after-revision proposal |
| Foreign revision identity | One invalid instruction ignored; original A completed, error0.218m, zero B |
| Global stop racing redirect | Task cancelled; A remained pending/revoked, zero B or later proposal |
| Host-model redirect | Three actual proposals, explicitly requested `gpt-6-sol` / high via Codex0.159.0; A released in about4.994s before after-revision, only B completed, error0.236m |

Business inputs remain controlled. The installed application receives only public
Session feedback; the model receives the normalized instruction and declared map
measurements. Passive Gazebo truth is evaluated separately and never drives a
decision. The reuse boundary checks correlated native/child/BT/outlet closure,
fresh odometry quiet and all six fresh B readiness replies. Gazebo snapshots
corroborate selected motion/arrival positions, not continuous independent quiet.
Cancel ACK alone never permits B. Timings above are individual observations,
not hard stop limits.

One earlier model scene failed in RViz startup before any Agent/model request;
its original logs remain incomplete. The unchanged second scene passed; the
graphics failure's root cause remains unknown. The exact scene containers and
owned model/relay children were removed/reaped. Host groups exited zero without
forced cleanup; the actual container had no network, 2CPU/4GiB and no private
host model output mount. Reports retain unassessed task verdicts and unknown
native/remote cleanup; normal final B remains current/pending.

Two additional, separately evaluated stop/model-redirect scenes delivered the
instruction four seconds after the window opened. They retained the original
budgets and thresholds: stop released
A in about5.050s with zero B; model redirect released A in about5.683s, then
completed only B with independent error0.228m. Both scenes retain their own raw
logs and raw recordings; the earlier zero-delay recordings remain intact.
The delayed model scene's RViz view was empty despite its completed task, so
that video was rejected for presentation. This additional graphics issue remains
unresolved. The published redirect clip comes from the earlier zero-delay run;
the stop clip uses the delayed run. No clips splice different scenes.

The public `--task revision --instruction stop --instruction-delay 0` command was
also exercised against the same installations. Its caller/scene completion and
exact container removal passed; this separate entry check is not another
physical evaluation. [Same-run stop and redirect videos](https://xiao-yang25.github.io/robot-harness/#revision-demos)
present the two normal branches. Neither Owner restart, arbitrary routes, human
intent recognition, hardware nor a general model service is qualified.

## In-motion revision software checks

The original software increment for `RevisionNavigationTask` consumed Harness
`7279cd1`; the current dependency is recorded in
[workspace.repos](../workspace.repos). The published `v0.1.0a1` tag and its older
pin remain immutable. Application checks cover one motion window, no instruction,
stop/redirect, foreign/expired inputs, native completion races, original budget
clipping, provider/observation/global-stop failures, post-model release/pose loss,
ambiguous B, missing expiry facts and default-profile rejection. Existing task
tests remain enabled.

New installed combinations use the actual public Unix Session and compiled Core,
with a CI-only owner injecting synthetic motion/native facts. They check A-only,
actual Core cancelled/no_output→released, succeeded/authority_revoked→released,
unconfirmed release→zero B, public caller close, and host/relay phase paths with
controlled subprocess proposals. Existing fixed/checkpoint/ALOHA checks also run
against the new pin. Both existing Ubuntu workflows automatically discover these
cases; no duplicate job or physics/model qualification is introduced.

The same new wheel is installed outside the source tree on macOS and Ubuntu 22.04
amd64 using the retained Humble image. Local macOS application tests passed
106 cases. Both platforms exercised 26 installed cases; an incorrect old
failed-proposal process count was corrected and the affected seven host cases
passed. The final missing-expiry guard then passed 15 boundary cases and twelve
affected installed cases in new wheel installations on each platform. Original
failed logs are retained. Existing CI runs the complete final collections.
These software checks do not establish ROS/physics, authenticated model or
physical-stop timing. The separate fixed-pair qualification above supplies its
own bounded evidence; older checkpoint videos retain their recorded scope.


## Checkpoint navigation qualification

The explicit [checkpoint tutorial](../examples/navigation/README.md#run-the-checkpoint-task)
has new installed software checks and bounded Humble/Nav2 qualification, separate
from the original fixed A→B runs below. Recorded application code `2ac951b` uses
the unchanged immutable Harness dependency `13bc75e` with new Linux Core/Agent
installations and the existing qualified Ubuntu 22.04/Humble amd64 image. The
whole image and optional Python-header download branch were not rebuilt.
Application and installed combination checks passed 86/18 on macOS; the two new
installed host/relay cases use controlled model and native providers.

Four separate new scenes each had one offline physical evaluation. Controlled
finish-A completed in 60.55 seconds with A error0.189m and zero B requests.
Host-model continue-B completed in109.55 seconds with A/B errors0.188/0.175m:
three actual `gpt-6-sol` / high proposals via Codex0.159.0, including the normalized
continue instruction, were accepted after fresh feedback. An actual Docker
inspection confirmed no network, 2CPU/4GiB and no mounted host model output.
Both business instructions were controlled and delivered after four seconds;
this does not qualify human intent recognition or a general model service.

Foreign-checkpoint and valid-but-late instruction cases entered needs-help after
released A, with zero B and no extra model proposal. The late provider deliberately
ignored its cooperative deadline and returned after10.22 seconds; the task refused
the answer. All four exact containers were removed. A remains settled/released;
normal final B is current/pending in its task report. Every task verdict stays
unassessed, with native and remote cleanup unknown. Actual host model/relay children
were reaped; owned host groups exited zero without forced cleanup.

[Same-run videos](https://xiao-yang25.github.io/robot-harness/#checkpoint-demos)
present the two normal runs at original speed with startup trimmed and captions.
No in-motion replanning, Owner recovery, hardware or hard stop limit is qualified.
The public example command was also run against these new installations with
`--task checkpoint --instruction finish_at_a --instruction-delay 0`: process and
container completion passed, with A-only completion and exact container removal.
This separate command/cleanup check is not another physical evaluation. Hosted
checks are recorded against the final delivered revision separately; configured
CI alone is not a physics result.

The [ALOHA](README.md#aloha-application) and [navigation](README.md#navigation-application)
contracts define application behavior.
A model assessment, a settled execution receipt and an independent task verdict
are different results.

## Developer preview verification

The `0.1.0a1` package pairs with the immutable Harness dependency in
[workspace.repos](../workspace.repos). Its default entry is the
[controlled navigation tutorial](../examples/navigation/README.md), with separate
optional host-model and ACT / ALOHA preparation. Record the Agent commit, package
version, Harness revision and selected image identity when reproducing it.

Before a GitHub prerelease, check the source distribution and its built wheel,
license files, installed entry points and applicable application/combination CI.
Then reproduce the public controlled tutorial in fresh Linux build/install and
run directories. Check the three correlated proposals, A settled/released before
B, final B accepted/pending, the unassessed task verdict, unknown native cleanup,
and actual proposal/container reaping. Process completion is separate from
physical task success; the preview tag predates the
[installed navigation evaluator](#installed-fixed-navigation-evaluation).

The historical qualifications below retain their exact versions and environments;
a version or documentation change does not rerun those experiments. CI uses
controlled providers and does not replace actual ROS/Gazebo reproduction. The
preview makes no cross-version API/ABI promise. Known limits include Owner
loss/restart, hard stop deadlines, full native cleanup, general routes/obstacles,
physical hardware and broad model reliability. Isaac/RTX qualification is separate.
Report failures through the [feedback guidance](../CONTRIBUTING.md#feedback-and-changes).

## Automated checks

[Checkpoint application checks](../tests/test_navigation_checkpoint.py) cover both
business instructions, missing/foreign/late answers, shared deadlines, unreleased
A, changed feedback, cancellation, proposal/command disagreement and ambiguous B
without replay. A controlled proposal child also checks the checkpoint schema.
The existing application workflow discovers these alongside the fixed A→B checks.

[Four installed checkpoint cases](../tests/combination/test_navigation_checkpoint_installed.py)
consume a fresh Agent installation with the real public Session and Core: finish
at A, continue to B, foreign checkpoint rejection and actual slow-provider deadline
expiry. They check retained A release, exact B revocation on caller close, honest
pending/unknown outcomes, owner process exit and socket removal. The existing
Ubuntu combination workflow discovers them automatically. Native and instruction
providers remain controlled; these checks do not establish real ROS/model/physics
behavior or a hard stopping deadline.

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
Two [host/relay composition cases](../tests/combination/test_navigation_host_installed.py)
use installed packages and actual local processes: normal decisions retain B
pending, while a host tool event crosses the relay as an error with zero admissions.
Discovery includes twelve combination cases; these controlled tests do not run
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
candidate in isolated Ubuntu 22.04/Humble amd64 simulation. Codex0.159.0 requested
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
build/install directories in an existing Ubuntu 22.04/Humble image, and exercised
three controlled proposals through the installed CLI. It did not rebuild the
entire ROS image or repeat live-model qualification. Failed preparation and
evaluation attempts were retained separately. The published videos above are
distinct runs, rather than evidence for this new installation.

That reproduction used research-only launcher selection, controlled proposal
and passive-observer tools. The new [controlled business tutorial](../examples/navigation/README.md)
provides public preparation, launch and report inspection using the existing
Harness supervisor and installed Agent CLI. The fixed new installation and
controlled native run are qualified below; the subsequent host model workflow
has its own qualification section. This historical reproduction predates the
[installed navigation evaluator](#installed-fixed-navigation-evaluation);
`robot-agent-evaluate-handoff` applies only to ALOHA. CLI completion and an owner's
process-completion verification file cannot prove physical task success.

Later Harness startup diagnostics in `03a357b` preserve the original service and
context budgets and report individual child failure. The new manifest includes
those diagnostics, trusted-client launcher and bounded B startup ordering in
`13bc75e`; older recorded
results retain their original versions and scope.
GetState preparation-timeout cause, Owner loss/restart, full native cleanup,
hard stop, hardware and general reliability remain unqualified. Application
licensing is now specified in the [project declaration](../LICENSE) and
[contribution terms](../CONTRIBUTING.md#licensing-status); the
[preview verification](#developer-preview-verification) remains separate from
these historical experiments.

## Public controlled navigation workflow

Fresh GitHub checkouts of Agent `721140b` and its fixed Harness
`13bc75e903f6005da3dd5d969f8242ce211d182f` exercised the published wheel, Linux
preparation and launch commands. New Core and Agent installations used an existing
qualified Ubuntu 22.04/Humble amd64 image with Python3.10 headers; this did not
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
for this packaging increment. The later public host model workflow has separate qualification below.

## Public host model navigation workflow

The opt-in [tutorial mode](../examples/navigation/README.md#run-with-a-host-model)
keeps model credentials and execution on the host. It supervises one model worker
and Harness launcher; Harness owns Docker cleanup. New actual-process tests cover
three phase exchanges, filtered inputs, file/nonce rejection, proposal withdrawal,
original deadline expiry, failed preparation and signal/forced process-group cleanup.
Private host outputs overlapping scene or container mounts are refused before startup.
The existing task/decision/operation budgets and pending/unknown outcomes remain.

Fresh public Agent `72908370f7c8ee3b8f8b56f63fe9fe226d18776e` and manifest Harness
`13bc75e903f6005da3dd5d969f8242ce211d182f` were fetched into a new consumer.
The published wheel/preparation commands built new Linux Core/Agent prefixes and
installed that same wheel into a separate host environment. An existing qualified
Ubuntu 22.04/Humble amd64 image with Python headers was reused; the whole image and
optional header-download branch were not requalified. macOS application checks and
exact-candidate Ubuntu CI passed all 67 application and twelve installed combination
cases, including the two new host/relay cases. Failed initial missing-extras and
incorrect test-error-location attempts were retained separately.

The public host model command made three actual Codex0.159.0 requests for
`gpt-6-sol` / high: visit A, visit B and observed complete. The task took66.293s.
Actual container inspection confirmed network none, 2 CPU/4GiB and exactly five
expected mounts, excluding host model output or credentials. Model inputs contained
only task context and declared map pose/time/sensor health, with no tool events.
A settled/released before fresh B admission; final B remained accepted/pending.
One separate same-run physical evaluation measured A/B errors0.202/0.159m under
the unchanged0.35m predicate. The application's task verdict remained unassessed;
native and remote model cleanup remained unknown.

All three actual model CLI and three container relay children were reaped. Both
owned host process groups exited0 without forced cleanup; the scene/container
exited0 without OOM and the exact container was removed. The passive observer also
exited0 and was reaped. This qualifies one normal public-entry combination, not
model-service reliability, remote cleanup, Owner loss, hardware or a hard stopping
limit. Historical model runs and published videos retain their own version/scope;
this packaging increment does not claim a new recording.


## Public recovery scene tutorial

The tutorial consumes Harness `32c78ad7020e1ccbea5d9225e9a20b1c477b4da8`, the
actual merged public-scene increment. `--task recovery --scene normal|occupied-a`
forwards the failure profile, matching map identity and installed public CLI to
the existing Harness launcher. The controlled client bind and host relay retain
the existing owned-process supervisor. Occupied A with another task and recovery
instruction options fail before checkout/process access. Earlier fixed,
checkpoint and revision selections retain their behavior. See the
[commands and outcome records](../examples/navigation/README.md#run-the-single-failure-recovery-task).

Local macOS application checks passed131, including four focused selector/client
checks. A new wheel consumed new real Harness Core installations outside both
source trees; all34 installed combinations passed on macOS. The original
macOS socket checks failed under filesystem sandbox permissions, then passed
with permitted local socket access without changing code or assertions.
Public image navigation needs no Pillow; the optional ALOHA/visual combination
suite uses a separate existing Linux test image with those dependencies.


All34 new installed combinations also passed offline on Ubuntu 22.04 amd64 with
the real new Core bridge and wheel. The first preparation attempt used an invalid
wheel bind filename and did not install or execute tests; correcting only that
filename completed installation and checks. Source, wheel and separate host/Linux
installed runtime modules were directly compared. Existing application and
combination CI discover the new checks without adding another workflow.

The actual public tutorial then completed normal A-only and occupied-A single B
with controlled proposals. A third occupied-A run through the same tutorial used
actual host `gpt-6-sol`/high via Codex0.159.0 and three proposals. Its failed A
closed/settled/released before the failure proposal; only B completed. Selected
map identities, native/Core records, public CLI reports, relay reply/proposal
association and owned process/container cleanup passed one focused entry check
per run. Both host groups and local proposal children exited and were reaped
without forced group cleanup; containers were removed without OOM. Private host
logs/credentials were outside scene mounts; proposal answers used the exchange.
These checks qualify the new installed public entry, not another physical arrival
or video evaluation. The preceding Harness public-scene runs used an external
physical evaluator; the older published videos retain their original pairing.
Task verdict stays unassessed, native/remote cleanup unknown and final B pending.

## Installed fixed navigation evaluation

`robot-agent-evaluate-navigation` consumes recorded normal fixed A→B evidence
with a packaged, fixed 0.25m arrival predicate. The [tutorial](../examples/navigation/README.md#collect-and-evaluate-the-fixed-normal-task)
opts into Harness's passive collection; default runs remain unchanged. The
[contract](README.md#planned-installed-navigation-evaluation) separates physical
goal, native outcomes, Owner-reported settlement and observed process cleanup.
The standard-library offline command neither modifies the task report nor
imports ROS, Docker, research evaluators or private Host/Core modules.

Synthetic checks cover correct/wrong/threshold arrivals, absent/malformed,
foreign/duplicate/nonfinite evidence, mixed Session/native identity, unknown
alignment/initial anchor, query/trigger deadlines, A capture after B reservation,
missing release, forced/unreaped collection, optional metadata and refusing an
existing output before evaluation. Controller replacement under the same ID,
jointly invalid receipt enums/native status types, nested optional metadata and
overflowing derived distances have rejecting regression checks. Installed combination discovery checks the
new executable/profile outside source trees, with `python -S`, all three exit
codes and retained output on refusal. The application workflow also checks its
installed help entry. No new CI workflow or physics run is introduced by those checks.

Fresh local application checks passed 148 tests, and the new wheel passed all
35 installed combinations with the real portable Core bridge. These are software
checks on synthetic/no-physics fixtures.

On 2026-10-06, Agent `71a804dfa9ff7f8671d464f8ed562cd2eeaec5e8` and its exact
Harness dependency `4b4bc5bf28c249016cfe4d7e272fa9877766a838` completed one new
public controlled normal A→B run. The public preparation script made fresh Linux
Core and Agent installations from this pair and a new wheel; package content
was directly compared with source and a new host installation. The existing
qualified Ubuntu 22.04/Linux-amd64 Humble/Nav2 1.1.20/Gazebo Classic image was
reused; the current source-mounted collector was not an image rebuild.

The installed offline command ran exactly once and returned `succeeded`:
A/B XY errors were **0.208517/0.188799m**, within the fixed 0.25m limit. Initial
map/world anchor, actual configured controller, unique native associations and
capture before B's native reservation were accepted by that predicate. A focused
independent safety-decision check accompanies this qualification; it does not
repeat physical evaluation or native closure adjudication.

Owner reports A settled/released and final B pending/current; both native goals
succeeded. The Agent report remains `task_verdict=unassessed` and native cleanup
unknown. The collector and three pose queries exited zero and were reaped with
no forced collector group kill; the container exited zero without OOM and was
removed. These observed process facts do not prove complete native resource
release. Three controlled proposals made no model calls. This is one fixed
simulation qualification, not reliability, arbitrary-map, hardware or a new
model qualification. Existing recordings retain their original versions and
are not presented as recordings of this new evaluation run.

## Explicit coordination tutorial

The current checkout pins Harness
`747d7d48a846ad361cf7260d2339b010c0b92a00`. The
[tutorial](../examples/navigation/README.md#experimental-coordination) explicitly
selects the experimental assembly and an Owner terminal query budget. Existing
public task defaults and historical qualifications retain their own versions.

[Application checks](../tests/test_navigation_coordination_demo.py) cover actual
host CLI selection/prevalidation, normal domain behavior, separate Session and
decision ownership, close-before-late-answer order, original B cancellation and
close failure retained as unknown. Diagnostic failure cannot bypass Session
cleanup, and cancel/late-answer errors cannot produce a successful tutorial exit.
Existing application discovery includes them.
The [installed combination checks](../tests/combination/test_navigation_runtime_installed.py)
add normal and final-decision-stop tutorial runs through installed packages and
the real portable Core/Unix Session, with synthetic native measurements. Existing
combination CI discovers them without a new workflow. These checks do not qualify
ROS/native movement or physical stopping; fresh public-entry scenes are recorded
separately before this pair is accepted for simulation.

On 2026-10-10, installed Agent
`930eaf8273772b145f290b407a372950eed678f2` / fixed Harness
`747d7d48a846ad361cf7260d2339b010c0b92a00` exercised both scenarios through this
public entry, using controlled proposals, the existing ROS Humble/Nav2/Gazebo
image, network-none, 2 CPU/4 GiB and an explicit eight-second terminal query
window. Fresh software checks passed 191 application tests, 18 focused checks
and four selected installed Core/Session checks. Existing CI discovers the new
checks without an additional workflow.

The normal task completed in 38.577 seconds; its one independent physical
arrival evaluation succeeded (A 0.207816 m, B 0.183400 m). The stop task reached
its final decision after B's successful native result, then withdrew while that
decision was held. Original B cancel/query and local Session close completed
before releasing the actual late answer, which was retained without another
submission. Its wall time was 36.553 seconds. This qualifies the controlled
waiting-decision boundary; it does not qualify cancellation during motion,
hard physical stop latency or a real model. Final B remains pending/current in
the normal sample and pending/revoked in the stop sample; native cleanup remains
unknown in both. Each task report stays unassessed; the separate evaluator owns
the normal physical-success verdict.

Independent software and focused safety-fact reviews approved this bounded
qualification. Both public launchers and passive same-container video observers exited zero;
containers exited zero, no OOM, and were removed. Both recordings fully decoded,
and representative frames showed actual navigation. Their original-speed clips
are local presentation candidates; media publication is a separate batch.

## Host proposals with shared coordination

The explicit experimental navigation assembly connects the existing host worker
and relay to the same private task coordinator for `normal` only. Application
checks cover selection before resource creation, an explicit model/private output,
separate Session/decision ownership and rejection of the controlled stop scenario
with a host provider. Legacy task entries and the Harness pin remain unchanged.

[Installed host composition tests](../tests/combination/test_navigation_host_installed.py)
exercise actual installed Agent, public NavigationSession and portable Core with
controlled executable proposals and synthetic native measurements. The new cases
complete A→B, reject a tool attempt with zero admissions, and externally interrupt
while an actual host proposal child waits at final. The stop case retains original
B cancellation, local Session close, relay withdrawal, no final response and
reaped local children. Cancellation is an unsuccessful normal demonstration;
native/remote cleanup and task verdict retain their original unknown/unassessed
scope. Existing combination discovery includes these cases without a separate
workflow or additional model dependency.

This is software/installation coverage. At this increment no real model,
ROS/physics run or new video was qualified for the assembly. The old host path
and controlled coordination scenes keep their own versions and evidence. The
subsequent qualification below uses an explicitly selected model and environment.

## Real-model shared coordination

On 2026-10-11, installed Agent
`0a91a2f0f0018aaadcb14587795a58ff2c9cb154` consumed its fixed Harness
`747d7d48a846ad361cf7260d2339b010c0b92a00` through the public opt-in
experimental-coordination host-codex path. GPT-6.1 Sol/high via CLI 0.159.0,
original 30 s per proposal/max 3 and 240 s task budgets, and the existing offline
Ubuntu 22.04/Humble/Nav2/Gazebo amd64 scene at 2 CPUs/4 GiB were retained. The host
network path was verified separately; credentials/raw model logs stay private.

- Normal: three actual proposals returned in about 10.97/11.27/9.93 s. Task
  completed in 69.923 s; A released before B admission. The one independent
  physical evaluator succeeded, A/B arrival error 0.204/0.198 m. Final B remains
  pending/current, task verdict unassessed, native/remote cleanup unknown.
- Withdrawal: after the actual visits, a research observer identified the
  business Task by final proposal nonce, endpoint and process start identity,
  then delivered SIGINT during the real final CLI turn without holding an
  answer. The original B cancel/query and Session close completed; no final
  answer or further submission was accepted. Task cancelled, B pending/revoked,
  local model children/process groups and exact scene container absent. Native
  ROS cleanup reported shutdown-context errors; native/remote cleanup unknown
  is not upgraded. No physical-success or hard-stop verdict is assigned.

A focused independent review checks the admission/withdrawal association and
local exit facts without repeating the complete evaluator. The normal scene
exits 0; withdrawn client/scene exits 1 as expected for this interrupted normal
Task, independently of the boundary verdict. The observer targets the business
Task, not the outer launcher, whose graceful cancellation is not qualified here.
The public controlled final-decision-stop/host-codex combination stays rejected.

The earlier first-proposal timeout without a shell proxy remains a failed sample.
A separately authorized same-budget proxy scene is the normal qualification
above; it does not prove an exclusive root cause or general service availability.
An initial evaluator import-path failure occurred before physical adjudication;
its record is retained and the one physical evaluation used the installed Agent
import path. These actual-model runs are separate from software/installation CI
and do not migrate the public default, qualify another provider or hardware.
[Same-run videos and limits](https://xiao-yang25.github.io/robot-harness/guide/docs/assets/demo/index.html#real-model-shared-coordination)
remain separately playable, with retained waits and original motion speed.

A later macOS main-CI deadline fixture exposed an overstrong file-absence
assertion: host expiry can publish a correlated timeout error before the relay's
withdrawal marker arrives. The relay must reject that error, publish cancellation
and produce no answer; an error response is not successful model output. The
fixture now permits only a matching-nonce TimeoutError without an answer, retaining
actual child reaping/absence checks. A separate actual-Relay error-response test
covers that ordering. This is a software-test correction, not a production change
or another model/physics run; the original failed CI remains a failed record.

## Private ROS camera binding

[Binding regressions](../tests/test_inspection_camera.py) cover actual-image health
provenance, clock-only silence, owned pixel/intrinsics snapshots, stale and future
images, publisher change, invalid inputs, delayed TF and a missing-map distinction.
The delay tests reject permanent frame loss and repeated-pump health renewal;
final association metadata keeps its own consumption time. ROS imports are lazy,
so these fourteen standard-library tests run in both existing application CI jobs
without a ROS dependency. Final macOS/Linux Python3.12 suites passed239 each;
31 source/binding checks passed against a fresh installation outside source trees.
Accurate-revision CI results are recorded below; no redundant workflow is added.

Two offline Ubuntu22.04/Humble/Gazebo amd64 stationary scenes consumed the freshly
installed Agent at2CPUs/4GiB, with640×480 RGB and a five-second/max25 window. Both
used the same abnormal-panel fixture, which was absent from the online interpreter:

- Continuous source:13 actual abnormal observations; after closure,10.014 seconds
  of controlled decision waiting and51 new-image health updates. Historical record
  remained applicable, no source pixel slot/read retained, proposal not withdrawn.
- Local observation-path loss:15 abnormal observations; destroy the client's Image
  subscription while clock advanced6.4→7.5. About1.066 seconds later, health expired,
  the old proposal was withdrawn and history stayed abnormal but inapplicable.
  One already-held frame completed association after destruction; its original
  receive time precedes destruction. No post-destruction new image is claimed.

Both gated decision threads stopped, camera Context closed, and actual Gazebo,
scene supervisor and containers exited zero without OOM. All dedicated containers
were removed; no image build/download or volume was created. Independent review
approved the repaired implementation and focused association/withdrawal/exit facts.
An earlier default-executor Context failure and then Humble numpy-scalar input
failure remain failed runs. The fixes preserve the same quality/time predicates.

These are real camera observations with a controlled waiting owner, not a real
model, navigation Action, arrival or full inspection task. No device crash, hard
response/stop bound, sustained throughput, localization accuracy or restart
qualification is inferred. Final paired installation/CI and full task scenarios
remain separate. Public defaults and the Harness dependency pin do not move.

## Inspection foundation delivery

The private event/source/camera foundation was delivered through
[PR40](https://github.com/xiao-yang25/robot-agent/pull/40), merged as
`96339257fe38b25aa284a1d615a3e62d60efca0c`. Accurate candidate and main checks
passed: Ubuntu/macOS application239 each and installed combination46.
[Main application run](https://github.com/xiao-yang25/robot-agent/actions/runs/38154174248)
and [main installed run](https://github.com/xiao-yang25/robot-agent/actions/runs/38154174256)
record those results. This updates Git/CI delivery status, not the earlier
stationary-camera qualification or its controlled waiting-owner scope. The
fixed Harness dependency and public defaults remain unchanged; complete
inspection policy and final paired physics/video qualification remain separate.

## Private station inspection policy

[Policy tests](../tests/test_inspection_policy.py) add23 software checks: normal A,
single B with A history retained, unknown without a successor, pose/reuse and
current readiness gates, original request/decision correlation, stale/foreign
window rejection, original task/operation/decision deadlines, clock rollback,
terminal late facts and duplicate results. Provider text cannot turn observations
into claims of repair or native release.

Controlled Source time distinguishes a closed historical record from current
health. Real Coordinator/Owner threads test model-wait withdrawal while original
I/O is collected and cancelled, withdrawal before submission claim, and a late
accepted result after claim. These use synthetic navigation/services, not actual
Session or camera navigation. A reserved request is not an accepted operation;
only confirmed accepted work may continue through an independent camera fault.
Actual pre-submit revalidation remains the binding's responsibility.

Final local macOS/Python3.12 and offline Ubuntu22.04 ARM64 runs passed262
application tests each. A fresh installed package outside the source trees passed
all23 policy tests. Focused independent review approved the final software slice
after repairing first-turn clock rollback and clarifying reservation/acceptance.
An intermediate test-placement failure was repaired without weakening the
original budget assertions. Existing application CI discovers these tests; its
candidate/main runs must be checked for the delivered revision. The installed
Agent/Harness workflow retains its existing compatibility scope and fixed pin.

These checks do not qualify moving inspection, actual model decisions, ROS
arrival, physical stop, sustained throughput or native cleanup. Full task
assembly and final paired physics/video qualification remain separate.

## Private inspection navigation binding

[Twelve software tests](../tests/test_inspection_navigation.py) check original
Session association, A reuse/B pending, pose/realm gates, applicable source record
identity, submission-time health/stop/revocation/deadlines, retained site
reservations, ambiguous reply without replay and original status/cancel after
camera failure. A controlled real I/O Owner crosses claim while the Source fails
during preparation; the final guard rejects with zero Session submissions.

Final local macOS and offline Ubuntu22.04 ARM64 application runs passed274 each.
A fresh installed package outside source trees passed12 focused checks and
[three Session/socket/Core checks](../tests/combination/test_inspection_navigation_installed.py).
The installed caller consumes actual correlated adapter facts through the policy
and Coordinator; the fixture supplies synthetic native results, logical source
time and manual classifications. Actual submit-entry counting distinguishes zero
replay from Core idempotence. Owned fixture processes exit normally and sockets
disappear; B's receipt remains pending before connection close.

Independent review repaired a submission guard interval during Source checks;
the final test invalidates permission at that exact point. A review of installed
tests strengthened lost-reply counting, and a fixture budget-anchor error was
fixed without relaxing the original deadline. Initial preparation failures are
not qualification. Existing application and installed-combination CI automatically
discover these additions; check exact candidate/main runs for delivery status.

This is software/installation evidence, not a production inspection runner,
actual camera navigation, model quality, physical stop or final paired migration.
Public defaults and the fixed Harness pin remain unchanged.

## Private inspection caller loop

[Twenty caller tests](../tests/test_inspection_runtime.py) exercise normal A,
single abnormal-A/B recheck, unknown without a successor, source loss versus
explicit stop, new health during slow decisions, native invalidation, original
ambiguous/late I/O, wrong/withdrawn decisions, startup budget, partial admission,
close errors and draining owners. Navigation/source checks additionally cover
original feedback and window deadline anchors and execution facts surviving a
condition-query failure. Synthetic images and manual classifications do not
qualify visual recognition or a live ROS camera.

Focused final checks passed75. macOS/Python3.12 and offline Ubuntu22.04 ARM64
passed297 application tests each; a fresh installed package passed20 caller
checks outside source trees. Its module help runs without initializing ROS.
[Three installed loop checks](../tests/combination/test_inspection_runtime_installed.py)
consume the retained pinned Harness through actual public Session/socket/Core:
normal A release, one B with anomaly history/pending context, and source loss
during B decision with cancellation of the exact original operation. Fixture
processes exit and sockets disappear. Native/source facts remain synthetic; the
local Core installation is retained rather than newly built.

Independent implementation review identified and reproduced normal-deadline
history loss, JSON failure when callback faults retained an original typed fact,
and cleanup of a reserved request without an established grant. Those defects
were repaired and regression-tested without extending deadlines or weakening
admission. Final scoped review approved the code, independently passing10
regressions and3 distinguishing probes. Initial failed checks remain research
evidence; they are not successful qualification.

Existing application CI discovers the new tests; installed-combination CI copies
the shared controlled camera fixture and discovers the3 new loop tests. Check
candidate/main runs for the exact delivered revision. This increment does not
qualify moving inspection, real models, physical stopping, sustained throughput,
restart recovery, final paired migration or a new video.

Initial hosted macOS CI exposed a controlled-fixture preparation problem: its
40ms window produced only one sample under coarse scheduling, so decision tests
never reached their intended branch. The fixture now provides250ms sampling
headroom; production source predicates and budgets are unchanged. The deadline
regression waits past the actual original deadline on interpretation4 and still
asserts exactly3 recorded samples. Independent ordinary/coarse-scheduling20-case
runs and a paired old/new-window probe passed; updated installed20 and Core3
checks also passed. Accurate-revision CI remains the delivery check.

## Selected moving inspection checks

The delivered private caller ran in retained Ubuntu22.04/Humble/Nav2/Gazebo
containers on an ARM Mac through amd64 emulation. Each scene retained2 CPU,
4GiB,512 PID slots and420 seconds externally; original task/operation/decision
and startup/cleanup budgets were unchanged. No model, GPU inference or hardware
was invoked. A current Agent installation and retained native Harness installation
were consumed; this is not a fresh native build or final public paired migration.

| Scene | Actual closed observations | Independent arrival error | Caller time |
| --- | --- | --- | --- |
| Normal A-only |19 normal samples |A0.190m |23.943s |
| A anomaly then single B |A14 abnormal; B15 normal |A0.206m; B0.187m |50.592s |

The one offline evaluator linked original Core requests/operations to reserved
native goals, terminal receipts, same-goal Gazebo queries and accepted image
records. Both selected scenes passed the fixed0.25m physical arrival threshold.
Actual image acquisition/receive/consume times, CameraInfo and image-time map TF
were retained. Source classification used the existing fixed color/white-border
thresholds and at least3 samples; fixture status and pose truth were excluded
from the online caller. A-only preserves the earlier fixed-A/B collector's
`unknown` status; required raw start/A samples and query errors/reaping were
checked directly for this distinct task.

A focused independent safety-decision check confirmed one A request or one A/B
pair, actual A release before B admission, original task/check/source association
and B pending/current at arrival then pending/revoked during closing. Reports
retain native cleanup unknown and independent task verdict unassessed. Owned
containers exited0 without OOM and were removed; native Owner and auxiliary
processes were reaped without force. Raw and original-speed preview videos were fully decoded; representative
frames confirmed navigation movement and same-run labelled captured camera
samples. Captured stills are not a live camera stream or precise timing evidence.
These are local preview assets; public tutorial/showcase release is separate.

Earlier runs remain failed evidence: one lost navigation conditions before A
arrival and retained unknown execution/close errors; its precise cause remains
unconfirmed. Two later camera windows returned unknown at the accepted arrival
pose because a controlled panel was off-center. Only the fixture's horizontal
readable width was changed, preserving vertical border geometry and original
classification/source predicates. Software rendering and recorder filter threads
were bounded within the same resource envelope; those combined changes do not
establish a unique cause for the first timing failure. One passive pose query
failed before the thread configuration change and is not successful evidence.

Independent review repaired research-supervisor cleanup-result propagation and
three evaluator association/recording gaps before accepting these two scenes.
Additional waiting/source-loss checks are recorded below. Full explicit-stop
qualification, sustained-load performance, general visual recognition, real
models, native/physical stopping, restart recovery, supported public inspection
tooling and final paired migration remain open. Software CI keeps its scope.

The normal/recheck runs had maximum sampled container memory1.784/1.787GiB
and sampled PID counts466/467. Maximum sampled caller camera-pump gaps were
0.106/0.107s. These observations include the emulator and display workload,
are not worst-case measurements, and do not establish a response or stop SLO.

## Selected decision-wait and source-loss checks

The same installed caller/native runtime, original budgets and offline2 CPU /
4GiB /512 PID envelope were used for controlled decision waiting. The research
RViz display was reduced from10 to5Hz; camera5Hz and original source/navigation
predicates stayed unchanged. No real model was called. Each selected scene was
submitted to its one offline evaluator once.

| Scene | Observed decision/history | Whole-scene evaluation |
| --- | --- | --- |
| Healthy A wait |10.003s;49 new health updates; A15 normal |Passed; independent A error0.208m |
| Image loss during A wait |A17 abnormal retained; actual subscription destroyed; clock33.2 to34.2; original visit-B proposal withdrawn; zero B |Passed; independent A error0.182m |
| Explicit stop during B wait |A19 abnormal/B19 normal retained; original B cancel response; late report proposal withdrawn |Failed; independent A error0.259m exceeds fixed0.25m |

The Source became inapplicable after Image loss with its original health-expiry
reason. The event was observed0.930s after subscription destruction; this is one
sample, not a worst-case failure or stop bound. The provider returns the original
proposal after withdrawal; task/check/source association and late retention are
checked directly. The caller retains the actual original check for Source
applicability; the decision owner receives an isolated copy. History does not
grant new authority after source failure or explicit stop.

All three selected containers and native/auxiliary processes exited normally
without OOM or forced reaping and were removed. Reports retain native cleanup
unknown and independent task verdict unassessed. The explicit-stop observation
does not make its failed whole-scene qualification pass. Two other runs remain
failed: initial scan receive age1.0014s exceeded1s before any A; a B-wait pose
lag0.526s exceeded0.5s before the stop trigger. The latter overlapped host media
conversion; a later isolated run reached the stop, but that does not establish
a root cause or eliminate intermittent freshness failure.

Maximum sampled memory was1.774/1.779/1.783GiB and PID count465 for these three
selected runs. Local original-speed videos retain captured-still labels; public
publication is separate. Research-helper identity/failure/challenge-action gaps
were repaired and independently reviewed before evaluation. The navigation
arrival margin and feedback freshness, full explicit-stop qualification,
independent navigation during inspection-source loss, missing/stale/wrong
association and final paired migration remain open. Existing software CI was
not replaced with these machine-specific scenes.

## Navigation prerequisite diagnosis

An observation-only diagnostic instrumented the existing Owner and Camera TF
buffers, with no additional ROS node or background thread. B's controlled wait
lasted 10.002s; each consumer supplied 98 wait snapshots and both transform chains
advanced. The complete recorded B period had 149 paired snapshots, no query or
pairing gaps, and a maximum successful Owner pose age of 0.031s. Sampling and
instrumentation can affect timing; this did not reproduce or explain the earlier
0.526s failure. A missing predicate-failure file is recorded as unknown rather
than proof of zero invalid observations. No whole-task qualification was inferred
from this diagnostic.

A separate, single margin trial changed only the two controllers' DWB and
SimpleGoalChecker XY tolerances from 0.25 to 0.15m; stateful and other parameters
were retained. The existing Owner read both actual parameter pairs before Core
admission. The independent physical threshold stayed 0.25m. A's diagnostic
physical error was 0.113m, but all 14 recorded marker observations were unknown:
the first central region had 0.628 color coverage, below the unchanged 0.7 threshold.
Source health remained valid. The report requested help, retained the unknown
check, and admitted no B or decision; explicit stop was never reached. The one
whole-scene evaluator failed, and no repeat or threshold relaxation followed.

The margin case's native Owner and local resources closed normally; its container
returned 1 because the requested stop branch was not reached, without OOM, and
was removed. Configuration/observation helpers received independent software
review; focused actual-fact checks remain distinct from task evaluation. Inspection
viewpoint/quality applicability and complete stop qualification remain open.
This research configuration has not changed product defaults, dependency pin,
public API or hosted software-test scope.
