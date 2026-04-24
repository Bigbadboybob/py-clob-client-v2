import asyncio
import logging
import traceback

import httpx

from py_clob_client_v2.clob_types import (
    BalanceAllowanceParams,
    DropNotificationParams,
    OpenOrderParams,
    OrderScoringParams,
    OrdersScoringParams,
    TradeParams,
)
from ..exceptions import PolyApiException

logger = logging.getLogger(__name__)

GET = "GET"
POST = "POST"
DELETE = "DELETE"
PUT = "PUT"


def _overload_headers(method: str, headers: dict) -> dict:
    if headers is None:
        headers = {}
    headers["User-Agent"] = "py_clob_client_v2"
    headers["Accept"] = "*/*"
    headers["Connection"] = "keep-alive"
    headers["Content-Type"] = "application/json"
    if method == GET:
        headers["Accept-Encoding"] = "gzip"
    return headers


def _is_transient_error(exc: Exception, status_code: int = None) -> bool:
    """
    Returns True if the error is likely transient and worth retrying once.
    Matches: 5xx responses, network-level errors (connect, timeout, network).
    """
    if status_code is not None and 500 <= status_code < 600:
        return True
    if isinstance(exc, PolyApiException) and exc.status_code is None:
        return True
    return isinstance(
        exc,
        (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError),
    )


class ClientHelper:
    """
    Helper class that wraps an injected httpx.AsyncClient and issues async
    HTTP requests.  Every coroutine method returns either parsed JSON (when
    the server sends JSON content) or the raw text body.
    """

    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def request(
        self,
        endpoint: str,
        method: str,
        headers=None,
        data=None,
        params=None,
    ):
        headers = _overload_headers(method, headers)
        try:
            if isinstance(data, str):
                # Pre-serialized body: send exact bytes
                resp = await self.client.request(
                    method=method,
                    url=endpoint,
                    headers=headers,
                    content=data.encode("utf-8"),
                    params=params,
                )
            else:
                resp = await self.client.request(
                    method=method,
                    url=endpoint,
                    headers=headers,
                    json=data,
                    params=params,
                )

            if resp.status_code != 200:
                # resp.text is the server response body (no credentials are logged here)
                logger.error(
                    "[py_clob_client_v2] request error status=%s url=%s body=%s",
                    resp.status_code,
                    endpoint,
                    resp.text,
                )
                raise PolyApiException(resp)

            # Check content type header to see if it's JSON
            content_type = resp.headers.get("content-type", "")

            if not resp.content or len(resp.content.strip()) == 0:
                return {}
            if "application/json" in content_type:
                return resp.json()
            # Some endpoints still return JSON without the header; try anyway
            try:
                return resp.json()
            except ValueError:
                return resp.text

        except PolyApiException:
            raise
        except httpx.RequestError as exc:
            logger.error("[py_clob_client_v2] request error: %s", exc)
            traceback.print_exc()
            raise PolyApiException(
                error_msg=f"{exc.__class__.__name__}: {repr(exc)}"
            ) from exc

    async def get(self, endpoint, headers=None, data=None, params=None):
        return await self.request(endpoint, GET, headers, data, params)

    async def post(self, endpoint, headers=None, data=None, params=None):
        return await self.request(endpoint, POST, headers, data, params)

    async def delete(self, endpoint, headers=None, data=None, params=None):
        return await self.request(endpoint, DELETE, headers, data, params)

    async def put(self, endpoint, headers=None, data=None, params=None):
        return await self.request(endpoint, PUT, headers, data, params)


_client_helper: "ClientHelper | None" = None


def get_client() -> ClientHelper:
    """
    Returns the process-wide ClientHelper.  Lazily instantiated with a default
    httpx.AsyncClient() when no client has been injected.
    """
    global _client_helper
    if _client_helper is None:
        _client_helper = ClientHelper(httpx.AsyncClient(http2=True))
    return _client_helper


def set_client(client_helper: ClientHelper) -> None:
    """Inject a ClientHelper to be used by module-level helpers / ClobClient."""
    global _client_helper
    _client_helper = client_helper


# ---------------------------------------------------------------------------
# Module-level async helpers (backward-compat surface).  These delegate to the
# shared ClientHelper so that a single AsyncClient (with its connection pool)
# is reused across the whole process.
# ---------------------------------------------------------------------------

async def request(endpoint, method, headers=None, data=None, params=None):
    return await get_client().request(
        endpoint, method, headers=headers, data=data, params=params
    )


