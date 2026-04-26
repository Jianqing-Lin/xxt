from core.api import Api


class CourseStudyWorkflow:
    def __init__(self, parser, dispatcher, task_client, logger, collect_tiku: bool):
        self.parser = parser
        self.dispatcher = dispatcher
        self.task_client = task_client
        self.log = logger
        self.collect_tiku = collect_tiku

    def get_job_list(self, course: dict, point: dict) -> tuple[list[dict], dict]:
        params = {
            "clazzid": course["classid"],
            "courseid": course["courseid"],
            "knowledgeid": point["id"],
            "ut": "s",
            "cpi": course["cpi"],
            "v": "2025-0424-1038-3",
            "mooc2": 1,
        }
        jobs = []
        job_info = {}
        for num in "0123456":
            response = self.task_client.get_job_cards(params, num)
            if response.status_code != 200:
                self.log(f"Get job list failed: {point['title']}", 3)
                self.log(response.text, 0)
                return [], {}
            current_jobs, current_info = self.parser.parse_course_cards(response.text)
            if current_info.get("notOpen"):
                return [], current_info
            jobs.extend(current_jobs)
            job_info.update(current_info)
        return self.parser.dedupe_jobs(jobs), job_info

    def dispatch_job(self, course: dict, point: dict, job: dict, job_info: dict):
        job_type = job.get("type", "")
        self.log(f"Job start: {job_type} - {job.get('name', '')}")
        return self.dispatcher.dispatch(job_type, course, point, job, job_info)

    def iter_runnable_jobs(self, jobs: list[dict]):
        for job in jobs:
            if self.collect_tiku and job.get("type") != "workid":
                continue
            yield job

    def study_empty_page(self, course: dict, point: dict) -> bool:
        response = self.task_client.get_empty_page(
            {
                "courseId": course["courseid"],
                "clazzid": course["classid"],
                "chapterId": point["id"],
                "cpi": course["cpi"],
                "verificationcode": "",
                "mooc2": 1,
                "microTopicId": 0,
                "editorPreview": 0,
            }
        )
        if response.status_code != 200:
            self.log(f"Empty page failed: {point['title']}", 3)
            return False
        self.log(f"Empty page finished: {point['title']}")
        return True

    def summarize_job_result(self, summary: dict, job_type: str, result):
        if result is None:
            summary["unsupported"] += 1
            return
        if job_type in {"read", "document"}:
            summary["completed" if result else "skipped"] += 1
            return
        if job_type in {"video", "audio", "workid"}:
            summary["completed" if result else "failed"] += 1

    def close(self):
        close = getattr(self.task_client, "close", None)
        if callable(close):
            close()
