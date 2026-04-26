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
