from fastapi import FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from uuid import uuid4
import time
import base64

app = FastAPI(title="Orders API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TOTAL_ORDERS = 46
RATE_LIMIT = 17
WINDOW = 10

orders = [{"id": i, "item": f"Order {i}"} for i in range(1, TOTAL_ORDERS + 1)]

idempotency_store = {}
rate_store = {}


class OrderRequest(BaseModel):
    item: str = "New Order"


def check_rate_limit(client_id: str):
    now = time.time()

    timestamps = rate_store.get(client_id, [])
    timestamps = [t for t in timestamps if now - t < WINDOW]

    if len(timestamps) >= RATE_LIMIT:
        retry = max(1, int(WINDOW - (now - timestamps[0])))
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
            headers={"Retry-After": str(retry)},
        )

    timestamps.append(now)
    rate_store[client_id] = timestamps
    return None


@app.get("/")
def root():
    return {"message": "Orders API running"}


@app.post("/orders", status_code=201)
def create_order(
    req: OrderRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    x_client_id: str | None = Header(default="default", alias="X-Client-Id"),
):
    limited = check_rate_limit(x_client_id)
    if limited:
        return limited

    if idempotency_key and idempotency_key in idempotency_store:
        return idempotency_store[idempotency_key]

    order = {
        "id": str(uuid4()),
        "item": req.item,
    }

    if idempotency_key:
        idempotency_store[idempotency_key] = order

    return JSONResponse(status_code=201, content=order)


@app.get("/orders")
def list_orders(
    limit: int = 10,
    cursor: str | None = None,
    x_client_id: str | None = Header(default="default", alias="X-Client-Id"),
):
    limited = check_rate_limit(x_client_id)
    if limited:
        return limited

    start = 0

    if cursor:
        try:
            start = int(base64.b64decode(cursor).decode())
        except Exception:
            start = 0

    end = min(start + limit, TOTAL_ORDERS)

    items = orders[start:end]

    next_cursor = None
    if end < TOTAL_ORDERS:
        next_cursor = base64.b64encode(str(end).encode()).decode()

    return {
        "items": items,
        "next_cursor": next_cursor,
    }