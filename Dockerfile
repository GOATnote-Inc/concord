# CONCORD (agent + split-screen UI). Akash-deployable; keyless => deterministic
# cached extraction, labeled honestly in the UI (CONCORD_FORCED=1).
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir pyyaml anthropic
COPY engine/ engine/
COPY ui/ ui/
COPY data/ data/
COPY artifacts/ artifacts/
COPY server.py rehearse.py ./
EXPOSE 8901
ENV CONCORD_FORCED=1
CMD ["python", "server.py"]
