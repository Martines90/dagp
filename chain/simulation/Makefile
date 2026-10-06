PYTHON ?= python3
.PHONY: test pilot large verify
test:
	$(PYTHON) -m unittest discover -s tests -v
pilot:
	$(PYTHON) community.py --seeds 7 19 43 --output results/pilot
large:
	$(PYTHON) community.py --citizens 10000 --seeds 7 --output results/large
verify:
	$(PYTHON) verify.py results/pilot --replay
