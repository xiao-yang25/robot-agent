# Documentation

Robot Agent owns task decisions and uses Robot Harness's public Session.
Core belongs to Harness; the dependency runs from Agent to Harness.

## Application artifacts and reusable boundaries

| Artifact | What a user can use today | Boundary |
|---|---|---|
| `robot-agent-handoff` and [HandoffTask](../src/robot_agent/handoff.py) | Installed runnable ALOHA transfer/hold application | Fixed stages and skills with application-owned waiting/budgets; not a generic task execution SDK |
| [CodexDecision](../src/robot_agent/codex_decision.py) | Structured visual proposals used by that application | Task-specific cooperating model backend; not a general planner, memory system or execution authority |
| [ACT worker and preparation](../skills/aloha/README.md) | Bundled candidate worker, pinned environment and explicit weight preparation | ALOHA-specific policy input/output; pinned Harness private candidate transport, not a stable skill plugin API |
| `robot-agent-evaluate-handoff` and [fixed profile](../src/robot_agent/handoff_profile.json) | Installed offline evaluation of the declared recorded task | Task-specific predicate; evaluation does not drive decisions or authorize execution |
| `robot-agent-navigation` and [scene tutorial](../examples/navigation/README.md) | Installed bounded A→B application; controlled or host model proposals in the isolated Nav2 scene | Same-container owner; bounded local process cleanup, remote cleanup unknown |
| [RecoveryNavigationTask](../src/robot_agent/navigation_recovery.py) | Experimental Python task and explicit CLI mode: A, or one pre-authorized backup B after confirmed failed-A release | Prepared-owner and actual-model checks; explicit public scene tutorial |
| [Combination CI](../.github/workflows/combination.yml) | Reproducible installed Agent/Harness boundary checks | Explicit no-physics providers; not a model/robot task qualification |

These delivered artifacts are useful applications, policies and verification
tools. Their names and installation do not establish a general Agent framework.
Test fixtures and run-specific setup are not reusable task APIs.

ALOHA and navigation consume the same Harness execution coordinator for retained
requests, authority, deadlines, results and settlement. Their native execution and
closure remain backend-specific. Goals, context interpretation, skill selection
and business retries remain with Agent; each native engine owns its work once.
The navigation application preserves `HandoffTask` behavior; the manifest pins
the paired Harness implementation for both applications. This is bounded reuse,
not a generic skill-plugin framework or a physical-robot qualification.

### Adapt an existing application

Start with the [ALOHA setup](../skills/aloha/README.md) or the
[navigation tutorial](../examples/navigation/README.md) and the pinned
[Harness dependency](../workspace.repos). Both applications are runnable starting
points; their task classes are experimental Python interfaces.

| Change | Current extension point | What must remain qualified |
|---|---|---|
| Model or proposal logic | Explicit CLI model selection, or a caller-supplied `decision_backend` in `HandoffTask` / `NavigationTask` | Return the application's allowed proposal with its original task/phase/observation identity; keep the model separate from Session calls. A new model needs its own task evaluation |
| Shorter task/decision/operation budgets | `Budget` / `NavigationBudget` when constructing the task in Python | Stay within the existing bounds; shorter budgets do not make synchronous calls interruptible or guarantee a hard stop |
| New navigation sites, map or visit order | Requires a new application/owner adaptation; no general site configuration is exposed by the installed owner | Match task coordinates, map feedback, native contexts and closure obligations before claiming support |
| Different robot, camera, policy or skill duration | Check the affected task/backend contracts and adapt them where semantics change | Requalify observation/action semantics, normal behavior and relevant failures; keep third-party model/asset terms separate |

For an application-owned proposal backend, implement
`decide(context, observation, deadline, stop_requested)` and pass it to the task
constructor. The bundled CLIs select their declared backends; there is no general
CLI plugin loader. ALOHA supplies camera/joints, while navigation supplies map
pose/time/sensor health. Preserve each application's measurement whitelist and
proposal schema instead of treating them as interchangeable inputs.

