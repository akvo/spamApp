# Agentic Development Practices

A guide for building stable software with AI coding agents. These practices address the specific failure modes of agentic development — where an AI agent writes and modifies code across sessions without persistent memory of past decisions, bugs, or context.

---

## Why Agentic Development Needs Different Practices

Traditional development assumes a human developer who:
- Remembers why they wrote code a certain way
- Knows which parts of the codebase are fragile
- Understands implicit dependencies between modules
- Won't "helpfully" refactor something that was intentionally written that way

AI agents have none of this. Each session starts fresh. Without explicit guardrails, agents will:
- Change a function signature without updating all callers
- Violate an implicit contract between modules
- Re-introduce a bug that was already fixed
- Over-engineer or refactor code that was intentionally simple
- Make changes that pass unit tests but break integration workflows

The practices below compensate for these gaps.

---

## 1. Project Context File (`CLAUDE.md` or equivalent)

**What:** A single file at the project root that the agent reads at the start of every session. It is the agent's "memory" of the project.

**Must contain:**
- What the project is (1-2 sentences)
- Pointers to all other essential files (design docs, task list, contracts, changelog)
- Key architectural decisions with brief rationale
- Project structure overview
- Development workflow (TDD, build order, commands)
- Process rules (when to test, how to commit, how to handle bugs)
- Stable interfaces that must not change without updating all callers

**Rules:**
- Keep it under 200 lines — agents have context limits
- Link to detailed docs rather than inlining everything
- Update it when decisions change — stale context causes regressions

**Template:**
```markdown
# CLAUDE.md

## What This Is
[1-2 sentences]

## Essential Files
1. `docs/tasks.md` — Task list. Check before starting. Update as you go.
2. `CONTRACTS.md` — Module invariants. Never violate.
3. `CHANGELOG.md` — Recent changes. Update after each task.
4. `docs/design/hld.md` — Architecture and requirements.
5. `docs/design/lld.md` — Schema, pseudo code, test plan.

## Key Decisions
- [Decision]: [Why]

## Project Structure
[tree]

## Commands
[make targets or scripts]

## Process Rules
- [rule 1]
- [rule 2]

## Stable Interfaces
- [function signature 1]
- [function signature 2]
```

---

## 2. Module Contracts (`CONTRACTS.md`)

**What:** Explicit rules about what each module promises and what it must never do. This is the most important file for preventing regressions.

**Why agents need this:** An agent optimizing module A has no reason to know that module B depends on A always returning a list (never None), or that module C assumes A never touches the database. Without written contracts, the agent will eventually break these assumptions.

**What to include for each module:**
- What it imports (and what it must NEVER import)
- Return value guarantees (e.g., "always returns X, never None")
- Side effect rules (e.g., "must save revision before update")
- Ownership boundaries (e.g., "only pages.py combines parser + database")

**Rules:**
- Add a contract the moment you establish a pattern, not after it breaks
- Include the *reason* each contract exists
- When a contract is violated and you fix it, add a note: "Violated on [date], caused [bug]"

**Template:**
```markdown
# CONTRACTS.md

## Module: [name]
- NEVER imports [module]. Reason: [why].
- [function]() always returns [type], never None. Reason: callers don't check for None.
- [function]() MUST [do X] before [doing Y]. Reason: [data safety / consistency].

## General
- No module outside `src/` imports from `scripts/`.
- Regression tests must never be deleted.
```

---

## 3. Change Log (`CHANGELOG.md`)

**What:** A chronological record of what changed, why, and any gotchas discovered.

**Why agents need this:** The agent in session 5 doesn't know that session 3 discovered a subtle bug with hashtag extraction inside URLs. Without a changelog, it might refactor that code and reintroduce the bug.

**What to log:**
- Tasks completed
- Bugs found and how they were fixed
- Decisions made during implementation (especially deviations from the plan)
- Fragile areas discovered ("this works but is sensitive to X")
- Things that were tried and didn't work (prevents the agent from trying again)

**Rules:**
- Update after every completed task
- Keep entries brief — 1-3 bullet points per change
- Include the "why" and any non-obvious context

**Template:**
```markdown
# CHANGELOG

## YYYY-MM-DD
- Task N complete: [what was done]
- Bug found: [description]. Fixed by [approach]. Regression test: test_[name].
- Decision: [chose X over Y because Z]
- Gotcha: [thing that's fragile or non-obvious]
```

---

## 4. Task List (`docs/tasks.md`)

**What:** A structured list of tasks with statuses, estimates, dependencies, and scope.

**Why:** Agents without a task list will try to do everything at once, or skip steps, or redo work from a previous session.

**Rules for task sizing:**
- Each task should be completable in 1-3 hours by a human
- Each task should be independently testable
- Dependencies must be explicit
- Scope must be specific enough that the agent can't "creatively interpret" it

