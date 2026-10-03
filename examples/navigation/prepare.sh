#!/usr/bin/env bash
# Run in the declared Ubuntu22.04 amd64 container with fresh /consumer mounts.
set -euo pipefail
[[ -f /.dockerenv ]] || exit 2
for name in build install agent-install; do
  [[ ! -e /consumer/$name ]] || { echo "Existing consumer $name refused" >&2; exit 2; }
done
# The public simulation image does not need Python headers to run its default case.
# Only this disposable preparation container installs them if absent.
if ! python3 -c 'import pathlib,sysconfig; assert (pathlib.Path(sysconfig.get_path("include"))/"Python.h").is_file()'; then
  apt-get update
  apt-get install -y --no-install-recommends python3-dev
fi
trap 'chown -R "${DEMO_UID:?}:${DEMO_GID:?}" /consumer' EXIT
cmake -S /harness-source -B /consumer/build -DCMAKE_BUILD_TYPE=Debug \
  -DROBOT_HARNESS_BUILD_PYTHON=ON -DBUILD_TESTING=ON -DCMAKE_INSTALL_LIBDIR=lib \
  -DPython3_EXECUTABLE=/usr/bin/python3 -DCMAKE_INSTALL_PREFIX=/consumer/install
cmake --build /consumer/build --target _core --parallel 2
cmake --install /consumer/build
ctest --test-dir /consumer/build -R '^python_session$' --output-on-failure --no-tests=error
PYTHONPATH=/pip-25.0.1-py3-none-any.whl python3 -m pip install --no-index --no-deps \
  --target /consumer/agent-install /robot_agent-0.0.0-py3-none-any.whl
