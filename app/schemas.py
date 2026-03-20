from pydantic import BaseModel, ConfigDict, Field
from typing import Any, Optional, List, Dict

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


class CoachMessageIn(BaseModel):
    role: str
    text: str


class CoachChatRequest(BaseModel):
    messages: List[CoachMessageIn]
    sport: Optional[str] = None
    student: Optional[str] = None
    context: Optional[dict] = None


class CoachLiveRequest(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    sport: str
    student: Optional[str] = None
    feedback: Optional[List[str]] = None
    angles: Optional[dict] = None
    session_score: Optional[float] = Field(default=None, alias="sessionScore")
    phase: Optional[str] = None
    rep_count: Optional[int] = Field(default=None, alias="repCount")
    tracking_quality: Optional[str] = Field(default=None, alias="trackingQuality")
    drill_focus: Optional[str] = Field(default=None, alias="drillFocus")
    custom_note: Optional[str] = Field(default=None, alias="customNote")


class CoachConfigIn(BaseModel):
    api_key: Optional[str] = None
    key_source: Optional[str] = None
    voice_enabled: Optional[bool] = None
    live_guidance_enabled: Optional[bool] = None
    voice_style: Optional[str] = None


class CoachConfigOut(BaseModel):
    configured: bool
    api_key_masked: Optional[str] = None
    key_source: str = "personal"
    platform_key_available: bool = False
    wallet_balance: float = 0
    wallet_currency: str = "credits"
    credit_rate_per_1k_tokens: float = 1
    inr_per_credit: float = 1
    suggested_top_up: float = 100
    voice_enabled: bool = True
    live_guidance_enabled: bool = True
    voice_style: str = "calm"


class WalletTopUpIn(BaseModel):
    credits: float = Field(default=100, gt=0)
    amount_inr: Optional[float] = Field(default=None, gt=0)
    note: Optional[str] = None


class WalletRechargeInitIn(BaseModel):
    credits: float = Field(default=100, gt=0)
    amount_inr: Optional[float] = Field(default=None, gt=0)
    note: Optional[str] = None


class WalletRechargeOrderOut(BaseModel):
    order_id: str
    amount: int
    currency: str
    key_id: str
    credits: float
    amount_inr: float


class WalletRechargeVerifyIn(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class WalletTransactionOut(BaseModel):
    id: str
    username: str
    type: str
    credits: float
    balance_after: float
    amount_inr: Optional[float] = None
    tokens_used: Optional[int] = None
    source: Optional[str] = None
    model: Optional[str] = None
    note: Optional[str] = None
    created_at: float


class WalletSummaryOut(BaseModel):
    username: str
    balance: float = 0
    currency: str = "credits"
    preferred_key_source: str = "personal"
    personal_key_configured: bool = False
    platform_key_available: bool = False
    default_credit_rate_per_1k_tokens: float = 1
    inr_per_credit: float = 1
    suggested_top_up: float = 100
    updated_at: Optional[float] = None


class AiPlatformSettingsIn(BaseModel):
    default_api_key: Optional[str] = None
    credit_rate_per_1k_tokens: Optional[float] = Field(default=None, gt=0)
    inr_per_credit: Optional[float] = Field(default=None, gt=0)
    suggested_top_up: Optional[float] = Field(default=None, gt=0)


class AiPlatformSettingsOut(BaseModel):
    default_api_key_masked: Optional[str] = None
    platform_key_available: bool = False
    credit_rate_per_1k_tokens: float = 1
    inr_per_credit: float = 1
    suggested_top_up: float = 100
    api_key_source: Optional[str] = None


class UserSettingsIn(BaseModel):
    theme: Optional[str] = "light"
    density: Optional[str] = "comfortable"
    layout: Optional[str] = "workspace"
    quick_search_enabled: Optional[bool] = True
    notifications_email: Optional[bool] = True
    notifications_in_app: Optional[bool] = True
    onboarding_seen: Optional[bool] = False
    camera_defaults: Optional[Dict[str, Any]] = None
    live_defaults: Optional[Dict[str, Any]] = None


class AcademySettingsIn(BaseModel):
    academy_id: Optional[str] = None
    branding: Optional[Dict[str, Any]] = None
    support: Optional[Dict[str, Any]] = None
    notification_defaults: Optional[Dict[str, Any]] = None
    sport_policies: Optional[Dict[str, Any]] = None
    reminder_defaults: Optional[Dict[str, Any]] = None


class WorkspaceSettingsOut(BaseModel):
    user: Dict[str, Any]
    academy: Dict[str, Any]


class NotificationOut(BaseModel):
    id: str
    actor: Optional[str] = None
    action: str
    entity_type: str
    entity_id: Optional[str] = None
    summary: str
    created_at: float
    read: bool = False
    target_user: Optional[str] = None
    academy_id: Optional[str] = None
    org_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class ReportIn(BaseModel):
    title: str
    scope: str = "personal"
    student: Optional[str] = None
    sport: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    filters: Optional[Dict[str, Any]] = None
    summary: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None
    chart_config: Optional[Dict[str, Any]] = None


class ReportOut(ReportIn):
    id: str
    owner: str
    academy_id: Optional[str] = None
    org_id: Optional[str] = None
    share_token: Optional[str] = None
    created_at: float
    updated_at: float
    export_requests: Optional[List[Dict[str, Any]]] = None


class TrainingPlanIn(BaseModel):
    title: str
    student: str
    sport: Optional[str] = None
    summary: Optional[str] = None
    weekly_focus: Optional[List[str]] = None
    target_metrics: Optional[Dict[str, Any]] = None
    assigned_drills: Optional[List[Dict[str, Any]]] = None
    coach_comments: Optional[str] = None
    due_date: Optional[str] = None
    status: Optional[str] = "active"
    progress: Optional[float] = 0


class TrainingPlanProgressIn(BaseModel):
    progress: Optional[float] = None
    status: Optional[str] = None
    completion_notes: Optional[str] = None
    drill_updates: Optional[List[Dict[str, Any]]] = None


class TrainingPlanOut(TrainingPlanIn):
    id: str
    owner: str
    academy_id: Optional[str] = None
    created_at: float
    updated_at: float
    completion_notes: Optional[str] = None


class CoachReviewIn(BaseModel):
    title: str
    student: str
    sport: Optional[str] = None
    primary_session_id: Optional[str] = None
    comparison_session_id: Optional[str] = None
    summary: Optional[str] = None
    notes: Optional[str] = None
    approval_state: Optional[str] = "draft"
    annotations: Optional[List[Dict[str, Any]]] = None
    key_frames: Optional[List[Dict[str, Any]]] = None
    attachments: Optional[List[str]] = None


class CoachReviewOut(CoachReviewIn):
    id: str
    reviewer: str
    academy_id: Optional[str] = None
    created_at: float
    updated_at: float


class CalendarEventIn(BaseModel):
    title: str
    event_type: Optional[str] = "training"
    start_at: float
    end_at: float
    description: Optional[str] = None
    student: Optional[str] = None
    attendees: Optional[List[str]] = None
    reminder_minutes: Optional[int] = None
    status: Optional[str] = "scheduled"
    location: Optional[str] = None


class CalendarEventOut(CalendarEventIn):
    id: str
    owner: str
    academy_id: Optional[str] = None
    created_at: float
    updated_at: float


class InviteIn(BaseModel):
    email: str
    username: Optional[str] = None
    role: str
    academy_id: Optional[str] = None
    org_id: Optional[str] = None
    full_name: Optional[str] = None
    message: Optional[str] = None


class InviteAcceptIn(BaseModel):
    token: str
    username: str
    password: str
    full_name: Optional[str] = None


class InviteOut(InviteIn):
    id: str
    invited_by: str
    token: str
    status: str
    created_at: float
    expires_at: float
    accepted_at: Optional[float] = None


class FavoriteIn(BaseModel):
    entity_type: str
    entity_id: str
    title: str
    subtitle: Optional[str] = None
    href: Optional[str] = None
    icon: Optional[str] = None


class FavoriteOut(FavoriteIn):
    id: str
    owner: str
    created_at: float


class AttachmentIn(BaseModel):
    entity_type: str
    entity_id: str
    filename: str
    media_type: Optional[str] = None
    size_bytes: Optional[int] = None
    external_url: Optional[str] = None
    storage_key: Optional[str] = None
    upload_status: Optional[str] = "ready"
    notes: Optional[str] = None


class AttachmentOut(AttachmentIn):
    id: str
    owner: str
    academy_id: Optional[str] = None
    created_at: float
    updated_at: float


class SearchResultOut(BaseModel):
    type: str
    id: str
    title: str
    subtitle: Optional[str] = None
    href: Optional[str] = None
    icon: Optional[str] = None
    roleScope: Optional[str] = None


class AuditLogOut(BaseModel):
    id: str
    actor: Optional[str] = None
    action: str
    entity_type: str
    entity_id: Optional[str] = None
    summary: str
    academy_id: Optional[str] = None
    org_id: Optional[str] = None
    target_user: Optional[str] = None
    created_at: float
    metadata: Optional[Dict[str, Any]] = None


class BillingWorkspaceOut(BaseModel):
    current_plan: Optional[Dict[str, Any]] = None
    available_plans: List[Dict[str, Any]]
    payment_history: List[Dict[str, Any]]
    organization: Optional[Dict[str, Any]] = None


class SystemStatusOut(BaseModel):
    database_ok: bool
    email_configured: bool
    razorpay_configured: bool
    ai_configured: bool
    enabled_features: List[str]
    collection_counts: Dict[str, int]


class HelpArticleIn(BaseModel):
    title: str
    body: str
    category: Optional[str] = "general"
    audience: Optional[str] = "all"
    order: Optional[int] = 0
    published: Optional[bool] = True


class HelpArticleOut(HelpArticleIn):
    id: str
    created_by: Optional[str] = None
    created_at: float
    updated_at: float
