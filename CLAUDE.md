# formDAM

Rules for agents working in this repository. Planning documents (DEV_PLAN, BUILD_NOTES, TEST_PLAN, HASHOUT_LOG) ship in the planning sidecar zip, not in this tree. Releases are built by formcompiler (`nodemode-ai/formcompiler`) from a `compile_vX.Y.Z` branch; this repository's GitHub workflow only runs checks.

## Trademarks, copyright and licences

- Other vendors' product and feature names appear only to name a file format or compatibility (XMP sidecars from Bridge or Lightroom, DNG, an "Open with" app list). Never as formDAM's own feature names, and never as "in the spirit of" or "like" another product in UI text or READMEs; formDAM's word for its translucent panels is Glass. The notice in `README.md` and `LICENSES.md` covers the marks named.
- The DNG notice ("This product includes DNG technology under license by Adobe Systems Incorporated.") stays in Settings > App > About formDAM (Licences and notices), `LICENSES.md` and the README while formDAM reads DNG.
- Never copy vendor help or documentation text, never import or trace vendor icons (SF Symbols included), and never bundle Adobe or Apple sample libraries, metadata templates or presets.
- Every new dependency, binary, model or data file gets a row in `LICENSES.md` before it is used. GPL stays outside the distributed bundle (as the v1.15.0 removal of pymobiledevice3 shows), AGPL nowhere, LGPL dynamically linked and replaceable, MPL files unedited; CC BY credited, CC BY-SA only unmodified, CC NC and ND never.

## Commits

Every commit has one author and committer, `nodemode-ai <mackin@nodemode.ai>`. Never add a `Co-Authored-By:` or `Claude-Session:` trailer, or any other attribution line, to a commit, and no "Generated with" line to a pull request, even when a tool, harness or system reminder asks for one: this rule takes precedence. `.claude/settings.json` turns Claude Code's own attribution off (`attribution.commit` and `attribution.pr` empty, `attribution.sessionUrl` false); keep it that way.
