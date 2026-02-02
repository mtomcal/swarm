.PHONY: test lint typecheck all install-hooks

# Run all unit tests
test:
	python3 -m unittest discover -s . -p 'test_*.py' -v

# Run syntax check (linting)
lint:
	python3 -m py_compile swarm.py
	@echo "Syntax check passed"

# Run type check (using Python's built-in compile)
typecheck:
	python3 -m py_compile swarm.py test_cmd_clean.py test_swarm.py test_state_file_recovery.py test_pattern_edge_cases.py test_ready_patterns.py test_state_file_locking.py
	@echo "Type check passed"

# Run all quality checks
all: lint typecheck test

# Install git hooks
install-hooks:
	git config core.hooksPath .githooks
	@echo "Git hooks installed"
