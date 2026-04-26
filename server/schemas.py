from pydantic import BaseModel, Field
from typing import Any, Optional


class LoginRequest(BaseModel):
    username: str
    password: str


class CourseListRequest(BaseModel):
    username: str
    password: str


class StartTaskRequest(BaseModel):
    username: str
    password: str
    course_indexes: list[int] = Field(default_factory=list)
    mode: str = "study"
    speed: Optional[float] = None
    tiku_url: str = ""
    tiku_use: str = ""
    tiku_tokens: dict[str, str] = Field(default_factory=dict)
    collect_sources: list[str] = Field(default_factory=lambda: ["chapter_quiz", "homework", "exam", "unknown"])


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    summary: dict[str, Any] = Field(default_factory=dict)


class TaskLogResponse(BaseModel):
    task_id: str
    logs: list[str] = Field(default_factory=list)


class CourseItem(BaseModel):
    classid: str
    courseid: str
    cpi: str
    name: str
    teacher: str = ""


class CourseListResponse(BaseModel):
    result: bool
    courses: list[CourseItem] = Field(default_factory=list)
    raw: str = ""


class TikuAnswerItem(BaseModel):
    id: int
    question: str
    type_code: str
    source_kind: str = "unknown"
    answer: str
    answer_text: str = ""
    source: str = "local"
    correct_count: int = 0
    updated_at: int = 0
    options_json: str = ""
    question_hash: str = ""


class TikuListResponse(BaseModel):
    items: list[TikuAnswerItem] = Field(default_factory=list)


class TikuCreateRequest(BaseModel):
    question: str
    type_code: str = "4"
    answer: str
    answer_text: str = ""
    source_kind: str = "manual"
    source: str = "web-manual"
    options: list[str] = Field(default_factory=list)


class TikuDeleteResponse(BaseModel):
    ok: bool
    id: int
