FROM python:3.12-slim

RUN useradd --uid 65532 --no-create-home --shell /usr/sbin/nologin sandbox
RUN pip install --no-cache-dir pandas==2.2.3

WORKDIR /sandbox
COPY runner.py /sandbox/runner.py
USER sandbox
ENTRYPOINT ["python", "/sandbox/runner.py"]
