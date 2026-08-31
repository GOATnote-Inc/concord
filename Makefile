PY=.venv/bin/python

venv:
	python3 -m venv .venv && .venv/bin/pip install --quiet anthropic pyyaml

demo:
	$(PY) server.py

demo-forced:
	CONCORD_FORCED=1 $(PY) server.py

# Evidence delivered through Nexla (requires NEXLA_SESSION_TOKEN and
# CONCORD_NEXSET_ID in the environment; scripts/nexla_evidence_flow.py prints the id).
demo-gov:
	CONCORD_NEXLA=live $(PY) server.py

rehearse:
	$(PY) rehearse.py

rehearse-forced:
	$(PY) rehearse.py --forced

reset:
	curl -s -X POST localhost:8901/reset >/dev/null; echo reset
