# Contributing

Robot Agent is experimental. Start with the [application documentation](docs/README.md)
and [skill setup](skills/aloha/README.md).

## Feedback and changes

Use [Issues](https://github.com/xiao-yang25/robot-agent/issues) for problems,
reproduction reports and task proposals. Include the Agent commit/package version,
pinned Harness revision, selected image identity, environment, failed stage,
expected/observed behavior and minimal redacted output. The
[preview tutorial](examples/navigation/README.md#report-a-problem-or-return-to-a-previous-pair)
describes returning to a previously verified pair in a fresh directory.
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

Except for third-party material with its own notices, Robot Agent is licensed
under [MIT](LICENSE-MIT) OR [Apache-2.0](LICENSE-APACHE), at your option; see the
[project declaration](LICENSE).

By intentionally submitting a contribution for inclusion in this project, you
agree to license it under the same `MIT OR Apache-2.0` terms, without additional
terms. You retain your copyright; no copyright assignment or separate CLA is
required. You must have the right to provide the contribution under these terms.
Identify third-party material and preserve its original notices; discuss material
with different terms before inclusion. Model weights, dependencies and simulator
assets retain their own terms; this grant does not replace them.
