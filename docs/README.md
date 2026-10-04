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
| Understand the current application | [Task contract](../README.md#task-contract) and [implementation](../src/robot_agent/handoff.py) |
| Prepare and run ACT / ALOHA | [Skill setup](../skills/aloha/README.md) and [dependency pin](../workspace.repos) |
| Understand model proposals | [Run](../README.md#run) and [adapter](../src/robot_agent/codex_decision.py) |
| Test or evaluate a run | [Testing and qualification](TESTING.md) |
| Report a problem or propose a change | [Contributing](../CONTRIBUTING.md) |

The README owns the task contract; the skill guide owns setup commands; the
[fixed profile](../src/robot_agent/handoff_profile.json) owns the evaluation
predicate. Testing documentation explains checks and their limits.

New applications should document goal, initial conditions, observations, allowed
skills, budgets, outcomes and supported recovery alongside a runnable tutorial.
Extract shared guidance when actual consumers need it. Keep research plans, raw
experiments, checkpoints and private configuration outside this repository.

[Existing-agent MCP integration](https://github.com/xiao-yang25/robot-harness/tree/master/integrations/mcp)
is another Harness consumer path. It does not replace this application's task
state. The application uses [MIT OR Apache-2.0](../LICENSE); see
[contribution terms](../CONTRIBUTING.md#licensing-status). A versioned preview
and actual external reproduction remain pending.

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
147000ms maximum respected; at most three proposals/two submissions. The proposal
CLI runs with its tools disabled. Reuse the existing bounded subprocess lifecycle
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


The existing [ALOHA contract](../README.md#task-contract) stays unchanged.
[NavigationCodexDecision](../src/robot_agent/navigation_decision.py) supplies the
text prompt/schema; both proposal adapters share the private bounded CLI lifecycle.
[The navigation CLI](../src/robot_agent/navigation_cli.py) owns connect/close and
keeps close intent, pending settlement and unknown native cleanup in its report.
The [host-to-container proposal relay](../examples/navigation/README.md#run-with-a-host-model)
is delivered for this local tutorial, not a general remote provider protocol.
[Testing](TESTING.md#navigation-candidate-qualification)
records the installed normal task and unresolved transport/fault scope.