The caller owns startup or connection and close; the task borrows the Session.
Keep ambiguous requests, pending settlement, cleanup and independent task verdicts
in their existing separate report fields. Verify an adaptation against the
[application and installed-combination checks](TESTING.md#automated-checks), then
record model/physics evidence for the changed behavior. Fixture checks alone do
not qualify it. A different goal or sequence should define its own task contract;
editing constants in these fixed applications is not a supported configuration API.

<a id="next-application-candidate-checkpoint-navigation"></a>
### Checkpoint navigation application

[CheckpointNavigationTask](../src/robot_agent/navigation_checkpoint.py) visits A,
then accepts one business instruction to continue to B or finish its own task at A.
This experimental Python interface borrows a prepared Session. The existing
`NavigationTask`, installed navigation CLI and released developer preview still require A→B;
returning `help` at A remains needs-help for that original goal.

The checkpoint requires A's correlated accepted result and settled/released
receipt plus fresh feedback at A. Supply an instruction provider implementing
`request(context, deadline, stop_requested)`. The context contains `task_id`,
`checkpoint_id`, `session_id`, integer `epoch`, `map_id`, `frame` and
`allowed_actions`. Return those six identity fields unchanged and an `action`
of `continue_b` or `finish_at_a`. Unknown optional metadata is ignored. Missing,
foreign, invalid or late answers lead to help without a default B submission.
The provider is called once; it receives no Session or independent physical truth.

Instruction collection has a ten-second window and shares the original
thirty-second after-A decision budget with the following proposal and validation.
All work stays within the 240-second task budget; shorter `NavigationBudget`
values also apply. The Owner must use its existing explicit 45-second caller wait,
rather than the default 15-second entry. Both provider and proposal backend must
cooperate with the deadline and stop callback; synchronous calls cannot be
forcibly interrupted by the task. The caller owns provider resources and Session
close.

The proposal backend receives the normalized `checkpoint_instruction`. Its answer
must echo that `checkpoint_id` and propose `visit_b` for `continue_b`, or
`finish_at_a` for `finish_at_a`; it may instead propose `help`. The usual
task/phase/observation identity and reason fields still apply. The bundled
`NavigationCodexDecision` supports this schema when used directly in Python.
Fresh Session/epoch/map, sensor health, A association and position are checked
again before B admission or completion at A. No proposal grants execution authority.

Finishing at A reports `completed_sites: ['A']`, A released, task verdict
unassessed and native cleanup unknown. B may already have a prepared native
context even though no B request was sent, so the caller must still close.
Continuing preserves B's current/pending disposition; ambiguous B submission
retains cancellation of exactly that request and never authorizes replay.
The task instance cannot be run again.

The [explicit checkpoint tutorial](../examples/navigation/README.md#run-the-checkpoint-task)
selects this application separately and can use controlled or opt-in host proposals.
The host relay reconstructs its bound instruction only in explicit checkpoint mode.
Application and installed-package checks use controlled instruction/model/native
providers; actual qualification is recorded separately in [Testing](TESTING.md).
General routes, in-motion replanning,
recovery, network instruction delivery and a generic skill framework are outside
this application.


### In-motion business revision

`RevisionNavigationTask` is a concrete, opt-in application: initially visit A,
accept at most one **stop** or **redirect_b** during measured A motion, and
otherwise complete only A. Use Harness profile
`scoped-two-context-nav2-revision-v1` from the immutable dependency in
[workspace.repos](../workspace.repos). Fixed A→B and released-A checkpoint tasks
keep their existing profiles and behavior.

The caller lends Session and a cooperative provider implementing
`poll(context, deadline, stop_requested)`, returning `None` or one instruction.
The caller owns provider resources and Session close. After associated A native
acceptance/current authority/pending outcome, public map measurements must span
at least 0.5 simulation seconds and exceed 0.1m displacement to open one window.
Its deadline is at most ten seconds, clipped to A's original operation/task
budget. The context binds task/revision, A request/operation/native goal, and
Session/map/epoch/frame. Instructions echo those fields and choose `stop` or
`redirect_b`; optional metadata is discarded. Invalid/foreign/expired input is
ignored, without refreshing the window or cancelling A. A terminal race closes
it. Global stop, provider failure, bad feedback or expired execution budgets
cancel/help with no B.

A valid instruction cancels exact A **before any model wait**. The application
waits at most fifteen seconds, clipped to A's remaining budget, for the public
correlated terminal/output receipt, explicit unexpired fact and settled/released authority. Only Harness
can establish the native/outlet/quiet/successor readiness boundary. Cancel ACK
or an Agent pose cannot grant reuse. `stop` returns `stopped_by_instruction` with
no completed site and no second model call; unconfirmed release returns
`needs_help`. Actual cancelled/succeeded race outcomes remain in the report.

Redirect uses one `after_revision` proposal (`visit_b`/`help`), bound to the
normalized instruction, `revision_id` and fresh public measurements. It does not
require arrival at A. After the proposal the Agent rechecks A release, identity,
health and a stable pose, then reserves/submits B once with the fresh reference.
An ambiguous request retains its ID and is never replayed. Completion reports
`completed_sites=[A]` without instruction, or `[B]` after redirect. Final model
assessment uses that `completion_site`; task verdict stays unassessed and native
cleanup unknown. Final B remains current/pending.

The 240s task / 30s decision / 160s operation budgets (public maximum 147000ms)
and 45s caller wait are unchanged. Polling targets 100ms cooperatively; provider
and Session calls have no hard preemption guarantee. No background model thread,
arbitrary target, recovery, Owner restart or hard-stop qualification is added.
See the [explicit tutorial](../examples/navigation/README.md#run-the-in-motion-revision-task)
and [fixed-pair qualification](TESTING.md#in-motion-revision-qualification).
New bounded Humble/Nav2 runs include stop, redirect, no instruction, selected
invalid/failure cases and an actual host-model redirect; matching videos retain
that limited scope. Installed synthetic native checks alone do not establish
those results.

### One backup after confirmed failure

[RecoveryNavigationTask](../src/robot_agent/navigation_recovery.py) defines a
business goal that permits registered B as one backup: visit A; if its navigation
explicitly fails and Harness releases it, ask once whether to visit B or seek
help. A success finishes only A. This task must not substitute for a different
application that strictly requires A. Default task/CLI behavior and the published preview stay unchanged.

Use the immutable [Harness dependency](../workspace.repos) and an explicitly
prepared `scoped-two-context-nav2-failure-recovery-v1` Owner. The existing site
coordinates remain fixed. `expected_map_id` defaults to `turtlebot3-world-v1`;
the caller may explicitly bind a prepared scene's other map identity. Capability,
measurement and reference must all match it, and Session/map/epoch must remain
unchanged throughout the task. This does not qualify arbitrary maps, register
new sites or verify map content. The task borrows
the public Session and a backend implementing
`decide(context, observation, deadline, stop_requested)`; the caller owns
backend resources and connection close.

Only accepted, correlated native `failed` A with no result, explicit no-output
disposition, settled/released receipt, unchanged admission/scope/goal/deadline
and no observed cancellation/expiry selects `after_failure`. Pending closure
continues within A's original operation budget; revoked, cancelled, ambiguous,
unconfirmed or regressed facts require help. The Agent trusts the declared
Owner's release assertion, including its native/quiet/successor obligations;
it does not inspect ROS closure or label the site physically unreachable.

One proposal receives fresh whitelisted map measurements and `failure_context`:
recovery ID, A request/operation/goal, original observation reference and native
failed outcome. Return `visit_b` or `help`, echo `recovery_id`, `request_id`,
integer `operation_id` and `goal_id`, and preserve the usual task/phase/proposal
observation fields. Unknown optional metadata grants no authority. After the
proposal, recheck A release, current capability, Session/map/epoch, input health
and stable fresh pose before issuing one B with the new Owner-issued reference.
Arrival at failed A is not required.

Failed A never counts as a visit. Completion names only A or only B; final
observation assessment uses that site's measurements. B failure, unknown
submission or later help never triggers another recovery, A retry, third site
or reset. The original 240s task, 30s proposals and 160s operations clipped to
the public 147000ms maximum remain unchanged. Calls remain cooperative without
hard preemption. Final B retains pending settlement, task verdict unassessed
and native cleanup unknown.

The installed CLI explicitly selects this task with `--task recovery`;
`--expected-map-id` binds the operator-prepared scene and is refused for the
default fixed task. The host relay also requires explicit recovery mode and the
same map. It reconstructs the failure identity and public measurements, then
serves prepare/final for A success or prepare/after_failure/final for one backup.
Credentials and the private host working directory/raw logs remain outside
every container mount; the proposal answer crosses the shared relay exchange.
The [prepared-owner entry](../examples/navigation/README.md#connect-the-single-backup-task-to-a-prepared-owner)
does not create a recovery scene.

This entry has [application/installed checks](TESTING.md#single-backup-software-checks).
Controlled paired Humble/Nav2 scenes cover A-only success, one backup, help,
missing successor readiness, failed backup, foreign proposal and global stop.
A new bounded actual-model/host-relay pair is recorded in Testing; its scene
preparation in those original runs remains research-specific. The
[public scene tutorial](../examples/navigation/README.md#run-the-single-failure-recovery-task)
now selects the fixed normal/occupied-A scene and failure profile explicitly.
[Homepage recordings](https://xiao-yang25.github.io/robot-harness/#recovery-demos)
retain their original pairing and do not record those subsequent public commands.

## Models and algorithm providers

Robot tasks may combine business LLM/VLM decisions, VLA or learned action
policies, perception/state estimation, navigation/avoidance, and speech input or
audio output. They may also use deterministic algorithms. Agent owns goals,
context interpretation, skill selection and business retries; this does not make
every provider part of the Agent repository. Perception can feed skills or native
control stacks directly, and a skill can delegate to an existing navigation stack.
Speech recognition supplies input for intent interpretation; speech synthesis
supplies feedback rather than execution authority.

ALOHA uses Codex visual proposals and a fixed ACT action policy. The local
navigation application uses text proposals over public map feedback and delegates
movement to Nav2. It does not deliver a general VLA, perception, avoidance or speech
framework. Future tasks should select only needed capabilities and declare their
versions, observation/action semantics, deployment, timing, resource needs and
unavailable-input behavior. Harness Runtime coordinates execution lifecycles;
providers retain model-specific inference, and native outlets retain applicable
command checks and device protections. Late outputs must not revive cancelled
motion. Qualify both the selected capability and its contribution to the task;
model metrics alone do not establish task success or a physical stop guarantee.

## Reading paths

| Goal | Read |
|---|---|
| Try the developer preview | [Version and pairing](../README.md#developer-preview), [navigation tutorial](../examples/navigation/README.md) and [verification scope](TESTING.md#developer-preview-verification) |
| Understand the current application | [ALOHA contract](#aloha-application) and [implementation](../src/robot_agent/handoff.py) |
| Prepare and run ACT / ALOHA | [Skill setup](../skills/aloha/README.md) and [dependency pin](../workspace.repos) |
| Understand model proposals | [Run ALOHA](#run-aloha) and [adapter](../src/robot_agent/codex_decision.py) |
| Test or evaluate a run | [Testing and qualification](TESTING.md) |
| Report a problem or propose a change | [Contributing](../CONTRIBUTING.md) |

This page owns the [ALOHA](#aloha-application) and [navigation](#navigation-application)
task contracts; the README provides the project and preview entry. The skill guide
owns environment setup commands; the [fixed profile](../src/robot_agent/handoff_profile.json)
owns the evaluation
predicate. Testing documentation explains checks and their limits.

New applications should document goal, initial conditions, observations, allowed
skills, budgets, outcomes and supported recovery alongside a runnable tutorial.
Extract shared guidance when actual consumers need it. Keep research plans, raw
experiments, checkpoints and private configuration outside this repository.

[Existing-agent MCP integration](https://github.com/xiao-yang25/robot-harness/tree/master/integrations/mcp)
is another Harness consumer path. It does not replace this application's task
state. The application uses [MIT OR Apache-2.0](../LICENSE); see
[contribution terms](../CONTRIBUTING.md#licensing-status). Start with the
[developer preview](../README.md#developer-preview); release checks and actual
external reproduction are distinct from historical qualification.

## ALOHA application

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


### Run ALOHA

Run commands from the repository root.

Follow [ACT / ALOHA setup](../skills/aloha/README.md) to install the pinned skill
and Harness dependency, and explicitly prepare model weights outside Git.
Select an available visual model and authenticate the Codex CLI yourself.

```sh
# Run after skill setup, including its Harness PYTHONPATH.
skills/aloha/.venv/bin/robot-agent-handoff --output /path/to/fresh-run \
  --checkpoint /path/to/migrated-checkpoint --device mps --seed 0 \
  --model YOUR_AVAILABLE_MODEL
```

Use `--device cpu` in the documented Linux environment. The proposal adapter
runs an ephemeral CLI with user configuration ignored, tools disabled and a
maximum 60-second decision window. It is a cooperating backend, not a security
sandbox or a general robot agent framework.

`report.json` records task state, decisions, receipts and cleanup. `decisions/`
contains model inputs and outputs; `episodes/` contains the Harness trace/video.
Raw runs may contain private prompts and local paths; review and redact before
sharing. A successful CLI exit requires completed stages and confirmed cleanup;
it does not establish independently verified task success.


### Evaluate ALOHA

After the Session closes, run the separate evaluator in the pinned skill environment.
See [evaluation commands and verdicts](TESTING.md#independent-evaluation).
Its report never changes the application report or authorizes another operation.


## Navigation application

The bounded [NavigationTask](../src/robot_agent/navigation.py) application uses the prepared `scoped-two-context-nav2-shim-v1`
owner, visiting registered A then B. `NavigationTask` borrows the public
`NavigationSession`; its decision backend returns only visit/help/final-assessment
proposals, with task/phase/issued-observation identity. It does not own ROS,
Core, native UUIDs, controller policies or physical evaluation.

Each proposal consumes a whitelist of current map pose, simulation sample time,
sensor health and registered sites. The one-second admission reference may expire
while the model thinks. Keep the model's original reference, then re-observe:
require the same session/map/frame/epoch, nondecreasing sample time, valid sensor
health and no more than 5cm pose change while no new task is submitted. Use the
new owner-issued reference only after those checks; log both references. A changed
scene or binding requests help, without replanning/retrying. This is a finite
idle-scene revalidation rule, not general obstacle/perception change detection.

Reserve request ID before sending; ambiguous submission triggers best-effort
cancel/status for that exact ID, never another admission. Correlate result and
receipt with the submitted request/site/operation and actual native identity.
A must settle/release before B. B may return accepted output with pending
settlement; the task can report an observation-based assessment, but never release
Core or claim resource reuse. The CLI owns connection close and reports its
shutdown intent separately from native termination; caller failure cancels the
retained request. No automatic reset or task replay.

Use explicit model/executable and output paths. Default application budgets are
240 seconds including startup, 30 per proposal, 160 per operation with the owner's native
147000ms maximum respected; at most three proposals/two submissions. The model adapter
has a five-second version-probe timeout. The proposal CLI runs with its tools disabled.
Reuse the existing bounded subprocess lifecycle
without changing ALOHA signatures. Keeping a separate copied CLI loop was rejected
because it would duplicate cancellation/late-answer checks; extending the ALOHA
prompt/schema was rejected because its measurements and task phases are different.

Acceptance: fresh installed public consumption; normal A→B with new observations,
A released/B pending, separate physical evaluator; stale/foreign/changed or late
proposals and unavailable/pending/revoked/mismatched operations admit no next task;
cancellation and ambiguous submission preserve cleanup obligations. Preserve
ALOHA/process tests, verify actual subprocess teardown and independently review
this ownership/proposal boundary. Live model and native simulation qualification
are distinct from controlled tests; both require their own recorded evidence.


The existing [ALOHA contract](#aloha-application) stays unchanged.
[NavigationCodexDecision](../src/robot_agent/navigation_decision.py) supplies the
text prompt/schema; both proposal adapters share the private bounded CLI lifecycle.
[The navigation CLI](../src/robot_agent/navigation_cli.py) owns connect/close and
keeps close intent, pending settlement and unknown native cleanup in its report.
The [host-to-container proposal relay](../examples/navigation/README.md#run-with-a-host-model)
is delivered for this local tutorial, not a general remote provider protocol.
[Testing](TESTING.md#navigation-candidate-qualification)
records the installed normal task and unresolved transport/fault scope.


### Planned installed navigation evaluation

**Design only.** Navigation currently has no installed physical evaluator or
public truth collector. Existing tutorial runs and recordings retain their
recorded scope. The first increment will cover the fixed A→B task in the normal
TurtleBot3 Waffle / Gazebo Classic / Humble scene, with the existing scoped Nav2
profile. Checkpoint, revision, recovery, other worlds and hardware need their own
later extensions; this plan does not qualify them.

Agent will own one offline, task-specific evaluator, following the installed
ALOHA evaluator's `--run` / fresh `--output` pattern and 0/1/2 exit codes.
Harness simulation will own an explicitly enabled passive collector and its
process cleanup. Collection must not gate native submission, supply model input,
alter Owner receipts, or grant execution authority. No new framework, model
dependency, general evaluator service or source digest is required.

| Input | Purpose |
|---|---|
| Existing `run.json`, scene/profile records | Identify the actual isolated run, map, selected controller and observed launcher/container outcome |
| Existing `caller.jsonl` and `agent/report.json` | Associate A/B requests, operations, native goals, task identity and the Owner's reported release before B |
| New passive samples and collector outcome | Record same-run Gazebo model poses, terminal-event association, container identity and collection completeness |

The installed predicate will fix A=(0.7,-0.5), B=(-1.5,-0.5), the existing
0.25m XY arrival limit and the normal scene's map/world relationship. It must
check actual targets, scene/map/profile and sample identities against that
predicate, not trust an arbitrary target or threshold supplied by a report.
The fixed scene's map/world alignment must be recorded and checked during
collection; unknown alignment cannot yield a physical success. Required numbers
must be finite, required associations unique, and task/operation/scope/generation/
native-goal relationships consistent. Extra optional metadata is allowed.

Samples use the same container monotonic clock as the Owner's `arrival` event,
which follows native success and fresh localization. Let `t` be that event's
`steady` value: require `t <= started <= finished <= t + 5.5`, with a five-second
pose-query deadline. For A, also require `finished < b_reserved.steady`, where
`b_reserved` is the associated B `core_native_reserved` event emitted before
the native send. This proves capture before B's native transmission, not before
the caller's RPC; neither post-dispatch `core_admitted` nor `goal_sent` supplies
that stronger caller boundary. Missing boundary or missing, duplicate, foreign,
late or nonfinite samples yield `unknown`; they do not trigger another run.
Host wall time and ROS simulation time cannot substitute for this clock relation.

The goal verdict and execution facts remain separate:

- `succeeded`: the fixed task's associated A/B sequence and two valid physical
  samples satisfy the declared arrival predicate.
- `failed`: otherwise complete associated evidence contradicts a required goal
  condition, such as a measured endpoint outside the limit.
- `unknown`: unsupported scope or missing/invalid/ambiguous evidence prevents
  adjudication. Help, cancellation or process failure alone is not a complete
  physical failure measurement.

The report will retain the consumed predicate and metrics, plus separately
labelled Agent status, native outcomes, Owner-reported settlement/authority and
observed process cleanup. In particular, goal success can coexist with final B
pending. This evaluator will not re-prove native child closure or promote the
Owner's assertion into independent native-resource verification. It will not
modify `agent/report.json`, its `task_verdict=unassessed`, or future decisions.

The command must refuse an existing output before evaluating, parse incomplete
input into a retained `unknown` report when possible, and be run once per new
run. Offline parsing uses no Docker, ROS, credentials or model calls. Samples
are trusted local recordings, not tamper-proof attestations; only acquisition
needs the declared Gazebo environment. Historical evidence is not re-evaluated.

Delivery will require focused success/failure/unknown and association checks,
fresh wheel installation without research imports, one new public fixed-task
run with its single evaluator, one independent safety-decision check, and
applicable CI. This design adds no runnable command yet.
Collector checks must also cover collection disabled, unsupported scope rejected
before container creation, partial startup, slow/failed queries, and interruption
or timeout with live query children. Observe actual child exit/reaping within the
existing budgets; these checks do not repeat physical or settlement adjudication.

### Run navigation

Build/install the exact Harness commit in [workspace.repos](../workspace.repos),
including its optional Python bridge, and prepare its isolated simulation owner
as described in the [owner setup](https://github.com/xiao-yang25/robot-harness/tree/9278fea6249e61c1533defd4b39ea3d776f1a2ae/integrations/ros2/nav2_session).
Install this Agent application, then connect to that owner's private endpoint:

```sh
robot-agent-navigation --endpoint /path/to/navigation.sock \
  --output /path/to/new-task --model YOUR_MODEL
```


The matching owner must also allow bounded caller think time. This
30-second proposal application uses owner `--caller-wait-seconds 45`, covering
proposal time and public RPC allowance. The in-container simulation shell also
reads `M6_CALLER_WAIT_SECONDS=45`; setting it only on the host does not propagate
it through the simulation launcher.
The owner's unconfigured final-close wait is 10 seconds; a model reply can exceed
it and leave the task needing help. This idle configuration does not increase
native deadlines, observation TTL or physical stopping guarantees.


For a complete scene, follow the [navigation tutorial](../examples/navigation/README.md):
controlled proposals by default or opt-in host Codex proposals. See
[recorded qualification](TESTING.md#public-host-model-navigation-workflow) for
actual model runs and [controlled qualification](TESTING.md#public-controlled-navigation-workflow)
for the separate no-model path.
