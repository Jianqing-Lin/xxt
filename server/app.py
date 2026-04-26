from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from server.course_service import WebCourseService
from server.log_buffer import LogBuffer
from server.schemas import CourseListRequest, CourseListResponse, LoginRequest, StartTaskRequest, TaskLogResponse, TaskStatusResponse
from server.task_manager import TaskManager
from server.task_runner import WebTaskRunner


app = FastAPI(title="Autumn-xxt web api", version="0.1.0")
app.mount("/web", StaticFiles(directory="web"), name="web")
log_buffer = LogBuffer()
task_manager = TaskManager(log_buffer=log_buffer)


@app.get("/")
def index():
    return FileResponse("web/index.html")


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/auth/login")
def login(payload: LoginRequest):
    service = WebCourseService()
    try:
        service.login_and_get_cookie(payload.username, payload.password)
        return {
            "ok": True,
            "username": payload.username,
            "logs": service.logger.lines,
        }
    except SystemExit:
        return {
            "ok": False,
            "username": payload.username,
            "logs": service.logger.lines,
        }


@app.post("/api/courses/list", response_model=CourseListResponse)
def list_courses(payload: CourseListRequest):
    service = WebCourseService()
    try:
        data = service.list_courses(payload.username, payload.password)
    except SystemExit:
        return CourseListResponse(result=False, courses=[], raw="login or cookie validation failed")
    return CourseListResponse(result=bool(data.get("result")), courses=data.get("courses", []), raw=data.get("raw", ""))


@app.post("/api/tasks/start", response_model=TaskStatusResponse)
def start_task(payload: StartTaskRequest):
    task = task_manager.create_task()
    task_manager.append_log(task.task_id, f"task created: mode={payload.mode}, user={payload.username}")

    def emit_log(line: str):
        task_manager.append_log(task.task_id, line)

    def run_real_task():
        runner = WebTaskRunner(emit_log=emit_log)
        return runner.run(
            username=payload.username,
            password=payload.password,
            course_indexes=payload.course_indexes,
            mode=payload.mode,
            speed=payload.speed,
            tiku_url=payload.tiku_url,
            tiku_use=payload.tiku_use,
            tiku_tokens=payload.tiku_tokens,
        )

    task_manager.run_background(run_real_task, task=task)
    return TaskStatusResponse(task_id=task.task_id, status=task.status, summary=task.summary)


@app.get("/api/tasks", response_model=list[TaskStatusResponse])
def list_tasks():
    return [TaskStatusResponse(task_id=task.task_id, status=task.status, summary=task.summary) for task in task_manager.list_tasks()]


@app.get("/api/tasks/{task_id}", response_model=TaskStatusResponse)
def get_task(task_id: str):
    task = task_manager.get_task(task_id)
    if task is None:
        return TaskStatusResponse(task_id=task_id, status="not_found", summary={})
    return TaskStatusResponse(task_id=task.task_id, status=task.status, summary=task.summary)


@app.get("/api/tasks/{task_id}/logs", response_model=TaskLogResponse)
def get_task_logs(task_id: str):
    return TaskLogResponse(task_id=task_id, logs=task_manager.get_logs(task_id))
