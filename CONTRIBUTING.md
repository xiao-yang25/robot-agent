# Contributing

Robot Agent is experimental. Start with [documentation](docs/README.md),
[task contract](README.md#task-contract) and [skill setup](skills/aloha/README.md).

## Feedback and changes

Use [Issues](https://github.com/xiao-yang25/robot-agent/issues) for problems,
reproduction reports and task proposals. Include the Agent commit, pinned Harness
revision, environment, expected/observed behavior and minimal redacted output.
Distinguish model decisions, execution failures and independent evaluation.
Do not upload credentials, private prompts, local paths, weights or raw runs.

Keep changes focused. Agent owns strategy, model adapters and skill preparation;
Harness owns execution authority, native resources and Core settlement. Use
public Harness interfaces and preserve that dependency direction. Document new
tasks' success criteria and observation/skill boundaries. Evaluator truth must
never drive task decisions.

Follow [testing guidance](docs/TESTING.md). Describe the concrete problem,
resulting behavior, actual checks and material gaps in a pull request against
`master`, with an English commit message. Fixture/CI success cannot substitute
for real model/physics qualification. For docs, check links/anchors and commands.
No private maintainer tool or research directory is required to contribute.

Behavior changes involving authority, cancellation/concurrency, ownership,
recovery, integrity, protocols or core public APIs require independent review.
Maintainers coordinate it; self-review does not replace it.

## Licensing status

The repository has no adopted license or settled patch contribution terms yet.
Resolve those terms before submitting patches or adopting the code. Reports and
discussion are welcome meanwhile. Third-party code, models and assets retain
their own terms; this guide is not a license grant.
