import hashlib
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from ..db import db
from ..schemas import (
    HardwareDeviceIn,
    HardwareDeviceOut,
    HardwareDeviceProvisionOut,
    HardwareDeviceUpdate,
    HardwareTelemetryIn,
    HardwareTelemetryOut,
)
from ..utils import dependencies
from ..utils.roles import has_any_role, normalize_role
from ..utils.workspace import clean_doc, log_workspace_event, make_id, require_student_access

router = APIRouter(prefix="/hardware", tags=["hardware"])


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _build_device_token(device_id: str) -> str:
    return f"edv_dev_{device_id}_{secrets.token_urlsafe(24)}"


def _token_preview(token: str) -> str:
    if len(token) <= 12:
        return token
    return f"{token[:10]}...{token[-6:]}"


def _telemetry_sort():
    return [("captured_at", -1), ("updated_at", -1)]


async def _get_device_or_404(device_id: str) -> dict:
    device = await db.hardware_devices.find_one({"id": device_id})
    if not device:
        raise HTTPException(status_code=404, detail="Hardware device not found")
    return device


async def _enforce_device_access(device: dict, current_user) -> dict:
    role = normalize_role(current_user.role)
    if role == "admin":
        return device
    if role == "student":
        if device.get("student") != current_user.username:
            raise HTTPException(status_code=403, detail="Students can only access their own hardware devices")
        return device
    if has_any_role(current_user.role, ["academy_admin", "academyAdmin", "staff"]):
        if device.get("academy_id") != current_user.academy_id:
            raise HTTPException(status_code=403, detail="Cannot access hardware devices outside academy")
        return device
    raise HTTPException(status_code=403, detail="Insufficient privileges")


async def _resolve_target_student(student_username: str | None, current_user) -> tuple[str, dict]:
    role = normalize_role(current_user.role)
    if role == "student":
        target = current_user.username
    else:
        target = (student_username or "").strip()
        if not target:
            raise HTTPException(status_code=400, detail="A student must be assigned to the hardware device")
    student = await require_student_access(target, current_user)
    return target, student


def _device_out(doc: dict, device_token: str | None = None) -> dict:
    cleaned = clean_doc(doc) or {}
    cleaned.pop("token_hash", None)
    cleaned["token_preview"] = cleaned.get("token_preview") or (device_token and _token_preview(device_token))
    if device_token is not None:
        cleaned["device_token"] = device_token
    return cleaned


@router.get("/devices", response_model=list[HardwareDeviceOut])
async def list_devices(
    student: str | None = Query(default=None),
    current_user=Depends(dependencies.get_current_active_user),
):
    role = normalize_role(current_user.role)
    query: dict = {}
    if role == "admin":
        if student:
            query["student"] = student
    elif role == "student":
        query["student"] = current_user.username
    elif has_any_role(current_user.role, ["academy_admin", "academyAdmin", "staff"]):
        query["academy_id"] = current_user.academy_id
        if student:
            query["student"] = student
    else:
        raise HTTPException(status_code=403, detail="Insufficient privileges")

    cursor = db.hardware_devices.find(query).sort("updated_at", -1)
    return [_device_out(doc) async for doc in cursor]


@router.post("/devices", response_model=HardwareDeviceProvisionOut)
async def create_device(
    payload: HardwareDeviceIn,
    current_user=Depends(dependencies.get_current_active_user),
):
    target_student, student = await _resolve_target_student(payload.student, current_user)
    now = datetime.utcnow().timestamp()
    device_id = make_id("device")
    device_token = _build_device_token(device_id)
    doc = {
        "id": device_id,
        "name": payload.name.strip(),
        "student": target_student,
        "device_type": payload.device_type or "esp32-bme280",
        "transport": payload.transport or "wifi-http",
        "sampling_interval_ms": int(payload.sampling_interval_ms or 500),
        "firmware_version": payload.firmware_version,
        "notes": payload.notes,
        "active": True,
        "academy_id": student.get("academy_id"),
        "owner": current_user.username,
        "created_at": now,
        "updated_at": now,
        "last_seen_at": None,
        "last_telemetry_at": None,
        "latest_temperature_c": None,
        "latest_pressure_kpa": None,
        "latest_humidity_pct": None,
        "latest_battery_pct": None,
        "token_hash": _token_hash(device_token),
        "token_preview": _token_preview(device_token),
    }
    await db.hardware_devices.insert_one(doc)
    await log_workspace_event(
        current_user,
        action="hardware.device_created",
        entity_type="hardware_device",
        entity_id=device_id,
        summary=f"Registered hardware device {payload.name.strip()} for {target_student}.",
        target_user=target_student,
        academy_id=student.get("academy_id"),
        notify_users=[target_student],
        metadata={"device_type": doc["device_type"], "transport": doc["transport"]},
    )
    return _device_out(doc, device_token)


@router.patch("/devices/{device_id}", response_model=HardwareDeviceOut)
async def update_device(
    device_id: str,
    payload: HardwareDeviceUpdate,
    current_user=Depends(dependencies.get_current_active_user),
):
    device = await _get_device_or_404(device_id)
    await _enforce_device_access(device, current_user)

    updates = payload.model_dump(exclude_none=True)
    if "student" in updates:
        target_student, student = await _resolve_target_student(updates.get("student"), current_user)
        updates["student"] = target_student
        updates["academy_id"] = student.get("academy_id")
    updates["updated_at"] = datetime.utcnow().timestamp()

    await db.hardware_devices.update_one({"id": device_id}, {"$set": updates})
    updated = await _get_device_or_404(device_id)
    await log_workspace_event(
        current_user,
        action="hardware.device_updated",
        entity_type="hardware_device",
        entity_id=device_id,
        summary=f"Updated hardware device {updated.get('name')}.",
        target_user=updated.get("student"),
        academy_id=updated.get("academy_id"),
        notify_users=[updated.get("student")] if updated.get("student") else None,
    )
    return _device_out(updated)


