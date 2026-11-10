PY ?= python

.PHONY: snapshot repeat lag report checks live clean

snapshot:
	$(PY) src/measure.py --markets 150 --sizes 100,1000,10000 --rounds 3 --interval 45

repeat:
	$(PY) src/measure.py --markets 150 --sizes 100,1000,10000 --rounds 3 --interval 45 \
		--out data/snapshot-2026-11-10-repeat.jsonl

lag:
	$(PY) src/lag.py --snapshot data/snapshot-2026-11-10.jsonl

report:
	$(PY) src/report.py data/snapshot-2026-11-10.jsonl

checks:
	$(PY) src/checks.py

live:
	$(PY) src/checks.py --live

clean:
	rm -rf src/__pycache__
