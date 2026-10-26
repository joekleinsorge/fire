.PHONY: run test check
run:
	python3 -m fireplanner.server
test:
	python3 -m unittest discover -s tests -v
check: test
	python3 -m compileall -q fireplanner
	node --check web/app.js
	node --check web/children.js
	node --check web/purchases.js
	node --check web/whatif.js
