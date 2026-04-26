from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

from clients.session import SessionFactory
from clients.task_client import TaskClient
from handlers.document_handler import DocumentHandler
from handlers.media_handler import MediaHandler
from handlers.read_handler import ReadHandler
from handlers.work_handler import WorkHandler
from model.tiku import TikuStore
from parsers.course_task_parser import CourseTaskParser
from workflow.course_study_workflow import CourseStudyWorkflow
from workflow.job_dispatcher import JobDispatcher


class Course:
    def __init__(self, Courses):
        self.course = Courses.course
        self.User = Courses.User
        self.iLog = Courses.iLog
        self.runtime = getattr(self.User.ice, "runtime", None)
        self.speed = getattr(self.runtime, "speed", getattr(self.User.ice, "speed", 1.0))
        self.collect_tiku = getattr(self.runtime, "collect_tiku", getattr(self.User.ice, "collect_tiku", False))
        self.collect_threads = self._normalize_collect_threads(getattr(self.runtime, "collect_threads", 1))
        self.parser = CourseTaskParser()
        self.tiku = TikuStore(
            adapter_url=getattr(self.User.ice, "tiku_url", ""),
            use=getattr(self.User.ice, "tiku_use", ""),
            tokens=getattr(self.User.ice, "tiku_tokens", {}),
            proxy=getattr(self.User.ice, "proxy", None),
        )
        self.session_factory = SessionFactory(
            headers=self.User.ice.headers,
            cookies=self.User.cookie,
            proxy=self.User.ice.proxy,
            follow_redirects=True,
        )
        self.task_client = TaskClient(self.session_factory)
        self.read_handler = ReadHandler(self.task_client, self.iLog)
        self.document_handler = DocumentHandler(self.task_client, self.iLog)
        self.work_handler = WorkHandler(
            self.task_client,
            self.tiku,
            self.parser,
            self.iLog,
            self.collect_tiku,
            self.get_work_headers,
            collect_sources=getattr(self.runtime, "collect_sources", None),
        )
        self.media_handler = MediaHandler(
            self.task_client,
            self.iLog,
            self.User.cookie,
            self.User.ice.headers,
            self.speed,
        )
        self.dispatcher = JobDispatcher(
            {
                "read": lambda course, point, job, job_info: self.read_handler.handle(course, job, job_info),
                "document": lambda course, point, job, job_info: self.document_handler.handle(course, job, job_info),
                "workid": lambda course, point, job, job_info: self.work_handler.handle(course, job, job_info),
                "video": lambda course, point, job, job_info: self.media_handler.handle(course, job, "video"),
                "audio": lambda course, point, job, job_info: self.media_handler.handle(course, job, "audio"),
            },
            self.iLog,
        )
        self.dispatcher.runtime_holder = self
        self.study_workflow = CourseStudyWorkflow(
            parser=self.parser,
            dispatcher=self.dispatcher,
            task_client=self.task_client,
            logger=self.iLog,
            collect_tiku=self.collect_tiku,
        )
        self.iLog(f"Tiku stats: {self.tiku.stats()}")
        self.summary = {
            "courses": 0,
            "points": 0,
            "jobs": 0,
            "completed": 0,
            "skipped": 0,
            "unsupported": 0,
            "failed": 0,
        }
        self.summary_lock = Lock()
        self.new()

    def _normalize_collect_threads(self, value):
        try:
            threads = int(value)
        except (TypeError, ValueError):
            threads = 1
        return max(1, min(32, threads))

    def _new_summary_delta(self):
        return {
            "courses": 0,
            "points": 0,
            "jobs": 0,
            "completed": 0,
            "skipped": 0,
            "unsupported": 0,
            "failed": 0,
        }

    def _merge_summary(self, delta: dict):
        with self.summary_lock:
            for key, value in delta.items():
                self.summary[key] += value

    def new(self):
        try:
            for course in self.course:
                self.process_course(course)
            self.iLog(f"Study summary: {self.summary}")
        finally:
            self.study_workflow.close()

    def process_course(self, course: dict):
        self.summary["courses"] += 1
        self.iLog(f"Course start: {course['name']}")
        points = self.parse_course_points(course["html"])
        self.summary["points"] += len(points)
        if not points:
            self.iLog(f"No points found: {course['name']}", 2)
            return
        if self.collect_tiku and self.collect_threads > 1:
            self.iLog(f"Collect threads: {self.collect_threads} - {course['name']}")
            with ThreadPoolExecutor(max_workers=self.collect_threads) as executor:
                futures = [executor.submit(self._process_point_collect, course, point) for point in points]
                for future in as_completed(futures):
                    self._merge_summary(future.result())
            return
        for point in points:
            self.process_point(course, point)

    def _process_point_collect(self, course: dict, point: dict):
        summary = self._new_summary_delta()
        self._process_point_with_summary(course, point, summary)
        return summary

    def process_point(self, course: dict, point: dict):
        self._process_point_with_summary(course, point, self.summary)

    def _process_point_with_summary(self, course: dict, point: dict, summary_target: dict):
        self.iLog(f"Point start: {point['title']}")
        if not self.collect_tiku:
            if point["has_finished"]:
                self.iLog(f"Point already finished: {point['title']}")
                summary_target["skipped"] += 1
                return
            if point["need_unlock"]:
                self.iLog(f"Point locked, skip: {point['title']}", 2)
                summary_target["skipped"] += 1
                return
        jobs, job_info = self.get_job_list(course, point)
        if job_info.get("notOpen"):
            self.iLog(f"Point not open, skip: {point['title']}", 2)
            summary_target["skipped"] += 1
            return
        if not jobs:
            if self.collect_tiku:
                self.iLog(f"Collect mode: no jobs found in point: {point['title']}", 2)
                summary_target["skipped"] += 1
                return
            if self.study_empty_page(course, point):
                summary_target["completed"] += 1
            else:
                summary_target["skipped"] += 1
            return
        for job in self.study_workflow.iter_runnable_jobs(jobs):
            summary_target["jobs"] += 1
            self.dispatch_job(course, point, job, job_info, summary_target)

    def parse_course_points(self, html_text: str) -> list[dict]:
        return self.parser.parse_course_points(html_text)

    def get_job_list(self, course: dict, point: dict) -> tuple[list[dict], dict]:
        return self.study_workflow.get_job_list(course, point)

    def parse_course_cards(self, html_text: str) -> tuple[list[dict], dict]:
        return self.parser.parse_course_cards(html_text)

    def dispatch_job(self, course: dict, point: dict, job: dict, job_info: dict, summary_target=None):
        result = self.study_workflow.dispatch_job(course, point, job, job_info)
        self.study_workflow.summarize_job_result(summary_target or self.summary, job.get("type", ""), result)

    def get_work_headers(self) -> dict:
        headers = dict(self.User.ice.headers)
        headers.update(
            {
                "Host": "mooc1.chaoxing.com",
                "Origin": "https://mooc1.chaoxing.com",
                "Referer": "https://mooc1.chaoxing.com/mooc-ans/knowledge/cards",
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            }
        )
        return headers

    def study_empty_page(self, course: dict, point: dict) -> bool:
        return self.study_workflow.study_empty_page(course, point)
