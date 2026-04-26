import time
import re


class DocumentHandler:
    def __init__(self, task_client, logger):
        self.task_client = task_client
        self.log = logger

    def handle(self, course: dict, job: dict, job_info: dict) -> bool:
        knowledge_match = re.search(r"nodeId_(.*?)-", job.get("otherinfo", ""))
        knowledgeid = knowledge_match.group(1) if knowledge_match else job_info.get("knowledgeid", "")
        response = self.task_client.get_document(
            {
                "jobid": job["jobid"],
                "knowledgeid": knowledgeid,
                "courseid": course["courseid"],
                "clazzid": course["classid"],
                "jtoken": job.get("jtoken", ""),
                "_dc": int(time.time() * 1000),
            }
        )
        if response.status_code != 200:
            self.log(f"Document failed: {response.text}", 3)
            return False
        self.log(f"Document finished: {job.get('name', '')}")
        return True
