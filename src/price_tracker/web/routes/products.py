"""Product list, creation, detail, and action routes."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from ...database.session import SessionFactory
from ...models.product import Product
from ...services.price_checker import PriceCheckStatus
from ...services.product_service import (
    DuplicateProductError,
    ProductNotFoundError,
    ProductService,
    ProductValidationError,
)
from ..charts import build_chart_data
from ..csrf import submitted_csrf_token, validate_csrf
from ..dependencies import (
    PriceCheckerDep,
    ProductScrapeServiceDep,
    ProductServiceDep,
)
from ..htmx import is_htmx_request
from ..price_summary import build_price_summary
from ..templating import render_template

router = APIRouter(prefix="/products", tags=["products"])

_FORM_VALUES = {"url": "", "target_price": ""}


def _list_context(
    products: list[Product],
    *,
    created: int | None = None,
    deleted: bool = False,
    scrape: str | None = None,
    form_errors: dict[str, str] | None = None,
    form_values: dict[str, str] | None = None,
) -> dict[str, object]:
    return {
        "products": products,
        "page_title": "Products",
        "created": created,
        "deleted": deleted,
        "scrape": scrape,
        "form_errors": form_errors or {},
        "form_values": form_values or dict(_FORM_VALUES),
    }


def _load_products(
    session_factory: SessionFactory,
    recent_decrease_days: int,
) -> list[Product]:
    with session_factory() as session:
        service = ProductService(
            session,
            recent_decrease_days=recent_decrease_days,
        )
        return service.list_products()


async def _render_form_error(
    request: Request,
    errors: dict[str, str],
    values: dict[str, str],
) -> Response:
    if is_htmx_request(request):
        return render_template(
            request,
            "products/_add_product_form.html",
            {
                "form_errors": errors,
                "form_values": values,
            },
            status_code=422,
        )

    products = await asyncio.to_thread(
        _load_products,
        request.app.state.session_factory,
        request.app.state.settings.recent_decrease_days,
    )
    return render_template(
        request,
        "products/list.html",
        _list_context(
            products,
            form_errors=errors,
            form_values=values,
        ),
        status_code=422,
    )


def _safe_next_path(next_path: str, product_id: int) -> str:
    allowed = {"/", "/products", f"/products/{product_id}"}
    return next_path if next_path in allowed else "/products"


@router.get("", response_class=HTMLResponse, name="products_list")
def list_products(
    request: Request,
    service: ProductServiceDep,
    created: Annotated[int | None, Query()] = None,
    deleted: Annotated[bool, Query()] = False,
    scrape: Annotated[str | None, Query()] = None,
) -> Response:
    return render_template(
        request,
        "products/list.html",
        _list_context(
            service.list_products(),
            created=created,
            deleted=deleted,
            scrape=scrape,
        ),
    )


@router.post("", response_class=HTMLResponse, name="products_create")
async def create_product(
    request: Request,
    scrape_service: ProductScrapeServiceDep,
    url: Annotated[str, Form()] = "",
    target_price: Annotated[str, Form()] = "",
    csrf_token: Annotated[str | None, Form()] = None,
) -> Response:
    validate_csrf(request, submitted_csrf_token(request, csrf_token))

    values = {"url": url, "target_price": target_price}
    try:
        result = await scrape_service.add_product(url, target_price or None)
    except ProductValidationError as exc:
        return await _render_form_error(request, exc.errors, values)
    except DuplicateProductError as exc:
        message = "This product is already tracked."
        if exc.existing_product_id is not None:
            message = f"This product is already tracked (product #{exc.existing_product_id})."
        return await _render_form_error(
            request,
            {"url": message},
            values,
        )

    scrape_status = "ok" if result.scraped else "failed"
    target = f"/products?created={result.product.id}&scrape={scrape_status}"
    if is_htmx_request(request):
        return Response(status_code=204, headers={"HX-Redirect": target})
    return RedirectResponse(url=target, status_code=303)


@router.get("/{product_id}", response_class=HTMLResponse, name="product_detail")
def product_detail(
    request: Request,
    product_id: int,
    service: ProductServiceDep,
    check: Annotated[str | None, Query()] = None,
) -> Response:
    product = service.get_product_or_raise(product_id)
    history = service.get_price_history(product_id)
    chart = build_chart_data(history)
    summary = build_price_summary(product, history)
    return render_template(
        request,
        "products/detail.html",
        {
            "product": product,
            "history": history,
            "chart": chart,
            "summary": summary,
            "check": check,
            "page_title": product.name or "Product details",
        },
    )


@router.post(
    "/{product_id}/check",
    response_class=HTMLResponse,
    name="product_check",
)
async def check_product(
    request: Request,
    product_id: int,
    checker: PriceCheckerDep,
    csrf_token: Annotated[str | None, Form()] = None,
) -> Response:
    validate_csrf(request, submitted_csrf_token(request, csrf_token))
    result = await checker.check_product(product_id)

    if result.status is PriceCheckStatus.NOT_FOUND:
        raise ProductNotFoundError(product_id)

    if result.status is PriceCheckStatus.BUSY:
        if is_htmx_request(request):
            return render_template(
                request,
                "partials/check_busy.html",
                {},
                status_code=409,
            )
        return RedirectResponse(
            url=f"/products/{product_id}?check=busy",
            status_code=303,
        )

    check_value = "ok" if result.status is PriceCheckStatus.SUCCESS else "failed"
    target = f"/products/{product_id}?check={check_value}"
    if is_htmx_request(request):
        return Response(status_code=204, headers={"HX-Redirect": target})
    return RedirectResponse(url=target, status_code=303)


@router.post(
    "/{product_id}/toggle",
    response_class=HTMLResponse,
    name="product_toggle",
)
def toggle_product(
    request: Request,
    product_id: int,
    service: ProductServiceDep,
    csrf_token: Annotated[str | None, Form()] = None,
    next_path: Annotated[str, Form(alias="next")] = "/products",
) -> Response:
    validate_csrf(request, submitted_csrf_token(request, csrf_token))
    product = service.toggle_active(product_id)

    if is_htmx_request(request) and next_path == "/products":
        return render_template(
            request,
            "products/_row.html",
            {"product": product},
        )

    return RedirectResponse(
        url=_safe_next_path(next_path, product_id),
        status_code=303,
    )


@router.post(
    "/{product_id}/delete",
    response_class=HTMLResponse,
    name="product_delete",
)
def delete_product(
    request: Request,
    product_id: int,
    service: ProductServiceDep,
    csrf_token: Annotated[str | None, Form()] = None,
) -> Response:
    validate_csrf(request, submitted_csrf_token(request, csrf_token))
    service.delete_product(product_id)

    if is_htmx_request(request):
        return Response(status_code=200)
    return RedirectResponse(url="/products?deleted=1", status_code=303)
