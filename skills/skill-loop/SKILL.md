---
name: skill-loop
description: Inspect, explain, undo, or pause Skill Loop, the automatic background process that edits the user's global CLAUDE.md, AGENTS.md, and skills, and creates new skills, from corrections the user gave and from repeated failures the agent resolved. Use when the user asks what Skill Loop changed, learned, or created, where an instruction or skill came from, to undo or revert a learned rule, to turn the loop off or on, to check that the Claude and Codex copies of a skill match, to back up the agent configuration now, or why a review failed.
---

# Skill Loop

Skill Loop runs without approval. When the user approves work ("looks good", "ship it", "thanks"), every 5 prompts in long threads, before compaction, and at session end, a hook starts a hidden background review of that session. The review:

- sees the user's words, the agent's replies, and tool activity as structure (`[TOOL name: ok]`, `[TOOL name: FAILED (first error line)]`); a failed call shows one redacted line (no paths, URLs, or secrets), and all other tool output, pasted content, and injected context are removed before any model sees them;
- uses the session's own provider (Claude sessions → `claude -p`, Codex sessions → `codex exec`, read-only, no tools);
- prefers skills: lessons about a repeated workflow go to that skill (existing, or one new skill per review); CLAUDE.md and AGENTS.md get only cross-cutting behavior. The reviewer sees the full text of skills the session loaded or named, and may rewrite a skill's description (one line) when the skill should have triggered differently;
- learns two kinds of lesson:
  - **user corrections**: the evidence quote must appear verbatim in a recent user turn;
  - **resolved failures**: code must find the same tool failing at least twice and then succeeding, and the evidence quote must be the agent's own explanation after the last failure (never the error line); these never touch the global instruction files;
- may also target the skills of the repository the session worked in (`repo:skill/<name>`, from `.agents/skills` or `.claude/skills`); those edits are always proposals, never direct writes;
- passes every edit through code gates (no URLs, secrets, permission or approval changes, no frontmatter change beyond a one-line description, no commands that run on skill load; size-capped) and a second model pass. The verifier accepts, defers, or rejects each edit. A rejected edit with a sound narrower lesson gets one more round as that narrower rule. A deferred edit (the user had not accepted the outcome yet) is held and decided again at the session's next review;
- skips a file the user changed while the review ran, and journals every edit;
- keeps shared skills identical. A skill name with a SKILL.md in both `~/.claude/skills` and `~/.codex/skills` is one shared skill. An edit to one copy also lands in the other copy as a linked change, but only while the other copy still matches the edited copy's old bytes; a drifted copy stays untouched, and the log names the drift. A new skill lands in both runtimes when neither runtime has the name. Names in `runtime_specific_skills` in `~/.skill-loop/data/config.json` are never mirrored or compared;
- commits and pushes every applied change and revert to a private backup repository (local repository `~/.agent-config.git`, work tree `~`, whitelist in the repository's `info/exclude`). The `backup` command commits hand edits too; a scheduled task runs the command.

The next session starts with a one-line notice of what changed. Held lessons and repository proposals appear once as Suggested tasks in the Claude desktop app (a notice line elsewhere); each task runs `pending show`, asks the user, then `pending apply` or `pending drop`.

## Commands

```
python ~/.skill-loop/skill_loop.py log          # recent changes: id, status, target, rule
python ~/.skill-loop/skill_loop.py show <id>    # rule, the quote it rests on, verifier reason, diff
python ~/.skill-loop/skill_loop.py revert <id>  # undo one change; a created skill is deleted; a shared-skill change reverts both copies
python ~/.skill-loop/skill_loop.py pending              # lessons that wait for the user's OK
python ~/.skill-loop/skill_loop.py pending show <id>    # rule, quote, verifier reason, diff
python ~/.skill-loop/skill_loop.py pending apply <id>   # apply through the journal (revertable); repo files then follow the repo's rules
python ~/.skill-loop/skill_loop.py pending drop <id>    # discard
python ~/.skill-loop/skill_loop.py status       # on/off, errors, held lessons, shared-skill drift, recent activity
python ~/.skill-loop/skill_loop.py shared-check # shared skills whose two copies differ (agents/ and caches ignored); exit 1 on drift
python ~/.skill-loop/skill_loop.py backup       # commit and push now; logs drift; exit 1 when the commit or push failed
python ~/.skill-loop/skill_loop.py off | on     # kill switch
```

## Working with it

- When the user disagrees with a learned rule or created skill, `revert` that change instead of editing around it, then tell them the id you reverted.
- Do not edit files under `~/.skill-loop/data` by hand. Skills listed in `exclude_skills` in `~/.skill-loop/data/config.json` are never edited; add a skill there when another source (a repo sync) owns it.
- To change a shared skill by hand, make the same change in both copies, then run `shared-check`. Add a name to `runtime_specific_skills` only when the two runtimes need different content on purpose.
- When the user approves a held lesson, run `pending apply <id>`; for a repository proposal, then sync any mirrored skill copy byte-for-byte and commit under that repository's rules.
- Offline check after a code change: `python ~/.skill-loop/tests/e2e_skill_loop.py --offline` (no model calls); drop `--offline` for the full real-model run.
- A review failure shows once at the next session start and stays in `status`. A Claude authentication failure means the standalone CLI needs `claude auth login` in a terminal; a Codex credits error means the Codex workspace needs credits.
