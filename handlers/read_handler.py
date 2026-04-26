class ReadHandler:
    def __init__(self, task_client, logger):
        self.task_client = task_client
        self.log = logger

    def handle(self, course: dict, job: dict, job_info: dict) -> bool:
        response = self.task_client.get_read(
            {
                "jobid": job["jobid"],
                "knowledgeid": job_info.get("knowledgeid", ""),
                "jtoken": job.get("jtoken", ""),
                "courseid": course["courseid"],
                "clazzid": course["classid"],
            }
        )
        if response.status_code != 200:
            self.log(f"Read failed: {response.text}", 3)
            return False
        try:
            payload = response.json()
        except ValueError:
            self.log(f"Read result: {response.text}", 0)
            return False
        self.log(f"Read finished: {payload.get('msg', 'ok')}")
        return True
