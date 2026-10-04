.PHONY: test smoke integration rpm clean

test:
	python3 -m unittest discover -s tests -v

smoke:
	./scripts/smoke-test.sh

integration:
	./scripts/integration-test.sh

rpm:
	./build.sh

clean:
	rm -rf .build dist
	find . -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
	find . -name '*.pyc' -delete 2>/dev/null || true
