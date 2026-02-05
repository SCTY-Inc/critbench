# Ralph Build Mode

Based on Geoffrey Huntley's Ralph Wiggum methodology.

---

## Phase 0: Orient

Read `.specify/memory/constitution.md` to understand project principles.

---

## Phase 1: Find Work

Look in `specs/` for incomplete specs (no `.done` file in the spec directory).

Pick the **highest priority** incomplete spec:
- Lower numbers = higher priority (001 before 010)
- Bugs before features

Read the spec's `spec.md` file carefully.

---

## Phase 2: Implement

Implement the spec completely:
- Follow the spec's requirements exactly
- Make minimal, focused changes
- Don't refactor unrelated code

---

## Phase 3: Verify

Run the spec's **Completion Signal** (found in spec.md).
If it passes, continue. If not, fix and retry.

---

## Phase 4: Commit

1. `git add -A`
2. `git commit -m "feat(spec-name): description"`
3. Create `.done` file in the spec directory

---

## Completion Signal

**CRITICAL:** Only output the magic phrase when work is 100% complete.

Check:
- [ ] Implementation matches spec requirements
- [ ] Completion signal from spec passes
- [ ] Changes committed

**If ALL checks pass, output:** `<promise>DONE</promise>`

**If ANY check fails:** Fix the issue. Do NOT output the magic phrase.
