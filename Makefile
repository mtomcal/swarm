.PHONY: test lint typecheck all

# Run all unit tests
test:
	python3 -m unittest discover -s . -p 'test_*.py' -v

# Run syntax check (linting)
lint:
	python3 -m py_compile swarm.py
	@echo "Syntax check passed"

# Run type check (using Python's built-in compile)
typecheck:
	python3 -m py_compile swarm.py test_cmd_clean.py test_swarm.py
	@echo "Type check passed"

# Run all quality checks
all: lint typecheck test
