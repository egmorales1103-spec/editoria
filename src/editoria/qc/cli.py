"""qc (owner: A5)."""

from __future__ import annotations

import typer

from editoria.util.cli import command_log, fail, open_project


def register(app: typer.Typer) -> None:
    @app.command("qc")
    def qc_cmd(
        slug: str = typer.Argument(...),
        version: str = typer.Option("V1", "--version"),
    ) -> None:
        """Control de calidad automático (PASS/WARN/FAIL/REVISIÓN HUMANA)."""
        from editoria.policy.immutable import delivered_message
        from editoria.qc.control import DefaultQualityControl
        from editoria.schemas import QC_STATUS_LABEL
        from editoria.util.ffmpeg import FFmpegError, FFmpegNotFound
        from editoria.util.log import info, ok, warn

        ctx = open_project(slug)
        try:
            delivered = ctx.is_delivered(version)
        except ValueError as exc:
            fail(str(exc))
        if delivered:
            fail(delivered_message(version))
        with command_log(ctx.commands_log):
            try:
                report = DefaultQualityControl().run(ctx, version)
            except (
                ValueError,
                FileNotFoundError,
                PermissionError,
                FFmpegNotFound,
                FFmpegError,
            ) as exc:
                fail(str(exc))
        colors = {"PASS": "green", "WARN": "yellow", "FAIL": "red", "HUMAN": "cyan"}
        for c in report.checks:
            label = QC_STATUS_LABEL[c.status]
            info(f"[{colors[c.status]}]{label:<16}[/{colors[c.status]}] {c.id}: {c.detail}")
        qc_dir = ctx.version_dir(version) / "qc"
        if report.has_fail:
            warn(report.summary)
            fail(f"QC con fallas. Detalle en {qc_dir / 'qc.md'}")
        ok(f"{report.summary} Detalle en {qc_dir / 'qc.md'}")
