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
| Current Harness dependency pin | A fresh installed macOS/Linux test combination and deterministic Linux ACT/MuJoCo run passed normal consumption and the finite-hold evaluator. This did not repeat visual-model qualification. |

Earlier real visual checks used Harness `3acc9aa`; the current manifest pins
`0de9eb0ee9de670adc22abc34ae294ea6a486dcd`. Do not generalize older results to
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
