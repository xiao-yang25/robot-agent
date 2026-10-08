# Robot Agent

Observation-driven task applications for
[Robot Harness](https://github.com/xiao-yang25/robot-harness).

Agent owns goals, task strategy and model proposals. Harness coordinates execution,
results and settlement; robot stacks retain native control and device protection.

[Documentation](docs/README.md) · [Architecture](docs/DESIGN.md) · [Demos](https://xiao-yang25.github.io/robot-harness/) ·
[Testing](docs/TESTING.md) · [Contributing](CONTRIBUTING.md)

<a id="run"></a>
## Developer preview

[v0.1.0a1](https://github.com/xiao-yang25/robot-agent/releases/tag/v0.1.0a1)
is the first experimental preview. Start with the
[Nav2 A→B tutorial](examples/navigation/README.md): three controlled proposals,
with optional Codex proposals on the host.

```sh
git clone --branch v0.1.0a1 https://github.com/xiao-yang25/robot-agent.git
cd robot-agent
```

Follow that checkout's tutorial to build the Agent wheel and install its exact
[Harness dependency](workspace.repos). Navigation needs host Python3.10+, Docker
and the Ubuntu22.04 / ROS2 Humble / Gazebo Linux amd64 scene. Apple Silicon uses
Docker Desktop emulation. The default path needs no model service or weights.

<a id="task-contract"></a>
<a id="navigation-application"></a>
## Applications

| Application | Task | Setup and contract |
|---|---|---|
| Navigation | Fixed A→B, or opt-in checkpoint / in-motion instructions | [Tutorial](examples/navigation/README.md) · [Contract](docs/README.md#navigation-application) |
| ALOHA / ACT | Transfer a cube, then hold for one simulated second using visual proposals | [Skill setup](skills/aloha/README.md) · [Contract](docs/README.md#aloha-application) |

Both applications use Harness's public Session and shared execution coordinator.
Model decisions stay separate from execution authority and independent evaluation.
See [adaptation boundaries](docs/README.md#adapt-an-existing-application) for changing
models or extending an application.

Current development also exposes an experimental
[single-backup Python task](docs/README.md#one-backup-after-confirmed-failure);
its model/physics demonstration is pending.

<a id="evaluate-the-recorded-task-independently"></a>
<a id="installed-combination-ci"></a>
<a id="acceptance-and-delivery"></a>
## Results and limits

Model assessments, execution receipts and independent task verdicts are distinct.
Before requesting B, navigation releases A; final B remains accepted/pending, with
`task_verdict=unassessed` and native cleanup unknown. Inspect local process/container
cleanup separately. Fixed normal A→B has an [offline evaluator](docs/README.md#planned-installed-navigation-evaluation);
[ALOHA evaluation](docs/TESTING.md#independent-evaluation) uses its own fixed predicate.

APIs are experimental, with no cross-version API/ABI promise, physical-robot
qualification or hard stop guarantee. See [validation and limits](docs/TESTING.md),
[preview checks](docs/TESTING.md#developer-preview-verification) and
[installed combination CI](.github/workflows/combination.yml). Recorded simulations
and models retain their own versions and scope.

## Contributing

[Report a problem or propose an integration](https://github.com/xiao-yang25/robot-agent/issues).
Follow the [feedback and change guide](CONTRIBUTING.md) for version details,
redacted diagnostics and contributions.

## License

[MIT](LICENSE-MIT) OR [Apache-2.0](LICENSE-APACHE), at your option.
See the [declaration](LICENSE) and [contribution terms](CONTRIBUTING.md#licensing-status).
Models, dependencies and simulator assets retain their own terms.
