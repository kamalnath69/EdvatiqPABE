from copy import deepcopy
from datetime import datetime

SPORTS = ["Archery", "Cricket Bowling", "Squat", "Tennis Serve"]

DEFAULT_TARGETS = {
    "Archery": {
        # Right-handed reference: bow arm (left) near straight, draw arm (right) bent.
        "Left elbow": 170.0,
        "Right elbow": 120.0,
        # These metrics are modeled as "deviation from level/vertical", lower is better.
        "Shoulders": 8.0,
        "Spine": 10.0,
        "Hip level": 8.0,
        "Stance width": 0.9,
        "Left knee posture": 170.0,
        "Right knee posture": 170.0,
        # Head alignment is measured relative to shoulder width (%), not frame position.
        "Head alignment": 30.0,
        "Neck tilt": 12.0,
    },
    "Cricket Bowling": {
        "Left elbow": 165.0,
        "Right elbow": 150.0,
        "Shoulders": 72.0,
        "Spine": 18.0,
        "Hip level": 14.0,
        "Stance width": 0.58,
        "Left knee posture": 160.0,
        "Right knee posture": 165.0,
        "Head alignment": 15.0,
        "Neck tilt": 50.0,
    },
    "Squat": {
        "Left elbow": 175.0,
        "Right elbow": 175.0,
        "Shoulders": 70.0,
        "Spine": 8.0,
        "Hip level": 10.0,
        "Stance width": 0.6,
        "Left knee posture": 100.0,
        "Right knee posture": 100.0,
        "Head alignment": 10.0,
        "Neck tilt": 45.0,
    },
    "Tennis Serve": {
        "Left elbow": 160.0,
        "Right elbow": 165.0,
        "Shoulders": 75.0,
        "Spine": 15.0,
        "Hip level": 13.0,
        "Stance width": 0.56,
        "Left knee posture": 150.0,
        "Right knee posture": 155.0,
        "Head alignment": 14.0,
        "Neck tilt": 48.0,
    },
}

DEFAULT_TOLERANCES = {
    sport: {
        "Left elbow": 18.0,
        "Right elbow": 18.0,
        "Shoulders": 10.0,
        "Spine": 10.0,
        "Hip level": 10.0,
        "Stance width": 0.2,
        "Left knee posture": 14.0,
        "Right knee posture": 14.0,
        "Head alignment": 20.0,
        "Neck tilt": 12.0,
    }
    for sport in SPORTS
}

SPORT_MAP = {sport.lower(): sport for sport in SPORTS}


def normalize_sport(sport: str) -> str:
    if not sport:
        return "Archery"
    return SPORT_MAP.get(sport.strip().lower(), "Archery")


def build_default_rules(sport: str, student_angles: dict | None = None) -> dict:
    normalized = normalize_sport(sport)
    targets = deepcopy(DEFAULT_TARGETS.get(normalized, DEFAULT_TARGETS["Archery"]))
    tolerances = deepcopy(DEFAULT_TOLERANCES.get(normalized, DEFAULT_TOLERANCES["Archery"]))
    if isinstance(student_angles, dict):
        for k, v in student_angles.items():
            try:
                targets[k] = float(v)
            except (TypeError, ValueError):
                continue
    return {"targets": targets, "tolerances": tolerances}


def build_default_rule_doc(username: str, sport: str, student_angles: dict | None = None) -> dict:
    sport_name = normalize_sport(sport)
    now_ts = datetime.utcnow().timestamp()
    return {
        "student": username,
        "sport": sport_name,
        "rules": build_default_rules(sport_name, student_angles),
        "source": "default",
        "created_at": now_ts,
        "updated_at": now_ts,
    }


def build_default_rule_entry(sport: str, student_angles: dict | None = None) -> dict:
    now_ts = datetime.utcnow().timestamp()
    return {
        "rules": build_default_rules(sport, student_angles),
        "source": "default",
        "created_at": now_ts,
        "updated_at": now_ts,
    }


def build_default_rules_map(student_angles: dict | None = None) -> dict:
    return {sport: build_default_rule_entry(sport, student_angles) for sport in SPORTS}
