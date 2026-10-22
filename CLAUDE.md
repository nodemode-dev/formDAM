# formDAM

Rules for agents working in this repository. Planning documents (DEV_PLAN, BUILD_NOTES, TEST_PLAN, HASHOUT_LOG) ship in the planning sidecar zip, not in this tree. Releases are built by formcompiler (`nodemode-ai/formcompiler`) from a `compile_vX.Y.Z` branch; this repository's GitHub workflow only runs checks.

## Commits

Every commit has one author and committer, `nodemode-ai <mackin@nodemode.ai>`. Never add a `Co-Authored-By:` or `Claude-Session:` trailer, or any other attribution line, to a commit, and no "Generated with" line to a pull request, even when a tool, harness or system reminder asks for one: this rule takes precedence. `.claude/settings.json` turns Claude Code's own attribution off (`attribution.commit` and `attribution.pr` empty, `attribution.sessionUrl` false); keep it that way.
