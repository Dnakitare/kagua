# Pre-publish checklist

Blockers before the README goes public (per HANDOFF.md). Sweep run 2026-07-03.

- [x] **Trademark / prior-art sweep on "Kagua"** — CLEAR for an OSS dev tool. Findings below.
- [x] **Prior-art check on framing language** — clear with one citation obligation, folded into the README's Related work section. Findings below.
- [x] **PyPI name availability** — `kagua` is free (pypi.org/pypi/kagua returns 404). npm `kagua` also free. Claim PyPI at first release; don't squat npm.
- [x] **README screenshot** — README now leads with `docs/demo.svg`, generated from live output by `tools/render_demo_svg.py` (rerun it whenever demo output changes; it refuses to render a passing demo).
- [x] **Repo public on github.com/Dnakitare** — live 2026-07-03. Personal git identity on all commits (dnakitare@gmail.com).
- [x] **PyPI name claimed** — kagua 0.1.0 published 2026-07-03 via Trusted Publishing (OIDC): GitHub Release triggers `.github/workflows/release.yml`, environment `pypi`. No tokens stored anywhere. To release: bump version in pyproject.toml, tag, `gh release create`.

## Name sweep findings (2026-07-03)

- **USPTO / trademark**: no "KAGUA" mark found via Justia's USPTO index. The only established KAGUA brand is Far Yeast Brewing's Japanese craft beer (Nice class 32, beer). No overlap with software/SaaS (classes 9/42); confusion risk negligible.
- **GitHub**: small collisions, none blocking. `SK3CHI3/KAGUA-1.0` (Kenyan civic-transparency platform, 2 stars, same Swahili root, different domain), `Elly-L/KaguaAI` (code plagiarism detector, 0 stars), assorted personal repos. None in agent security/dev tooling.
- **Web**: no software company, startup, or security tool named Kagua. The name is dominated by the beer, a Japanese blog (kagua.biz), and Kenyan civic usage.
- **Domains**: kagua.dev and kagua.io are registered by others; kagua.sh unclear. Not needed for the OSS phase; revisit only if the paid track matures.
- **If the revenue track matures** (audit engagements, Gate 2): run a paid clearance search before invoicing under the name. This sweep is publish-grade, not counsel-grade.

## Framing-language findings (2026-07-03)

- **"Authority verification harness"**: no collision. Closest uses are unrelated (transaction-auth patents; an "agentic verification harness" in a game-generation paper).
- **"Authority envelope" / "delegation envelope"**: now established 2025-26 literature terms (arXiv:2604.25000 formalizes delegation envelopes; arXiv:2605.05440 uses "task-scoped authorization envelopes"; MIT's arXiv:2501.09674 underpins the delegation-chain framing). Do NOT claim coinage anywhere, including the thesis essay. README cites all of these in Related work.
- **"Attested" vs "qualified"**: "qualified opinion" is standard financial-audit vocabulary for exactly this meaning (assurance with stated reservations), which strengthens the framing for the P3/P4 compliance audience. No tool collision found.
- **Cedar/OPA positioning line** ("decide the point / verify the trajectory"): no one else uses it. Notably, arXiv:2606.26649 (policy-as-code autoformalization) lists trajectory-referencing policy checks as *future work*, and arXiv:2606.19242 (C-Trace) does runtime interception, not replayable post-hoc verdicts. Claim #3 ("nobody ships this artifact today") verified true as of 2026-07-03, but at least four papers in the last 14 months are circling it. The window is real and closing; publish sooner, not later.

## Standing language constraints (spec F8)

- Verdicts are findings and evidence, never attestations of compliance.
- Never write "certified compliant" anywhere, including marketing copy.
