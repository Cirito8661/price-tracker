"""Editable scheduler and email settings page."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import ValidationError

from ...runtime_settings import RuntimeSettings
from ..csrf import submitted_csrf_token, validate_csrf
from ..templating import render_template

router = APIRouter(tags=["web"])


def _form_values(settings) -> dict[str, object]:
    return {
        "check_interval_seconds": str(settings.check_interval_seconds),
        "email_enabled": settings.email_enabled,
        "smtp_host": settings.smtp_host or "",
        "smtp_port": str(settings.smtp_port),
        "smtp_username": settings.smtp_username or "",
        "smtp_from": settings.smtp_from or "",
        "smtp_to": settings.smtp_to or "",
        "smtp_security": settings.smtp_security,
        "smtp_timeout_seconds": str(settings.smtp_timeout_seconds),
    }


def _settings_context(
    request: Request,
    *,
    form_values: dict[str, object] | None = None,
    form_errors: dict[str, str] | None = None,
    saved: bool = False,
) -> dict[str, object]:
    store = request.app.state.runtime_settings
    effective = store.effective_settings
    scheduler = request.app.state.monitoring_scheduler
    return {
        "page_title": "Settings",
        "settings": effective,
        "email_effective": effective.effective_email_enabled,
        "email_configured": effective.email_configured,
        "email_enabled": effective.email_enabled,
        "email_warning": effective.email_configuration_warning,
        "runtime_password_configured": store.password_configured,
        "scheduler_running": scheduler.running,
        "scheduler_next_run": scheduler.next_run_time,
        "scheduler_interval_seconds": scheduler.interval_seconds,
        "form_values": (form_values if form_values is not None else _form_values(effective)),
        "form_errors": form_errors or {},
        "saved": saved,
    }


@router.get("/settings", response_class=HTMLResponse, name="settings")
def settings_page(
    request: Request,
    saved: Annotated[str | None, Query()] = None,
) -> Response:
    return render_template(
        request,
        "settings.html",
        _settings_context(request, saved=saved is not None),
    )


@router.post("/settings", response_class=HTMLResponse, name="settings_update")
def update_settings(
    request: Request,
    check_interval_seconds: Annotated[str, Form()] = "3600",
    email_enabled: Annotated[str | None, Form()] = None,
    smtp_host: Annotated[str, Form()] = "",
    smtp_port: Annotated[str, Form()] = "587",
    smtp_username: Annotated[str, Form()] = "",
    smtp_password: Annotated[str, Form()] = "",
    smtp_from: Annotated[str, Form()] = "",
    smtp_to: Annotated[str, Form()] = "",
    smtp_security: Annotated[str, Form()] = "starttls",
    smtp_timeout_seconds: Annotated[str, Form()] = "15",
    csrf_token: Annotated[str | None, Form()] = None,
) -> Response:
    validate_csrf(request, submitted_csrf_token(request, csrf_token))

    store = request.app.state.runtime_settings
    current = store.runtime
    values: dict[str, object] = {
        "check_interval_seconds": check_interval_seconds,
        "email_enabled": email_enabled is not None,
        "smtp_host": smtp_host,
        "smtp_port": smtp_port,
        "smtp_username": smtp_username,
        "smtp_from": smtp_from,
        "smtp_to": smtp_to,
        "smtp_security": smtp_security,
        "smtp_timeout_seconds": smtp_timeout_seconds,
    }

    try:
        runtime = RuntimeSettings(
            check_interval_seconds=check_interval_seconds,
            email_enabled=email_enabled is not None,
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            smtp_username=smtp_username,
            smtp_password=smtp_password.strip() or current.smtp_password,
            smtp_from=smtp_from,
            smtp_to=smtp_to,
            smtp_security=smtp_security,
            smtp_timeout_seconds=smtp_timeout_seconds,
        )
    except ValidationError as exc:
        errors: dict[str, str] = {}
        for error in exc.errors():
            location = error.get("loc") or ("_form",)
            errors[str(location[0])] = str(error.get("msg", "Invalid value"))
        return render_template(
            request,
            "settings.html",
            _settings_context(
                request,
                form_values=values,
                form_errors=errors,
            ),
            status_code=422,
        )

    try:
        store.save(runtime)
    except OSError:
        return render_template(
            request,
            "settings.html",
            _settings_context(
                request,
                form_values=values,
                form_errors={"_form": "Could not save settings to disk."},
            ),
            status_code=500,
        )

    request.app.state.monitoring_scheduler.reschedule(runtime.check_interval_seconds)
    return RedirectResponse(url="/settings?saved=1", status_code=303)