**Each task should specify:**
- Status: TODO / IN_PROGRESS / DONE
- What tests to write (TDD: tests first)
- What to implement
- How to verify (which make target)
- Dependencies on other tasks

**Rules:**
- Agent checks this file at the start of each session
- Agent updates status as it works
- Never start a task whose dependencies aren't DONE

---

## 5. Test Strategy

### 5.1 Three Layers of Tests

| Layer | What it catches | Example |
|-------|----------------|---------|
| **Unit tests** | Individual function bugs | `extract_links("[[A]] and [[B]]") == ["A", "B"]` |
| **Integration tests** | Broken seams between modules | Create page → update → verify backlinks AND revision AND FTS all correct |
| **Regression tests** | Previously fixed bugs coming back | `test_hashtag_in_url_not_extracted` |

Unit tests alone are not enough. Integration tests are what catch the "changed one module, broke the workflow" problems that plague agentic development.

### 5.2 Regression Test Protocol

When a bug is found:
1. **Write a failing test first** that reproduces the bug
2. Name it `test_*_regression` or start docstring with `"Regression:"`
3. Fix the bug
4. Verify the test passes
5. Log in CHANGELOG

**Rule: Regression tests must never be deleted.** They are the project's immune system.

### 5.3 Gate Before Commit

Create a single command that runs everything:

```makefile
check: lint test integration
	@echo "All checks passed"
```

**Rule: Never commit if `make check` fails.** This is the single most effective practice against regressions.

---

## 6. Design Docs

### 6.1 High-Level Design (HLD)

**Purpose:** Requirements, architecture, decisions, phasing. The "what and why."

**When to write:** Before any code. Updated when requirements change.

**Contains:**
- Problem statement
- Functional and non-functional requirements
- Architecture diagram
- Key design decisions with rationale
- Phasing / milestones
- What is NOT in scope

### 6.2 Low-Level Design (LLD)

**Purpose:** Schema, data structures, module APIs, pseudo code, test plan. The "how."

**When to write:** Before implementation. Updated when implementation reveals the design was wrong.

**Contains:**
- Database schema with column-level explanations
- Data structures / dataclasses
- Module-by-module API with pseudo code
- Edge cases to handle
- Test plan (what to test, expected inputs/outputs)

### 6.3 When to Update Design Docs

- When a decision during implementation contradicts the design → update the design doc, not just the code
- When a new edge case is discovered → add it to the LLD
- When a phase is complete → review and reconcile docs with reality

**Stale design docs are worse than no design docs.** They cause the agent to implement something that was already changed.

---

## 7. Development Workflow (TDD)

### 7.1 The Cycle

```
1. Pick next task from task list (check dependencies are DONE)
2. Read CONTRACTS.md for the relevant modules
3. Write failing tests (RED)
4. Implement minimal code to pass (GREEN)
5. Refactor while tests stay green (REFACTOR)
6. Run `make check`
7. Update: task status, CHANGELOG, CONTRACTS (if new invariant discovered)
8. Commit
```

### 7.2 Build Order

Always build in dependency order. A typical layered project:

```
Layer 0: Config, utilities (no app dependencies)
Layer 1: Core logic / parsers (pure functions, no I/O)
Layer 2: Data layer / database (no business logic dependencies)
Layer 3: Service layer (combines layers 1 + 2)
Layer 4: Scripts / CLI / API (calls layer 3)
Layer 5: Integration tests (tests full workflows across layers)
```

Each layer's tests should pass before building the next layer.

### 7.3 What the Agent Should Do at Session Start

1. Read `CLAUDE.md`
2. Read `docs/tasks.md` — find current task
3. Read `CHANGELOG.md` — understand recent changes
4. Read `CONTRACTS.md` — know what not to break
5. Run `make check` — verify everything is green before making changes
6. Start the TDD cycle for the current task

---

## 8. Git Practices

- **Commit after each completed task**, not after each file change
- **Commit message format:** `task-N: [what was done]`
- **Never commit if `make check` fails**
- **Never force push to main**
- **Gitignore data early:** databases, backups, exports, credentials, environment files
- **Don't commit generated files:** build artifacts, compiled output

---

## 9. Common Agent Failure Modes & Mitigations

