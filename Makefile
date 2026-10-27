.PHONY: run test check
run:
	python3 -m fireplanner.server
test:
	python3 -m unittest discover -s tests -v
check: test
	python3 -m compileall -q fireplanner
	for f in web/*.js; do node --check $$f || exit 1; done
