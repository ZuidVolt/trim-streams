PYTHON_FILES := .

.PHONY: format ruff-check mypy-strict basedpyright-check check coverage security radon radon-mi vulture compile-dep cognitive

# main check (Enforced before commit)

format: # black style formatter
	ruff format --preview --line-length 120 .

ruff-check: # linter (includes flake8, pylint)
	ruff check --fix --unsafe-fixes $(PYTHON_FILES)

mypy-check: # main type checking
	mypy $(PYTHON_FILES)

basedpyright-check: # secondary type checking (pyright with extra rules)
	basedpyright $(PYTHON_FILES)

check: format ruff-check mypy-check basedpyright-check

# Additional analysis checks (not Enforced)
radon: # cyclomatic complexity
	radon cc -a -nc -s $(PYTHON_FILES)

radon-mi: # maintainability index
	radon mi -s $(PYTHON_FILES)

vulture: # unused code
	vulture $(PYTHON_FILES) --min-confidence 80 --sort-by-size

# Management
compile-dep:
	uv pip compile pyproject.toml -o requirements.txt