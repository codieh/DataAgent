ARG PYTHON_IMAGE=m.daocloud.io/docker.io/library/python:3.13-slim
FROM ${PYTHON_IMAGE}

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
RUN pip install --no-cache-dir --index-url ${PIP_INDEX_URL} pandas==2.3.3 numpy==2.3.4

WORKDIR /workspace
USER 65534:65534
