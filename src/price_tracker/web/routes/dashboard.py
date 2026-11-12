"""Dashboard page."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from ..dependencies import ProductServiceDep
from ..templating import render_template

router = APIRouter(tags=["web"])


@router.get("/", response_class=HTMLResponse, name="dashboard")
def dashboard(request: Request, service: ProductServiceDep) -> Response:
    summary = service.dashboard_summary()
    return render_template(
        request,
        "dashboard.html",
        {
            "summary": summary,
            "page_title": "Dashboard",
        },
    )
