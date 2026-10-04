# ACT / ALOHA consumer setup

This experimental skill environment locks macOS arm64/MPS and Linux aarch64
with Python3.12. Linux validation selects CPU inference and OSMesa rendering,
covering deterministic execution and one normal visual Agent task. CUDA execution,
other architectures and visual reliability remain unqualified. See the
[Linux consumer path](#linux-consumer-path) for its exact scope.

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
install research tools. The dependency lock records provider-supplied identities.

[`workspace.repos`](../../workspace.repos) pins the Harness source dependency.
Use an existing checkout at that commit, or clone beside this repository:

```sh
git clone https://github.com/xiao-yang25/robot-harness.git ../robot-harness
git -C ../robot-harness checkout 13bc75e903f6005da3dd5d969f8242ce211d182f
cmake -S ../robot-harness -B ../robot-harness/build-agent \
  -DROBOT_HARNESS_BUILD_PYTHON=ON -DCMAKE_INSTALL_LIBDIR=lib \
  -DPython3_EXECUTABLE="$PWD/skills/aloha/.venv/bin/python"
cmake --build ../robot-harness/build-agent --target _core --parallel 2
cmake --install ../robot-harness/build-agent --prefix "$PWD/skills/aloha/harness-prefix"
export PYTHONPATH="$PWD/skills/aloha/harness-prefix/lib/robot-harness/python"
```

See [Harness build requirements](https://github.com/xiao-yang25/robot-harness/blob/13bc75e903f6005da3dd5d969f8242ce211d182f/bindings/python/README.md#build-and-run).
The extension must match the interpreter ABI. Do not replace an existing checkout
or prefix that contains other work; choose new paths instead. Record the Agent's
actual checkout commit alongside this pinned dependency for a delivered combination.
Obtain this application from [Robot Agent](https://github.com/xiao-yang25/robot-agent)
at the actual commit reviewed in its pull request. The Agent checkout identifies
its own version; the manifest pins its one-way Harness dependency.

For qualified combinations and limits, see [Testing](../../docs/TESTING.md#qualified-scope).

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
See the [application contract and evidence limits](../../docs/README.md#aloha-application).
Reports and recordings are private local evidence; do not commit them or weights.

Credits: ACT/ALOHA model and migration from
[LeRobot](https://github.com/huggingface/lerobot/tree/e595b7902714ba51f91e47523f66f89c5181b649),
simulator from [gym-aloha](https://github.com/huggingface/gym-aloha/tree/bd3325740ea8d1c97411c41ea1e0f4ce0a7de8da).
Upstream sources/model retain their own terms. The application uses
[MIT OR Apache-2.0](../../LICENSE); this grant does not relicense the upstream
code, model weights or simulator assets.

## Evaluate one closed episode

The application includes its fixed task predicate and independent evaluator.
After `robot-agent-handoff` has closed its Session, use the same skill environment:

```sh
skills/aloha/.venv/bin/robot-agent-evaluate-handoff \
  --run /absolute/new-run/episodes --trace-name episode-0.jsonl \
  --output /absolute/new-run/task-evaluation.json
```

For Linux, invoke `/workspace/robot-agent/skills/aloha/.venv/bin/robot-agent-evaluate-handoff`
inside the consumer container with its corresponding run paths. No Codex login,
ACT inference or dynamics stepping is needed for evaluation; the pinned MuJoCo
model/assets and NumPy from this skill environment are reused. Run it once per
trace and retain its new output. The CLI refuses an existing report before
loading evidence. Exit0 means the fixed finite physical predicate passed, exit1
means it failed, and exit2 means unknown or command/output error. Keep this
verdict separate from the application/visual assessment; see
[evaluation contract](../../docs/TESTING.md#independent-evaluation).

## Linux consumer path

The selected environment is Ubuntu22.04, aarch64, Python3.12.14, CPU ACT and
OSMesa software rendering. The Docker recipe contains build/render tools and
uv0.12.13; it contains no source, model weights, Codex CLI or credentials.
It uses [dm_control's OSMesa option](https://github.com/google-deepmind/dm_control#rendering).
System packages follow Ubuntu updates; this is a pinned Python/source combination,
not a byte-identical OS image or an amd64/CUDA support matrix.

Use a **new dedicated workspace** with `robot-agent/` and `robot-harness/` as
siblings, checking Harness out at the revision from `workspace.repos`. Run from
that parent directory. Mount only this workspace, never your home directory:

```sh
docker build --platform linux/arm64 -t robot-agent-aloha:ubuntu22.04-arm64 \
  robot-agent/skills/aloha/docker
docker run --name robot-agent-aloha-linux --memory 6g --cpus 6 -it \
  --mount type=bind,src="$PWD",dst=/workspace \
  robot-agent-aloha:ubuntu22.04-arm64
```

Inside the container, create a new environment and install both packages:

```sh
export UV_CACHE_DIR=/workspace/.uv-cache UV_PYTHON_INSTALL_DIR=/workspace/.python
uv sync --frozen --project robot-agent/skills/aloha --python 3.12.14
python_bin=/workspace/robot-agent/skills/aloha/.venv/bin/python
uv pip install --python "$python_bin" --no-deps "./robot-agent[vision]"
cmake -S robot-harness -B build-agent -DROBOT_HARNESS_BUILD_PYTHON=ON \
  -DCMAKE_INSTALL_LIBDIR=lib -DPython3_EXECUTABLE="$python_bin"
cmake --build build-agent --target _core --parallel 2
cmake --install build-agent --prefix /workspace/harness-prefix
export PYTHONPATH=/workspace/harness-prefix/lib/robot-harness/python
```

The pinned upstream LeRobot source selects PyTorch2.11.0+cu128 and
TorchVision0.26.0+cu128 on Linux. These builds include CUDA dependencies even
though this path explicitly uses `--device cpu` with no GPU. The environment
occupies about6.6GiB; reserve additional space for package download/cache,
Python, model originals/migration and recordings. Do not force a CPU-index
override that conflicts with the upstream package sources. No dependency upgrade
or implicit accelerator fallback is part of this qualification.

Use the explicit download/migration entry above, with new destinations:

```sh
"$python_bin" -m robot_agent.prepare_aloha download --output /workspace/original
"$python_bin" -m robot_agent.prepare_aloha migrate \
  --source /workspace/original --output /workspace/migration
export HF_HUB_OFFLINE=1 HF_HUB_DISABLE_IMPLICIT_TOKEN=1
worker_script=$("$python_bin" -c 'import robot_agent.aloha_worker as w; print(w.__file__)')
cd /tmp
"$python_bin" /workspace/robot-harness/examples/mujoco_handoff.py \
  --output /workspace/normal-run --worker-script "$worker_script" \
  --checkpoint /workspace/migration/checkpoint --device cpu --seed 0
```

This is the existing **deterministic caller**, which always selects transfer
then hold. Its report checks continuous observations, two results/settled
receipts, stale-reference rejection, explicit reset and process reaping.
`episodes/episode-0.mp4` and its trace cover the same450-step episode.
Completion is execution evidence; business success requires the separate fixed
physical evaluator. It does not establish observation-driven visual decisions.

The deterministic native run needs network only for explicit environment/model
preparation. It can use a separate container with `--network none`, the same
mounted workspace and image. The visual application below also needs network
for its three model requests. Do not transfer host credentials into either
container. Ordinary CI uses lightweight fixtures; see [CI scope](../../docs/TESTING.md#automated-checks).

### Real visual Agent in Linux

Use the same prepared Linux environment, migrated checkpoint and exact Harness
revision. The selected visual backend is the official Codex0.159.0 Linux aarch64
musl binary. On the host, from the dedicated workspace above, download/extract
that fixed release using GitHub CLI (`gh`) and `tar`:

```sh
mkdir -p codex-download codex-bin
gh release download rust-v0.159.0 --repo openai/codex \
  --pattern codex-aarch64-unknown-linux-musl.tar.gz --dir codex-download
tar -xzf codex-download/codex-aarch64-unknown-linux-musl.tar.gz -C codex-bin
```

Mount the binary read-only into a network-enabled container. Authentication stays
inside this container; it is not included in the image or workspace mount:

```sh
docker run --rm --name robot-agent-aloha-visual --memory 6g --cpus 6 -it \
  --mount type=bind,src="$PWD",dst=/workspace \
  --mount type=bind,src="$PWD/codex-bin/codex-aarch64-unknown-linux-musl",dst=/usr/local/bin/codex,readonly \
  robot-agent-aloha:ubuntu22.04-arm64
```

Inside that container, the operator signs in through the
[official device authentication flow](https://learn.chatgpt.com/docs/auth),
checks status and selects an available model explicitly:

```sh
codex --version
codex login --device-auth
codex login status
python_bin=/workspace/robot-agent/skills/aloha/.venv/bin/python
export PYTHONPATH=/workspace/harness-prefix/lib/robot-harness/python
export HF_HUB_OFFLINE=1 HF_HUB_DISABLE_IMPLICIT_TOKEN=1
cd /tmp
"$python_bin" -m robot_agent.cli --output /workspace/visual-run \
  --checkpoint /workspace/migration/checkpoint --device cpu --seed 0 \
  --model YOUR_AVAILABLE_MODEL
```

Login confirms authentication, not model access or task success. This disposable
container's login cache disappears when it exits; sign in again for a new
container. Keep recordings and reports in the dedicated workspace. Never put
login codes, credential files or tokens in the repository, image or task report.

This recipe covers the selected Linux aarch64/CPU/OSMesa path. Qualification
limits are recorded in [Testing](../../docs/TESTING.md#qualified-scope); the image
contains neither Codex nor authentication. No CUDA/amd64 or physical-robot support
is implied.
