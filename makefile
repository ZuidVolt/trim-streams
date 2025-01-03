PYTHON_FILES := trim_streams.py validate.py

.PHONY: format ruff-check mypy-strict basedpyright-check check coverage security radon radon-mi vulture

# main check (Enforced before commit)
format:
	@ruff format --preview --line-length 120 $(PYTHON_FILES)

ruff-check:
	@ruff check --preview --fix --unsafe-fixes $(PYTHON_FILES)

basedpyright-check:
	@basedpyright $(PYTHON_FILES)

mypy-strict:
	@mypy --strict $(PYTHON_FILES)

check: ruff-check mypy-strict basedpyright-check 

# Additional analysis checks (not Enforced)
coverage:
	coverage run -m pytest
	coverage report -m
	coverage html

security:
	ruff check --extend-select S --fix $(PYTHON_FILES)

radon: # cyclomatic complexity
	radon cc -a -nc -s $(PYTHON_FILES)

radon-mi: # maintainability index
	radon mi -s $(PYTHON_FILES)

vulture: # unused code
	vulture $(PYTHON_FILES) --min-confidence 80 --sort-by-size

# Management
compile-dep:
	uv pip compile  pyproject.toml -o requirements.txt