def normalize_role(role: str) -> str:
    if not role:
        return ""
    role_norm = role.strip()
    if role_norm == "academyAdmin":
        return "academy_admin"
    return role_norm


def has_any_role(user_role: str, allowed_roles: list[str]) -> bool:
    normalized_user = normalize_role(user_role)
    normalized_allowed = {normalize_role(role) for role in allowed_roles}
    return normalized_user in normalized_allowed
