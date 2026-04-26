from core.api import Api


class CourseStudyWorkflow:
    def __init__(self, parser, dispatcher, task_client, logger, collect_tiku: bool):
        self.parser = parser
        self.dispatcher = dispatcher
        self.task_client = task_client
        self.log = logger
        self.collect_tiku = collect_tiku
        runtime = getattr(getattr(dispatcher, "runtime_holder", None), "runtime", None)
        self.collect_sources = getattr(runtime, "collect_sources", {"chapter_quiz", "homework", "exam", "unknown"})

    def get_jobs_from_chapter_info(self, course: dict, point: dict) -> tuple[list[dict], dict]:
        try:
            response = self.task_client.get_chapter_info(course["classid"], course["courseid"])
            if response.status_code != 200 or "application/json" not in str(response.headers.get("content-type", "")):
                return [], {}
            payload = response.json()
        except Exception as error:
            self.log(f"Collect chapter info failed: {point['title']} | {error}", 2)
            return [], {}
        nodes = payload.get("data", []) if isinstance(payload, dict) else []
        target_ids = {str(point.get("id", ""))}
        jobs = []
        for node in nodes:
            if str(node.get("id", "")) not in target_ids:
                continue
            for card in node.get("card", {}).get("data", []) or []:
                for content in card.get("contentcard", {}).get("data", []) or []:
                    content_type = str(content.get("type", "")).lower()
                    if content_type not in {"workid", "work", "quiz", "test"}:
                        continue
                    jobid = str(content.get("id") or content.get("jobid") or content.get("workid") or "")
                    if jobid and not jobid.startswith("work-"):
                        jobid = f"work-{jobid}"
                    jobs.append(
                        {
                            "type": "workid",
                            "jobid": jobid,
                            "name": content.get("name") or card.get("title") or point.get("title", "work"),
                            "otherinfo": content.get("otherinfo", ""),
                            "enc": content.get("enc", ""),
                            "aid": content.get("aid", ""),
                            "objectid": content.get("objectid", ""),
                        }
                    )
        if jobs:
            self.log(f"Collect chapter info jobs: {len(jobs)} - {point['title']}")
        return self.parser.dedupe_jobs(jobs), {"knowledgeid": point.get("id", ""), "cpi": course.get("cpi", "")}

    def get_job_list(self, course: dict, point: dict) -> tuple[list[dict], dict]:
        if self.collect_tiku:
            chapter_jobs, chapter_info = self.get_jobs_from_chapter_info(course, point)
            if chapter_jobs:
                return chapter_jobs, chapter_info
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
            if self.collect_tiku and not current_jobs and not jobs:
                preview = " ".join(response.text[:300].split())
                self.log(f"Collect debug: no cards parsed for {point['title']} num={num}, preview={preview}", 0)
            if current_info.get("notOpen"):
                return [], current_info
            jobs.extend(current_jobs)
            for key, value in current_info.items():
                if value in (None, "", [], {}, ()):  # keep first non-empty runtime metadata
                    continue
                job_info[key] = value
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
