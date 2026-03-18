from pydantic import BaseModel
from typing import Optional, List

# authentication tokens
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None


class AdminBootstrapIn(BaseModel):
    username: str
    password: str
    full_name: Optional[str] = None
    email: Optional[str] = None

# user models
class UserIn(BaseModel):
    username: str
    password: str
    role: str = "student"
    academy_id: Optional[str] = None
    org_id: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[str] = None
    plan_code: Optional[str] = None
    plan_type: Optional[str] = None
    plan_tier: Optional[str] = None


class UserProfile(BaseModel):
    profile_image: Optional[str] = None
    full_name: Optional[str] = None
    dob: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    gender: Optional[str] = None
    address: Optional[str] = None
    bio: Optional[str] = None
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    dominant_hand: Optional[str] = None
    experience_level: Optional[str] = None
    angle_measurements: Optional[dict] = None
    assigned_sport: Optional[str] = None
    sport_rules: Optional[dict] = None

class UserOut(BaseModel):
    username: str
    role: str
    academy_id: Optional[str]
    org_id: Optional[str] = None
    email_verified: Optional[bool] = True
    email_verified_at: Optional[float] = None
    profile_image: Optional[str] = None
    full_name: Optional[str] = None
    dob: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    gender: Optional[str] = None
    address: Optional[str] = None
    bio: Optional[str] = None
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    dominant_hand: Optional[str] = None
    experience_level: Optional[str] = None
    angle_measurements: Optional[dict] = None
    assigned_sport: Optional[str] = None
    sport_rules: Optional[dict] = None
    can_add_students: Optional[bool] = None
    plan_code: Optional[str] = None
    plan_type: Optional[str] = None
    plan_tier: Optional[str] = None

class UserInDB(UserOut):
    hashed_password: str


class UserProfileUpdate(UserProfile):
    pass

# academy input/output
class AcademyIn(BaseModel):
    academy_id: str
    name: str
    address: str
    city: str
    state: str
    country: str
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None


class AcademyOut(AcademyIn):
    admins: Optional[List[str]] = []
    staff: Optional[List[str]] = []
    students: Optional[List[str]] = []

# session input
class SessionIn(BaseModel):
    student: str
    sport: str
    angles: dict
    feedback: Optional[List[str]] = []
    custom_note: Optional[str] = None
    drill_focus: Optional[str] = None
    duration_minutes: Optional[int] = None
    started_at: Optional[float] = None
    ended_at: Optional[float] = None
    intensity_rpe: Optional[int] = None
    tags: Optional[List[str]] = []
    created_by: Optional[str] = None
    timestamp: Optional[float] = None
    session_score: Optional[float] = None
    score_breakdown: Optional[dict] = None
    rep_summary: Optional[dict] = None
    phase_summary: Optional[dict] = None
    best_rep: Optional[dict] = None
    best_frame: Optional[dict] = None
    camera_summary: Optional[dict] = None
    movement_summary: Optional[dict] = None
    timeline_summary: Optional[dict] = None

# billing + plans
class PlanInfo(BaseModel):
    code: str
    name: str
    amount_inr: int
    currency: str = "INR"
    plan_type: str  # "personal" | "organization"
    tier: str  # "basic" | "pro"
    description: Optional[str] = None
    features: Optional[List[str]] = None
    ai_chat: Optional[bool] = None
    ai_analytics: Optional[bool] = None


class PlanFeaturesIn(BaseModel):
    description: Optional[str] = None
    features: Optional[List[str]] = None
    ai_chat: Optional[bool] = None
    ai_analytics: Optional[bool] = None


class CheckoutInitIn(BaseModel):
    plan_code: str
    username: str
    password: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    org_name: Optional[str] = None


class CheckoutVerifyIn(BaseModel):
    plan_code: str
    username: str
    password: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    org_name: Optional[str] = None
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str

# email verification + password reset
class EmailVerificationRequest(BaseModel):
    identity: str


class VerifyEmailIn(BaseModel):
    identity: str
    code: str


class ForgotPasswordIn(BaseModel):
    identity: str


class ResetPasswordIn(BaseModel):
    identity: str
    code: str
    new_password: str


class SignupEmailRequest(BaseModel):
    email: str


class SignupEmailVerify(BaseModel):
    email: str
    code: str

# leads
class DemoLeadIn(BaseModel):
    name: str
    email: str
    organization: Optional[str] = None
    role: Optional[str] = None
    team_size: Optional[str] = None
    timeline: Optional[str] = None
    goals: Optional[str] = None
    preferred_contact: Optional[str] = None


class SupportLeadIn(BaseModel):
    name: str
    email: str
    topic: Optional[str] = None
    message: str
    urgency: Optional[str] = None
    preferred_contact: Optional[str] = None


class LeadOut(BaseModel):
    id: Optional[str] = None
    name: str
    email: str
    organization: Optional[str] = None
    role: Optional[str] = None
    team_size: Optional[str] = None
    timeline: Optional[str] = None
    goals: Optional[str] = None
    topic: Optional[str] = None
    message: Optional[str] = None
    urgency: Optional[str] = None
    preferred_contact: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[float] = None


# policies
class PolicyIn(BaseModel):
    title: str
    body: str


class PolicyOut(BaseModel):
    id: Optional[str] = None
    key: str
    title: str
    body: str
    updated_at: Optional[float] = None
