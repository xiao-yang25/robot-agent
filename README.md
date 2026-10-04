# Robot Agent

Observation-driven task applications for
[Robot Harness](https://github.com/xiao-yang25/robot-harness).
Experimental: no versioned release or physical-robot qualification yet.

The first application attempts an ALOHA cube transfer followed by one simulated
second of holding. A visual backend chooses bounded skills; ACT produces joint
targets; Harness owns execution and resources. Task strategy and reports live here.
The navigation application also visits registered A then B through the public
NavigationSession, using bounded text proposals and fresh map feedback.
Core is part of Harness. Existing-agent MCP consumers are a separate integration
path, rather than this application's task controller.

[Documentation](docs/README.md) · [Skill setup](skills/aloha/README.md) ·
[Testing and limits](docs/TESTING.md) · [Contributing](CONTRIBUTING.md)

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

Follow [ACT / ALOHA setup](skills/aloha/README.md) to install the pinned skill
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

## Evaluate the recorded task independently

After the Session closes, run the separate evaluator in the pinned skill environment.
See [evaluation commands and verdicts](docs/TESTING.md#independent-evaluation).
Its report never changes the application report or authorizes another operation.

## Installed combination CI

[Combination CI](.github/workflows/combination.yml) tests installed Agent and
Harness together: ALOHA uses real Session/Host/Core, and navigation uses the public
Unix Session, trusted-owner requests and real Core. External providers are explicit
no-physics fixtures.
See [CI scope](docs/TESTING.md#automated-checks); ACT, perception and physical task
success require separate qualification.

## Acceptance and delivery

The selected normal task and bounded failure checks are delivered. See
[qualified scope](docs/TESTING.md#qualified-scope) for the distinction between
real visual runs, deterministic execution and fixture tests. CUDA, other architectures,
robot bodies, recovery and hard stop guarantees must not be inferred from those
results. ALOHA and navigation now consume shared Harness execution coordination;
their physical and model qualifications remain specific to each recorded combination.

See [application artifacts and reusable boundaries](docs/README.md#application-artifacts-and-reusable-boundaries)
for what can be run today and which pieces remain task-specific. Future extraction
of shared execution mechanics preserves this application's task contract.

## License

Except for third-party material with its own notices, Robot Agent is licensed
under [MIT](LICENSE-MIT) OR [Apache-2.0](LICENSE-APACHE), at your option.
See the [project declaration](LICENSE) and
[contribution terms](CONTRIBUTING.md#licensing-status).
Models, dependencies and simulator assets retain their own terms.


## Navigation application

[NavigationTask](src/robot_agent/navigation.py) is a separate A→B application for
the prepared `scoped-two-context-nav2-shim-v1` owner. It borrows the public
`NavigationSession`; no ROS, Core internals or simulator evaluation enter the Agent.
The [task/measurement boundary](docs/README.md#navigation-application)
keeps model proposals tied to their original observation, then revalidates a fresh
owner-issued reference before submission. No automatic retry, reset or recovery.

Build/install the exact Harness commit in [workspace.repos](workspace.repos),
including its optional Python bridge, and prepare its isolated simulation owner
as described in the [owner setup](https://github.com/xiao-yang25/robot-harness/tree/13bc75e903f6005da3dd5d969f8242ce211d182f/integrations/ros2/nav2_session).
Install this Agent application, then connect to that owner's private endpoint:

```sh
robot-agent-navigation --endpoint /path/to/navigation.sock \
  --output /path/to/new-task --model YOUR_MODEL
```

Budgets: 240 seconds including application startup, 30 per proposal and 160 per
operation, respecting the owner's advertised native deadline maximum. At most
three proposals and two site submissions. The CLI owns connection close; a close
intent or local socket disposal does not prove native cleanup. The model adapter
has a five-second version-probe timeout and a bounded proposal subprocess.

One installed local Codex/GPT normal task completed with fresh map feedback and
an independent simulation evaluator. A settled/released before B; B output was
accepted with settlement pending. `status=completed` reports the application
sequence and observation assessment; `task_verdict=unassessed`, pending execution
cleanup and unknown native cleanup remain separate. See [qualification](docs/TESTING.md#navigation-candidate-qualification).
The recorded model/simulation runs are local candidate qualification; installed
combination checks verify the public dependency pin separately. This experimental
application is not a general navigation Agent, obstacle-aware model or
physical-robot qualification.


The matching owner must also allow bounded caller think time. This
30-second proposal application uses owner `--caller-wait-seconds 45`, covering
proposal time and public RPC allowance. The in-container simulation shell also
reads `M6_CALLER_WAIT_SECONDS=45`; setting it only on the host does not propagate
it through the simulation launcher.
The owner's unconfigured final-close wait is 10 seconds; a model reply can exceed
it and leave the task needing help. This idle configuration does not increase
native deadlines, observation TTL or physical stopping guarantees.

For a complete scene with the installed business application, use the
[navigation tutorial](examples/navigation/README.md): controlled proposals by
default, or explicit Codex proposals on the host with no credentials in the
network-disabled scene. See [qualification and limits](docs/TESTING.md#public-host-model-navigation-workflow).