async def get(endpoint, headers=None, data=None, params=None):
    return await get_client().get(endpoint, headers=headers, data=data, params=params)


async def post(
    endpoint,
    headers=None,
    data=None,
    params=None,
    retry_on_error: bool = False,
):
    try:
        return await get_client().post(
            endpoint, headers=headers, data=data, params=params
        )
    except Exception as exc:
        status = getattr(exc, "status_code", None)
        if retry_on_error and _is_transient_error(exc, status):
            logger.info("[py_clob_client_v2] transient error, retrying once after 30 ms")
            await asyncio.sleep(0.03)
            return await get_client().post(
                endpoint, headers=headers, data=data, params=params
            )
        raise


async def delete(endpoint, headers=None, data=None, params=None):
    return await get_client().delete(
        endpoint, headers=headers, data=data, params=params
    )


async def put(endpoint, headers=None, data=None, params=None):
    return await get_client().put(
        endpoint, headers=headers, data=data, params=params
    )


def build_query_params(url: str, param: str, val) -> str:
    last = url[-1]
    if last == "?":
        return "{}{}={}".format(url, param, val)
    return "{}&{}={}".format(url, param, val)


def add_query_trade_params(
    base_url: str, params: TradeParams = None, next_cursor: str = "MA=="
) -> str:
    url = base_url
    has_query = bool(next_cursor) or (
        bool(params)
        and any(
            [
                params.market,
                params.asset_id,
                params.after,
                params.before,
                params.maker_address,
                params.id,
            ]
        )
    )
    if has_query:
        url = url + "?"
    if params:
        if params.market:
            url = build_query_params(url, "market", params.market)
        if params.asset_id:
            url = build_query_params(url, "asset_id", params.asset_id)
        if params.after:
            url = build_query_params(url, "after", params.after)
        if params.before:
            url = build_query_params(url, "before", params.before)
        if params.maker_address:
            url = build_query_params(url, "maker_address", params.maker_address)
        if params.id:
            url = build_query_params(url, "id", params.id)
    if next_cursor:
        url = build_query_params(url, "next_cursor", next_cursor)
    return url


def add_query_open_orders_params(
    base_url: str, params: OpenOrderParams = None, next_cursor: str = "MA=="
) -> str:
    url = base_url
    has_query = bool(next_cursor) or (
        bool(params) and any([params.market, params.asset_id, params.id])
    )
    if has_query:
        url = url + "?"
    if params:
        if params.market:
            url = build_query_params(url, "market", params.market)
        if params.asset_id:
            url = build_query_params(url, "asset_id", params.asset_id)
        if params.id:
            url = build_query_params(url, "id", params.id)
    if next_cursor:
        url = build_query_params(url, "next_cursor", next_cursor)
    return url


def drop_notifications_query_params(
    base_url: str, params: DropNotificationParams = None
) -> str:
    url = base_url
    if params and params.ids:
        url = url + "?"
        url = build_query_params(url, "ids", ",".join(params.ids))
    return url


def add_balance_allowance_params_to_url(
    base_url: str, params: BalanceAllowanceParams = None
) -> str:
    url = base_url
    if params:
        url = url + "?"
        if params.asset_type:
            url = build_query_params(url, "asset_type", str(params.asset_type))
        if params.token_id:
            url = build_query_params(url, "token_id", params.token_id)
        if params.signature_type is not None:
            url = build_query_params(url, "signature_type", params.signature_type)
    return url


def add_order_scoring_params_to_url(
    base_url: str, params: OrderScoringParams = None
) -> str:
    url = base_url
    if params and params.orderId:
        url = url + "?"
        url = build_query_params(url, "order_id", params.orderId)
    return url


def add_orders_scoring_params_to_url(
    base_url: str, params: OrdersScoringParams = None
) -> str:
    url = base_url
    if params and params.orderIds:
        url = url + "?"
        url = build_query_params(url, "order_ids", ",".join(params.orderIds))
    return url


def parse_orders_scoring_params(params: OrdersScoringParams = None) -> dict:
    """Returns a query-params dict for the orders-scoring endpoint."""
    result = {}
    if params and params.orderIds:
        result["order_ids"] = ",".join(params.orderIds)
    return result


def parse_drop_notification_params(params: DropNotificationParams = None) -> dict:
    """Returns a query-params dict for the drop-notifications endpoint."""
    result = {}
    if params and params.ids:
        result["ids"] = ",".join(params.ids)
    return result
