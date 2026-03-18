from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from ..utils import auth, dependencies
from ..utils.roles import has_any_role, normalize_role
from ..utils.default_rules import build_default_rule_entry, build_default_rules, normalize_sport
from ..db import db

router = APIRouter(prefix="/rules", tags=["rules"])


def _entry_to_response(username: str, sport_name: str, entry: dict):
    return {
        "student": username,
        "sport": sport_name,
        "rules": entry.get("rules", {}),
        "source": entry.get("source", "default"),
        "created_at": entry.get("created_at"),
        "updated_at": entry.get("updated_at"),
    }


async def ensure_rules_doc(student, sport: str):
    username = student.username
    sport_name = normalize_sport(sport)
    sport_rules = getattr(student, "sport_rules", None) or {}
    if sport_name in sport_rules:
        entry = sport_rules[sport_name] or {}
        source = entry.get("source", "default") if isinstance(entry, dict) else "default"
        existing_rules = entry.get("rules") if isinstance(entry, dict) else {}
        existing_rules = existing_rules if isinstance(existing_rules, dict) else {}

        # If entry is still default-generated, rebuild it so updated defaults are picked up.
        if source != "override":
            rebuilt = build_default_rule_entry(sport_name, getattr(student, "angle_measurements", None))
            now_ts = datetime.utcnow().timestamp()
            rebuilt_entry = {
                "rules": rebuilt.get("rules", {}),
                "source": "default",
                "created_at": entry.get("created_at", now_ts),
                "updated_at": now_ts,
            }
            if rebuilt_entry.get("rules", {}) != existing_rules:
                await db.users.update_one(
                    {"username": username},
                    {"$set": {f"sport_rules.{sport_name}": rebuilt_entry}},
                )
                return _entry_to_response(username, sport_name, rebuilt_entry)
            return _entry_to_response(username, sport_name, entry)

        # Build a complete rule set from defaults + student baseline, then overlay existing values.
        default_rules = build_default_rules(sport_name, getattr(student, "angle_measurements", None))
        default_targets = default_rules.get("targets", {}) if isinstance(default_rules, dict) else {}
        default_tolerances = default_rules.get("tolerances", {}) if isinstance(default_rules, dict) else {}

        if "targets" in existing_rules and isinstance(existing_rules.get("targets"), dict):
            existing_targets = existing_rules.get("targets") or {}
        else:
            # Backward compatibility: older shape may store targets directly at root.
            existing_targets = {
                k: v for k, v in existing_rules.items() if k not in ("tolerances", "targets")
            }
        existing_tolerances = existing_rules.get("tolerances") if isinstance(existing_rules.get("tolerances"), dict) else {}

        merged_rules = {
            "targets": {**default_targets, **existing_targets},
            "tolerances": {**default_tolerances, **existing_tolerances},
        }

        if merged_rules != existing_rules:
            now_ts = datetime.utcnow().timestamp()
            merged_entry = {
                "rules": merged_rules,
                "source": entry.get("source", "default"),
                "created_at": entry.get("created_at", now_ts),
                "updated_at": now_ts,
            }
            await db.users.update_one(
                {"username": username},
                {"$set": {f"sport_rules.{sport_name}": merged_entry}},
            )
            return _entry_to_response(username, sport_name, merged_entry)

        return _entry_to_response(username, sport_name, entry)

    entry = build_default_rule_entry(sport_name, getattr(student, "angle_measurements", None))
    await db.users.update_one(
        {"username": username},
        {"$set": {f"sport_rules.{sport_name}": entry}},
    )
    return _entry_to_response(username, sport_name, entry)


@router.post("/override")
async def override_rules(username: str, sport: str, rules: dict, current_user=Depends(dependencies.get_current_active_user)):
    # staff or academy admin for student's academy
    if not has_any_role(current_user.role, ["admin", "academy_admin", "academyAdmin", "staff"]):
        raise HTTPException(status_code=403, detail="Insufficient privileges")
    student = await auth.get_user(username)
    if not student or normalize_role(student.role) != "student":
        raise HTTPException(status_code=404, detail="Student not found")
    if has_any_role(current_user.role, ["academy_admin", "academyAdmin", "staff"]) and current_user.academy_id != student.academy_id:
        raise HTTPException(status_code=403, detail="Cannot modify rules outside academy")
    sport_name = normalize_sport(sport)
    now_ts = datetime.utcnow().timestamp()
    existing_entry = ((getattr(student, "sport_rules", None) or {}).get(sport_name) or {})
    entry = {
        "rules": rules,
        "source": "override",
        "created_at": existing_entry.get("created_at", now_ts),
        "updated_at": now_ts,
    }
    await db.users.update_one(
        {"username": username},
        {"$set": {f"sport_rules.{sport_name}": entry}},
    )
    return _entry_to_response(username, sport_name, entry)

@router.get("/{username}/{sport}")
async def get_rules(username: str, sport: str, current_user=Depends(dependencies.get_current_active_user)):
    student = await auth.get_user(username)
    if not student or normalize_role(student.role) != "student":
        raise HTTPException(status_code=404, detail="Student not found")
    if has_any_role(current_user.role, ["academy_admin", "academyAdmin", "staff"]) and current_user.academy_id != student.academy_id:
        raise HTTPException(status_code=403, detail="Cannot load rules outside academy")
    if normalize_role(current_user.role) == "student" and current_user.username != username:
        raise HTTPException(status_code=403, detail="Students can only view their own rules")

    rule_doc = await ensure_rules_doc(student, sport)
    if not rule_doc:
        raise HTTPException(status_code=404, detail="Student not found")
    return rule_doc["rules"]