@router.post("/devices/{device_id}/rotate-token", response_model=HardwareDeviceProvisionOut)
async def rotate_device_token(
    device_id: str,
    current_user=Depends(dependencies.get_current_active_user),
):
    device = await _get_device_or_404(device_id)
    await _enforce_device_access(device, current_user)

    next_token = _build_device_token(device_id)
    updates = {
        "token_hash": _token_hash(next_token),
        "token_preview": _token_preview(next_token),
        "updated_at": datetime.utcnow().timestamp(),
    }
    await db.hardware_devices.update_one({"id": device_id}, {"$set": updates})
    updated = await _get_device_or_404(device_id)
    await log_workspace_event(
        current_user,
        action="hardware.device_token_rotated",
        entity_type="hardware_device",
        entity_id=device_id,
        summary=f"Rotated hardware token for {updated.get('name')}.",
        target_user=updated.get("student"),
        academy_id=updated.get("academy_id"),
        notify_users=[updated.get("student")] if updated.get("student") else None,
    )
    return _device_out(updated, next_token)


@router.get("/devices/{device_id}/telemetry", response_model=list[HardwareTelemetryOut])
async def list_device_telemetry(
    device_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    current_user=Depends(dependencies.get_current_active_user),
):
    device = await _get_device_or_404(device_id)
    await _enforce_device_access(device, current_user)
    cursor = db.hardware_telemetry.find({"device_id": device_id}).sort(_telemetry_sort()).limit(limit)
    return [clean_doc(doc) async for doc in cursor]


@router.get("/telemetry/latest", response_model=HardwareTelemetryOut | None)
async def get_latest_telemetry(
    student: str | None = Query(default=None),
    device_id: str | None = Query(default=None),
    current_user=Depends(dependencies.get_current_active_user),
):
    if device_id:
        device = await _get_device_or_404(device_id)
        await _enforce_device_access(device, current_user)
        doc = await db.hardware_telemetry.find_one({"device_id": device_id}, sort=_telemetry_sort())
        return clean_doc(doc) if doc else None

    target_student = student or current_user.username
    await require_student_access(target_student, current_user)
    doc = await db.hardware_telemetry.find_one({"student": target_student}, sort=_telemetry_sort())
    return clean_doc(doc) if doc else None


@router.post("/telemetry", response_model=HardwareTelemetryOut)
async def create_hardware_telemetry(
    payload: HardwareTelemetryIn,
    current_user=Depends(dependencies.get_current_active_user),
):
    role = normalize_role(current_user.role)
    target_student = payload.student or current_user.username
    if role == "student" and target_student != current_user.username:
        raise HTTPException(status_code=403, detail="Students can only post telemetry for themselves")

    student = await require_student_access(target_student, current_user)
    now = datetime.utcnow().timestamp()
    captured_at = payload.captured_at or now
    doc = {
        "id": make_id("telemetry"),
        **payload.model_dump(),
        "student": target_student,
        "owner": current_user.username,
        "academy_id": student.get("academy_id"),
        "captured_at": captured_at,
        "updated_at": now,
    }
    await db.hardware_telemetry.insert_one(doc)
    return doc


@router.post("/ingest", response_model=HardwareTelemetryOut)
async def ingest_hardware_telemetry(
    payload: HardwareTelemetryIn,
    x_device_token: str | None = Header(default=None, alias="X-Device-Token"),
):
    token = (x_device_token or "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing device token")

    device = await db.hardware_devices.find_one({"token_hash": _token_hash(token), "active": True})
    if not device:
        raise HTTPException(status_code=401, detail="Invalid or inactive device token")
    if not device.get("student"):
        raise HTTPException(status_code=400, detail="Device is not assigned to a student")

    now = datetime.utcnow().timestamp()
    captured_at = payload.captured_at or now
    doc = {
        "id": make_id("telemetry"),
        **payload.model_dump(),
        "student": device.get("student"),
        "sport": payload.sport or None,
        "source": payload.source or "esp32",
        "device_id": device.get("id"),
        "owner": device.get("owner") or "hardware_device",
        "academy_id": device.get("academy_id"),
        "captured_at": captured_at,
        "updated_at": now,
    }
    await db.hardware_telemetry.insert_one(doc)
    await db.hardware_devices.update_one(
        {"id": device.get("id")},
        {
            "$set": {
                "updated_at": now,
                "last_seen_at": now,
                "last_telemetry_at": captured_at,
                "latest_temperature_c": payload.temperature_c,
                "latest_pressure_kpa": payload.pressure_kpa,
                "latest_humidity_pct": payload.humidity_pct,
                "latest_battery_pct": payload.battery_pct,
                "firmware_version": payload.metadata.get("firmware_version") if isinstance(payload.metadata, dict) and payload.metadata.get("firmware_version") else device.get("firmware_version"),
            }
        },
    )
    return doc
