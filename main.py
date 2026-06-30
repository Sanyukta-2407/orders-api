from collections import deque
from uuid import uuid4
import base64
import time

from fastapi import FastAPI, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI(title="Orders API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Retry-After"],
)

TOTAL_ORDERS = 46
RATE_LIMIT = 17
WINDOW = 10

catalog = [{"id": i, "item": f"Order {i}"} for i in range(1, TOTAL_ORDERS + 1)]

idempotency_store = {}
rate_store = {}


class OrderRequest(BaseModel):
    item: str = "New Order"


def check_rate_limit(client_id: str):
    now = time.time()

    q = rate_store.setdefault(client_id, deque())

    while q and now - q[0] >= WINDOW:
        q.popleft()

    if len(q) >= RATE_LIMIT:
        retry = max(1, int(q[0] + WINDOW - now + 0.999))
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
            headers={
                "Retry-After": str(retry)
            },
        )

    q.append(now)
    return None


@app.get("/")
def root():
    return {"message": "Orders API running"}


@app.post("/orders")
def create_order(
    body: OrderRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    x_client_id: str = Header(default="default", alias="X-Client-Id"),
):
    limited = check_rate_limit(x_client_id)
    if limited:
        return limited

    if idempotency_key and idempotency_key in idempotency_store:
        return JSONResponse(
            status_code=201,
            content=idempotency_store[idempotency_key],
        )

    order = {
        "id": str(uuid4()),
        "item": body.item,
    }

    if idempotency_key:
        idempotency_store[idempotency_key] = order

    return JSONResponse(
        status_code=201,
        content=order,
    )


@app.get("/orders")
def list_orders(
    limit: int = 10,
    cursor: str | None = None,
    x_client_id: str = Header(default="default", alias="X-Client-Id"),
):
    limited = check_rate_limit(x_client_id)
    if limited:
        return limited

    if limit < 1:
        limit = 1

    start = 0

    if cursor:
        try:
            start = int(base64.b64decode(cursor.encode()).decode())
        except Exception:
            start = 0

    end = min(start + limit, TOTAL_ORDERS)

    next_cursor = None
    if end < TOTAL_ORDERS:
        next_cursor = base64.b64encode(str(end).encode()).decode()

    return {
        "items": catalog[start:end],
        "next_cursor": next_cursor,
    }