| Failure Mode | What Happens | Mitigation |
|-------------|-------------|------------|
| **Signature drift** | Agent changes a function's params/return type, breaks callers | Stable Interfaces in CLAUDE.md. Grep for callers before changing. |
| **Contract violation** | Agent makes module A import module B, breaking separation | CONTRACTS.md with explicit "NEVER imports" rules |
| **Regression** | Agent refactors code that contained a subtle bug fix, reintroduces bug | Regression tests with "never delete" rule |
| **Scope creep** | Agent adds logging, docstrings, type hints, error handling you didn't ask for | Task list with specific scope. CLAUDE.md rule: "only make changes directly requested" |
| **Context loss** | New session doesn't know what previous session did | CHANGELOG.md updated after every task |
| **Over-engineering** | Agent creates abstractions for one-time operations | CLAUDE.md rule: "avoid premature abstraction" |
| **Silent breakage** | Unit tests pass but workflow is broken | Integration tests that test multi-step flows |
| **Stale docs** | Agent implements from outdated design doc | Rule: update design docs when implementation diverges |
| **Duplicate work** | Agent re-implements something that already exists | Task list with DONE statuses. Agent checks before starting. |
| **Unsafe changes** | Agent deletes files, force pushes, modifies data | Safety rules in CLAUDE.md. Agent confirms before destructive actions. |

---

## 10. Applying to a New Project — Checklist

When starting a new project with agentic development:

```
[ ] Create CLAUDE.md with project description and key decisions
[ ] Create docs/design/hld.md with requirements and architecture
[ ] Create docs/design/lld.md with schema/structures and pseudo code
[ ] Create CONTRACTS.md (even if empty — add contracts as patterns emerge)
[ ] Create CHANGELOG.md
[ ] Create docs/tasks.md with sized, dependency-ordered tasks
[ ] Create .gitignore (data, secrets, build artifacts)
[ ] Create Makefile with: test, lint, check targets
[ ] Set up test framework (pytest or equivalent)
[ ] Set up linter (ruff, eslint, or equivalent)
[ ] Write first test before first line of implementation code
```

Time to set this up: ~1 hour. Time it saves: every hour after that.

---

## 11. Requirement Review Protocol

Before implementing any new feature request (not in the existing task list), the agent MUST perform a two-phase review. The phases are sequential — do NOT skip to Phase 2.

### Phase 1 — Pushback (present FIRST)

Challenge the request before scoping it. Present these questions to the user and WAIT for confirmation before proceeding:

1. **Question necessity** — Is this actually needed now, or is it premature?
2. **Challenge assumptions** — Is the stated problem the real problem? Are there simpler framings?
3. **Propose alternatives** — Can existing features solve this? Would a simpler approach work?
4. **Clarify intent** — What's the actual workflow the user is trying to enable?

Do NOT proceed to Phase 2 until the user confirms the feature is still wanted after pushback.

### Phase 2 — Technical Scoping (only after Phase 1)

Once the user confirms the feature is needed:

1. **Clarify scope** — What exactly is being asked? What's in, what's out?
2. **Check impact** — Which existing modules, tests, and contracts does this touch?
3. **Check conflicts** — Does this contradict any existing design decisions or contracts?
4. **Identify edge cases** — What happens with empty input, duplicates, missing data?
5. **Flag risks** — What could go wrong? What's hard to reverse?

Present the analysis to the user before writing code. This prevents wasted work when the request needs refinement.

**Exceptions (no review needed):**
- Bug fixes (just fix it, with a regression test)
- Pre-defined tasks from the task list (already reviewed)
- Typo/formatting fixes

---

## 12. Autonomous TDD Loop

When an agent is working on a well-defined task with clear tests and contracts, it should iterate autonomously through the TDD cycle without stopping to ask permission at each step:

```
1. Read task scope, contracts, relevant tests
2. Write failing tests (RED)
3. Run tests — confirm they fail for the right reason
4. Write minimal implementation (GREEN)
5. Run tests — if fail, read error, fix code, re-run (up to 10 iterations)
6. Refactor while keeping tests green
7. Run full check (lint + all tests)
8. Update task status and changelog
```

**When to stop and ask:**
- 10 failed iterations on the same test (likely a design problem)
- Need to change a stable interface or violate a contract
- Need to change the database schema
- Task scope is ambiguous

**When NOT to stop:**
- Normal red-green cycle failures
- Fixable lint errors
- Expected import errors for modules being created

This protocol prevents the "ask permission for every line of code" anti-pattern while preserving guardrails for genuinely uncertain situations.

---

## 13. Parallel Agents (Swarms)

### When parallel agents help:
- Large-scale refactors (rename across many files)
- Independent test suites (lint + unit + integration in parallel)
- Research/exploration tasks (evaluate 3 libraries simultaneously)
- Truly independent features with zero shared files

### When parallel agents hurt (avoid):
- Sequential task chains where each task's output informs the next
- Tasks that modify shared files (conftest.py, config, shared docs)
- Tasks where contracts/edge cases discovered in one inform the other
- Small projects (<20 files) where context-switching overhead exceeds parallelism gains

### Rules if using parallel agents:
- Each agent must work in an isolated worktree (`isolation: "worktree"`)
- No two agents may modify the same file
- Shared docs (CHANGELOG, tasks, CONTRACTS) are updated by the coordinating agent after merge, not by sub-agents
- Integration tests run AFTER merge, not within each agent
- If merge conflicts arise, resolve manually — don't let agents auto-resolve
