# EditorIA

AI-assisted editing for short vertical videos (Reels, TikTok, Shorts): a **deterministic CLI that edits, verifies and delivers**, plus a Claude Code agent layer that operates it as creative director and editor.

[Versión completa en español](README.md)

> **Status: v0.1, in development.** Documentation, prompts and UI messages are written in Spanish; code, schema keys and internal names are in English.

## What it does

You bring a vertical video you recorded and already trimmed in your editor. EditorIA:

1. Analyses it: metadata, local word-level transcription (faster-whisper), silences, cuts and face zone.
2. Proposes **three creative treatments (A, B, C)** of the same passage, with a short sample of each and a recommendation.
3. Builds a full **V1**: captions, template-based motion graphics, sound effects and loudness-normalised mix.
4. Runs automatic **quality control** and delivers a package (video, SRT/VTT, plan, edit map, attributions).
5. **Stops** and waits for your time-coded feedback before creating V2, never overwriting a delivered version.

The core idea: *the model decides; the code executes and verifies.* Rules such as "do not touch background, identity or voice", "do not invent metrics", "do not spend credits without an authorised limit" and "wait for feedback after V1" are enforced by a plan linter, QC checks, the CLI and Claude Code hooks (see [docs/politicas.md](docs/politicas.md), in Spanish).

## Install

Requirements: Git, [uv](https://docs.astral.sh/uv/) and **FFmpeg 6+** (with libass) on the `PATH`; about 10 GB of free disk space.

```bash
git clone <repository-url> editoria && cd editoria
uv sync --all-extras
uv run playwright install chromium        # graphics engine
uv run python scripts/fetch_assets.py     # Noto emoji + Inter font (sha256-verified, not versioned)
uv run editoria doctor
```

Windows notes: [docs/guia-windows.md](docs/guia-windows.md).

## Quick start

```bash
uv run editoria init "my video.mp4" --slug my-video
uv run editoria transcribe my-video
uv run editoria analyze my-video
uv run editoria propose my-video
uv run editoria run my-video
```

Output goes to `proyectos/my-video/` (git-ignored). The repository ships no media; to try the flow without your own footage, run `uv run python scripts/make_fixtures.py` to generate synthetic clips.

## Using it

- **With Claude Code:** open it in the repository folder and use the `editar-video` skill (and `aplicar-feedback` for revisions). See [`.claude/`](.claude/).
- **CLI only:** every command works on its own; edit `plan.yaml` by hand if you prefer.
- **Chat without tools:** [prompts/prompt-maestro.md](prompts/prompt-maestro.md) is a generic prompt template ([guide](docs/uso-con-chat.md)); it plans but cannot render video.

## Honest limitations

- Template quality does not compete with a human editor: v0.1 ships 8 graphics templates and 3 styles.
- Identity, background and lip-sync are **not** verified automatically; QC flags them for human review.
- Generated shots (Higgsfield) are optional, manual-assisted and unverified end to end; an experimental API client is off by default and requires a budget.
- No CapCut project export, no publishing, no bundled music, no GUI.

## Licences

Code: Apache-2.0. Prompts, docs, templates and styles: CC BY 4.0. Generated sound effects: CC0. Third-party assets and dependencies are listed in [THIRD_PARTY.md](THIRD_PARTY.md); FFmpeg is invoked as an external binary and is not distributed.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md), the [Code of Conduct](CODE_OF_CONDUCT.md) and [SECURITY.md](SECURITY.md).
