import os
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


SERVICE_NAME = os.getenv("SERVICE_NAME", "iot-ingestion")
SERVICE_VERSION = os.getenv("SERVICE_VERSION", "0.4.0")
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "local-dev-token")


app = FastAPI(
    title="FIT4110 Lab 04 - IoT Ingestion Service",
    version=SERVICE_VERSION,
    description="Dockerized IoT Ingestion API aligned with Lab 03 contract.",
)


class SensorMetric(str, Enum):
    temperature = "temperature"
    humidity = "humidity"
    motion = "motion"
    smoke = "smoke"


class SensorUnit(str, Enum):
    celsius = "celsius"
    percent = "percent"
    boolean = "boolean"
    ppm = "ppm"


class ProblemDetails(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str
    instance: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class SensorReadingCreate(BaseModel):
    device_id: str = Field(..., min_length=3)
    metric: SensorMetric
    value: float = Field(..., ge=-40, le=80)
    unit: Optional[SensorUnit] = None
    timestamp: str


class SensorReadingCreated(BaseModel):
    reading_id: str
    device_id: str
    metric: SensorMetric
    accepted: bool
    created_at: str


READINGS: List[Dict] = []


def build_problem(
    *,
    status_code: int,
    title: str,
    detail: str,
    instance: Optional[str] = None,
    problem_type: str = "about:blank",
):
    data = {
        "type": problem_type,
        "title": title,
        "status": status_code,
        "detail": detail,
    }

    if instance:
        data["instance"] = instance

    return data


# FIXED HTTPException handler
@app.exception_handler(HTTPException)
async def http_exception_handler(
    request: Request,
    exc: HTTPException
):

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "type": "about:blank",
            "title": "Unauthorized"
            if exc.status_code == 401
            else "HTTP Error",
            "status": exc.status_code,
            "detail": str(exc.detail),
            "instance": str(request.url.path)
        },
        media_type="application/problem+json"
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError
):
    return JSONResponse(
        status_code=422,
        content=build_problem(
            status_code=422,
            title="Validation error",
            detail="Invalid request payload",
            instance=str(request.url.path),
        ),
        media_type="application/problem+json",
    )


def verify_bearer_token(
    authorization: Optional[str] = Header(default=None)
):

    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header"
        )

    expected = f"Bearer {AUTH_TOKEN}"

    if authorization != expected:
        raise HTTPException(
            status_code=401,
            detail="Invalid bearer token"
        )


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def next_reading_id():
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"R-{today}-{len(READINGS)+1:04d}"


@app.get("/health")
def health():

    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
    }


@app.post(
    "/readings",
    status_code=201,
    dependencies=[Depends(verify_bearer_token)]
)
def create_reading(
    payload: SensorReadingCreate,
    response: Response
):

    if payload.metric == SensorMetric.temperature and payload.value >= 70:
        response.headers["X-Warning"] = "high-temperature"


    reading_id = next_reading_id()

    item = {
        "reading_id": reading_id,
        "device_id": payload.device_id,
        "metric": payload.metric.value,
        "value": payload.value,
        "unit": payload.unit.value if payload.unit else None,
        "timestamp": payload.timestamp,
        "created_at": now_iso(),
    }

    READINGS.append(item)

    return {
        "reading_id": reading_id,
        "device_id": payload.device_id,
        "metric": payload.metric,
        "accepted": True,
        "created_at": item["created_at"],
    }


@app.get(
    "/readings/latest",
    dependencies=[Depends(verify_bearer_token)]
)
def latest_readings(
    device_id: Optional[str] = None,
    limit: int = 10
):

    items = READINGS

    if device_id:
        items = [
            x for x in items
            if x["device_id"] == device_id
        ]

    return {
        "items": items[-limit:]
    }


@app.get(
    "/readings/{reading_id}",
    dependencies=[Depends(verify_bearer_token)]
)
def get_reading(reading_id: str):

    for item in READINGS:
        if item["reading_id"] == reading_id:
            return item


    raise HTTPException(
        status_code=404,
        detail=build_problem(
            status_code=404,
            title="Not Found",
            detail="Reading does not exist",
        )
    )