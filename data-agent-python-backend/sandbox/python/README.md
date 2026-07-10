# Python analysis sandbox

Build the local image before enabling Python analysis:

```bash
docker build -t data-agent-python-sandbox:latest sandbox/python
```

The defaults use the DaoCloud Docker Hub mirror and the Tsinghua PyPI mirror. Both are build arguments:

```bash
docker build -t data-agent-python-sandbox:latest \
  --build-arg PYTHON_IMAGE=python:3.13-slim \
  --build-arg PIP_INDEX_URL=https://pypi.org/simple \
  sandbox/python
```

The backend starts an ephemeral container for every analysis attempt with no network, a read-only root filesystem,
no Linux capabilities, a non-root user, and CPU, memory, PID, and timeout limits.
