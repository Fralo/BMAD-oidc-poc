# Agents

All agents operating on this project SHALL strictly adhere to the instructions given in the present document.

## Agent behavior

Agents SHALL strictly adhere to human instructions. Deviations from the strategy or specifications provided as input MUST be validated with the human operator through an explicit check.

At every stable point, before executing tests and committing changes (see below), agents SHALL make sure they are not drifting from the initial instructions. If they are, they SHALL interrupt the current line of reasoning and remediate, potentially undoing the most recent changes; THEN they SHALL verify that the drift has been fixed; they SHALL repeat this loop until the drift has been fixed; THEN they SHALL resume the task, following the corrected course.

## Technical specifications

Agents SHALL strictly adhere to documented technical specifications. Agents MUST limit themselves to the adoption of the technologies and libraries listed in the documentation. Agents MUST NOT introduce additional/alternative technologies or libraries. If a problem is not solvable without the addition/replacement of one or more elements from this list, the agent MUST obtain explicit approval from the humen operator in order to do so.

Agents MUST take the project context, as described in [PROJECT_CONTEXT](./PROJECT_CONTEXT.md), into consideration at all times.

## Git operations

Agents SHALL commit frequently, at every point of stability within the execution of a task. Commit messages SHALL adhere to the [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/#specification) standard, without using the (scope) syntax.

IMPORTANT: before each commit, agents MUST make sure that all quality checks execute successfully. Quality checks are: `uv run ruff check`, `uv run ruff format --check`, `uv run ty check`, and the full test suite (e.g. `uv run pytest`). Type checking: both errors and warnings from ty must be fixed; do not add blanket suppressions unless justified and documented (e.g. in comments or PROJECT_CONTEXT).