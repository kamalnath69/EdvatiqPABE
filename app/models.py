from pydantic import BaseModel, Field
from typing import List, Optional

class Academy(BaseModel):
    academy_id: str
    name: str
    address: str
    city: str
    state: str
    country: str
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    admins: List[str] = []  # usernames
    staff: List[str] = []
    students: List[str] = []

class Session(BaseModel):
    student: str
    sport: str
    timestamp: float
    angles: dict
    feedback: Optional[List[str]] = []
