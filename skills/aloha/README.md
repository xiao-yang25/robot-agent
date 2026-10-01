# ACT / ALOHA consumer setup

This is the first experimental skill environment: macOS arm64, Python3.12 and
MPS, with the versions in `uv.lock`. Linux model/render qualification is pending;
the lock deliberately covers only this platform. Selecting `cpu` is supported by
the worker but has not qualified this complete application.

The application bundles `robot_agent.aloha_worker`, not model weights. This worker
uses the pinned Harness's private version2 candidate transport; it is not a
stable standalone plugin interface. It receives RGB/joints and proposes up to100
joint targets. Harness owns the simulator, candidate queue, admission and cleanup.

## Prepare the application and Harness

Run at the Robot Agent repository root with `uv` installed:

```sh
uv sync --frozen --project skills/aloha
uv pip install --python skills/aloha/.venv/bin/python --no-deps .
```

The setup requires access to the package index and the two pinned Git sources.
It creates a separate local environment; it does not change global Python or
install research tools. The dependency lock records provider-supplied identities;
there is no additional project digest chain.

[`workspace.repos`](../../workspace.repos) pins the Harness source dependency.
Use an existing checkout at that commit, or clone beside this repository:

```sh
git clone https://github.com/xiao-yang25/robot-harness.git ../robot-harness
git -C ../robot-harness checkout 3acc9aa08f0ae2b976030c03092e47e64947dc40
cmake -S ../robot-harness -B ../robot-harness/build-agent \
  -DROBOT_HARNESS_BUILD_PYTHON=ON -DCMAKE_INSTALL_LIBDIR=lib \
  -DPython3_EXECUTABLE="$PWD/skills/aloha/.venv/bin/python"
cmake --build ../robot-harness/build-agent --target _core --parallel 2
cmake --install ../robot-harness/build-agent --prefix "$PWD/skills/aloha/harness-prefix"
export PYTHONPATH="$PWD/skills/aloha/harness-prefix/lib/robot-harness/python"
```

See [Harness build requirements](https://github.com/xiao-yang25/robot-harness/blob/3acc9aa08f0ae2b976030c03092e47e64947dc40/bindings/python/README.md#build-and-run).
The extension must match the interpreter ABI. Do not replace an existing checkout
or prefix that contains other work; choose new paths instead. Record the Agent's
actual checkout commit alongside this pinned dependency for a delivered combination.
Obtain this application from [Robot Agent](https://github.com/xiao-yang25/robot-agent)
at the actual commit reviewed in its pull request. The Agent checkout identifies
its own version; the manifest pins its one-way Harness dependency.

## Prepare weights explicitly

The public model is
[`lerobot/act_aloha_sim_transfer_cube_human`](https://huggingface.co/lerobot/act_aloha_sim_transfer_cube_human/tree/ba73b2766f1371cdc133ca4efb97eb090d744625).
Download its four allowed files at the fixed revision, then migrate locally:

```sh
skills/aloha/.venv/bin/python -m robot_agent.prepare_aloha download \
  --output /absolute/new-original-assets
skills/aloha/.venv/bin/python -m robot_agent.prepare_aloha migrate \
  --source /absolute/new-original-assets --output /absolute/new-migration
```

An already downloaded original at that revision can be used as `--source`.
Migration requires no Hub connection, uploads nothing, preserves the source and
refuses an existing destination. It applies CPU/no-ImageNet-download configuration
overrides, uses upstream processor migration and directly compares learned tensor
keys/values. `migration-check.json` reports those checks, not task performance or
the authenticity of an arbitrary operator-supplied source. Normalization feature
statistics are checked for finite values and nonnegative deviations.

Failed downloads/migrations retain partial output for diagnosis. Use a fresh
destination after investigating the error; no automatic retry or overwrite occurs.
Neither setup nor task startup reads a Hub token; download uses `token=False` and
implicit Hub credentials are disabled. Upstream model-card publishing validation
is disabled only during offline migration.

## Run one task

Use an operator-authenticated Codex CLI and choose an available model explicitly:

```sh
skills/aloha/.venv/bin/robot-agent-handoff --output /absolute/new-run \
  --checkpoint /absolute/new-migration/checkpoint --device mps --seed 0 \
  --model YOUR_AVAILABLE_MODEL
```

The default worker comes from the installed Agent package. `--worker-script` is
an optional trusted-local override, not a remote plugin input. The same environment
must contain the model and renderer dependencies for the child host/worker.
See the [application contract and evidence limits](../../README.md#task-contract).
Reports and recordings are private local evidence; do not commit them or weights.

Credits: ACT/ALOHA model and migration from
[LeRobot](https://github.com/huggingface/lerobot/tree/e595b7902714ba51f91e47523f66f89c5181b649),
simulator from [gym-aloha](https://github.com/huggingface/gym-aloha/tree/bd3325740ea8d1c97411c41ea1e0f4ce0a7de8da).
Upstream sources/model retain their own terms; this project's license is pending.
