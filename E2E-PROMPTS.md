# E2E tests of the role-based approach without explicitly invoking an agent

The test passes if roles are selected and started **automatically**: the prompt
does not mention agents, roles, delegation, or the skill.

## How to read the results

| Indicator | Where to look | Expected result |
|---|---|---|
| Roles listed | session log | the calling session received the role list via `mavis_agent_list` |
| Roles selected | subagent panel | agent names from the 36-role set (for example, `research`, `verify`, `code_review`), not `worker`/`explore` |
| Role identity retained | subagent panel | each subagent has its own icon and role name, not the built-in executor's icon |
| Role model | runtime log (`local_runtime_token_usage`) | child sessions run in AUTO mode: MCode resolves the model itself |
| Zones do not overlap | zone reports | each zone has its own report file outside the customer's project |
| Role selected by description | session log | the calling session received the role list via `mavis_agent_list` and chose a role based on the 'Use when' entry in its description |

## Test 1. Three independent aspects (baseline)

```text
Review the repository at C:\Claude\IT\minimax-code-customizations in three independent
areas: (1) correctness of error handling in router/ and scripts/, (2) presence and
completeness of test coverage for router/ modules, and (3) security: secrets and keys in
code and configuration, unsafe calls, and data access. For each area, provide a
separate finding: what you checked and how, what you did not check, specific
links to files and lines, and an overall status.
```

What matters here: the aspects are numbered, and each is a self-contained
review with its own type of response. The prompt does not name any roles.

## Test 2. One large zone, broad coverage

```text
Assess whether the repository at C:\Claude\IT\minimax-code-customizations is ready for
publication in a public repository: security, test quality, and maintainability. For each
aspect, provide a separate finding with verifiable claims and links to files and lines,
what was not checked, and an overall status.
```

## Test 3. Different competencies in one task

```text
Analyze the code in C:\Claude\IT\minimax-code-customizations: where decisions about
models and roles are made, how well those decisions are supported by facts in the repository,
and whether there are places where behavior is not guaranteed by code. Provide three separate responses:
the facts and their sources, an assessment of the supporting evidence, and a search for uncovered areas. In each response, include
links to files and lines and a list of what remains unchecked.
```

## Failure indicators

- If the subagent panel shows `worker` / `explore` / `verifier` instead of named roles,
  the role was not selected and the task went to built-in agents.
- If the role ran (its prompt was used) but the panel shows a built-in executor, the role was invoked
  by something other than its bare name. Invoke the role by its bare agent name from the environment registry.
- One subagent handles everything — decomposition did not happen.
- One report file covers several zones, or a report is outside its assigned directory —
  the artifact contract was violated.

## Common failure causes

| Symptom | Cause | What to do |
|---|---|---|
| No role agents in the panel | the agent list is loaded at session startup | open a new MCode session |
| Role not selected based on its description | the calling session did not consult the role registry | check that the role description includes a 'Use when' entry and that the `mavis_agent_list` tool is available |
| `Unknown agent: <role>` | the role is not installed in the profile | `python -X utf8 scripts/install_roles.py` |
| `MODEL_SELECTION_INVALID` | a pinned model is not in the runtime catalog | fix `model` in the role's front matter and reinstall the roles |
