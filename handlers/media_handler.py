import hashlib
import random
import re
import time

from core.api import Api


class MediaHandler:
    def __init__(self, task_client, logger, cookie: dict, headers: dict, speed: float):
        self.task_client = task_client
        self.log = logger
        self.cookie = cookie
        self.headers = headers
        self.speed = speed

    def get_uid(self) -> str:
        for key in ("_uid", "UID"):
            value = self.cookie.get(key)
            if value:
                return str(value)
        return ""

    def get_fid(self) -> str:
        return str(self.cookie.get("fid", ""))

    def get_media_headers(self, media_type: str) -> dict:
        headers = dict(self.headers)
        headers["Referer"] = Api.Video_Referer if media_type == "video" else Api.Audio_Referer
        return headers

    def get_media_enc(self, classid: str, userid: str, job: dict, playing_time: int, duration: int) -> str:
        payload = (
            f"[{classid}]"
            f"[{userid}]"
            f"[{job['jobid']}]"
            f"[{job['objectid']}]"
            f"[{playing_time * 1000}]"
            f"[d_yHJ!$pdA~5]"
            f"[{duration * 1000}]"
            f"[0_{duration}]"
        )
        return hashlib.md5(payload.encode("utf-8")).hexdigest()

    def resolve_rt(self, job: dict) -> str:
        rt = str(job.get("rt", "")).strip()
        if rt:
            return rt
        match = re.search(r"-rt_([1d])", job.get("otherinfo", ""))
        if match:
            return "0.9" if match.group(1) == "d" else "1"
        return "1"

    def normalize_play_time(self, value) -> int:
        try:
            play_time = int(float(value or 0))
        except (TypeError, ValueError):
            return 0
        if play_time > 1000:
            return play_time // 1000
        return play_time

    def format_media_progress(self, current: int, duration: int) -> str:
        current = max(0, int(current))
        duration = max(0, int(duration))
        percent = 100 if duration <= 0 else min(100, int(current * 100 / duration))
        return f"{current}/{duration}s ({percent}%)"

    def get_media_status(self, job: dict, media_type: str):
        response = self.task_client.get_media_status(
            job["objectid"],
            {
                "k": self.get_fid(),
                "flag": "normal",
            },
            self.get_media_headers(media_type),
        )
        if response.status_code != 200:
            self.log(f"Media status failed: {response.status_code}", 2)
            return None
        try:
            payload = response.json()
        except ValueError:
            self.log(f"Media status invalid: {response.text[:200]}", 2)
            return None
        if payload.get("status") != "success":
            self.log(f"Media status not ready: {payload}", 2)
            return None
        return payload

    def media_progress_log(self, course: dict, job: dict, status_payload: dict, duration: int, playing_time: int, media_type: str):
        userid = self.get_uid()
        if not userid:
            self.log("Cannot resolve UID for media log", 3)
            return False, 0
        playing_time = max(0, min(int(playing_time), duration))
        params = {
            "clazzId": course["classid"],
            "playingTime": playing_time,
            "duration": duration,
            "clipTime": f"0_{duration}",
            "objectId": job["objectid"],
            "otherInfo": job.get("otherinfo", ""),
            "courseId": course["courseid"],
            "jobid": job["jobid"],
            "userid": userid,
            "isdrag": "3",
            "view": "pc",
            "enc": self.get_media_enc(course["classid"], userid, job, playing_time, duration),
            "dtype": "Audio" if media_type == "audio" else "Video",
        }
        if job.get("videoFaceCaptureEnc"):
            params["videoFaceCaptureEnc"] = job["videoFaceCaptureEnc"]
        if job.get("attDuration"):
            params["attDuration"] = job["attDuration"]
        if job.get("attDurationEnc"):
            params["attDurationEnc"] = job["attDurationEnc"]

        rt = self.resolve_rt(job)
        response = None
        if rt:
            params.update({"rt": rt, "_t": int(time.time() * 1000)})
            response = self.task_client.post_media_log(
                f"{Api.Media_Log}{course['cpi']}/{status_payload['dtoken']}",
                params,
                self.get_media_headers(media_type),
            )
        else:
            for current_rt in ("0.9", "1"):
                params.update({"rt": current_rt, "_t": int(time.time() * 1000)})
                response = self.task_client.post_media_log(
                    f"{Api.Media_Log}{course['cpi']}/{status_payload['dtoken']}",
                    params,
                    self.get_media_headers(media_type),
                )
                if response.status_code == 200:
                    break
                if response.status_code != 403:
                    break
        if response is None:
            return False, 0
        if response.status_code != 200:
            self.log(f"Media log failed: {response.status_code} {response.text[:200]}", 2)
            return False, response.status_code
        try:
            payload = response.json()
        except ValueError:
            self.log(f"Media log invalid: {response.text[:200]}", 2)
            return False, 0
        return bool(payload.get("isPassed")), 200

    def handle(self, course: dict, job: dict, media_type: str) -> bool:
        if not job.get("objectid"):
            self.log(f"Media object id missing: {job}", 2)
            return False
        status_payload = self.get_media_status(job, media_type)
        if status_payload is None:
            return False
        duration = int(float(status_payload.get("duration") or job.get("duration") or 0))
        if duration <= 0:
            self.log(f"Media duration invalid: {job.get('name', '')}", 2)
            return False
        play_time = self.normalize_play_time(job.get("playTime", 0))
        if status_payload.get("isPassed"):
            self.log(f"Media already finished: {job.get('name', '')}")
            return True
        if status_payload.get("playingTime") is not None:
            play_time = max(play_time, self.normalize_play_time(status_payload.get("playingTime", 0)))
        self.log(f"Media start: {job.get('name', '')} {self.format_media_progress(play_time, duration)}")

        passed, state = self.media_progress_log(course, job, status_payload, duration, play_time, media_type)
        if passed:
            self.log(f"Media finished instantly: {job.get('name', '')}")
            return True
        if state == 403:
            return False

        passed, state = self.media_progress_log(course, job, status_payload, duration, duration, media_type)
        if passed:
            self.log(f"Media finished instantly: {job.get('name', '')}")
            return True
        if state == 403:
            return False

        current = max(play_time, 0)
        last_reported = current
        last_tick = time.time()
        last_progress_output = time.time()
        progress_interval = 5
        wait_seconds = random.randint(30, 90)

        while current < duration:
            now = time.time()
            current = min(duration, current + max(1, int((now - last_tick) * self.speed)))
            last_tick = now

            if now - last_progress_output >= progress_interval or current == duration:
                self.log(f"Media progress: {job.get('name', '')} {self.format_media_progress(current, duration)}")
                last_progress_output = now

            if current - last_reported >= wait_seconds or current == duration:
                passed, state = self.media_progress_log(course, job, status_payload, duration, current, media_type)
                if passed:
                    self.log(f"Media finished: {job.get('name', '')}")
                    return True
                if state == 403:
                    refreshed = self.get_media_status(job, media_type)
                    if refreshed is None:
                        return False
                    status_payload = refreshed
                    self.log(
                        f"Media status refreshed: {job.get('name', '')} {self.format_media_progress(current, duration)}",
                        2,
                    )
                last_reported = current
                wait_seconds = random.randint(30, 90)
            time.sleep(1)

        passed, _ = self.media_progress_log(course, job, status_payload, duration, duration, media_type)
        if passed:
            self.log(f"Media finished: {job.get('name', '')}")
            return True
        self.log(f"Media failed: {job.get('name', '')}", 2)
        return False
