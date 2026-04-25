import hashlib
import json
import random
import re
import time
from typing import Optional

from bs4 import BeautifulSoup

from core.api import Api
from core.crates.Http import Http
from model.tiku import TikuStore


class Course:
   def __init__(self, Courses):
       self.course = Courses.course
       self.User = Courses.User
       self.iLog = Courses.iLog
       self.speed = getattr(self.User.ice, "speed", 1.0)
       self.collect_tiku = getattr(self.User.ice, "collect_tiku", False)
       self.tiku = TikuStore(
           adapter_url=getattr(self.User.ice, "tiku_url", ""),
           use=getattr(self.User.ice, "tiku_use", ""),
           tokens=getattr(self.User.ice, "tiku_tokens", {}),
           proxy=getattr(self.User.ice, "proxy", None),
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
       self.new()

   def new(self):
       for course in self.course:
           self.process_course(course)
       self.iLog(f"Study summary: {self.summary}")

   def process_course(self, course: dict):
       self.summary["courses"] += 1
       self.iLog(f"Course start: {course['name']}")
       points = self.parse_course_points(course["html"])
       self.summary["points"] += len(points)
       if not points:
           self.iLog(f"No points found: {course['name']}", 2)
           return
       for point in points:
           self.process_point(course, point)

   def process_point(self, course: dict, point: dict):
       self.iLog(f"Point start: {point['title']}")
       if point["has_finished"]:
           self.iLog(f"Point already finished: {point['title']}")
           self.summary["skipped"] += 1
           return
       if point["need_unlock"]:
           self.iLog(f"Point locked, skip: {point['title']}", 2)
           self.summary["skipped"] += 1
           return
       jobs, job_info = self.get_job_list(course, point)
       if job_info.get("notOpen"):
           self.iLog(f"Point not open, skip: {point['title']}", 2)
           self.summary["skipped"] += 1
           return
       if not jobs:
           if self.study_empty_page(course, point):
               self.summary["completed"] += 1
           else:
               self.summary["skipped"] += 1
           return
       for job in jobs:
           if self.collect_tiku and job.get("type") != "workid":
               continue
           self.summary["jobs"] += 1
           self.dispatch_job(course, point, job, job_info)

   def parse_course_points(self, html_text: str) -> list[dict]:
       soup = BeautifulSoup(html_text, "html.parser")
       points = []
       for chapter_unit in soup.find_all("div", class_="chapter_unit"):
           for raw_point in chapter_unit.find_all("li"):
               point = raw_point.find("div")
               if point is None:
                   continue
               point_id = point.get("id", "")
               match = re.search(r"^cur(\d+)$", point_id)
               if match is None:
                   continue
               title_node = raw_point.select_one("a.clicktitle")
               title = title_node.get_text(strip=True) if title_node else match.group(1)
               tips_node = raw_point.select_one("span.bntHoverTips")
               tips = tips_node.get_text(strip=True) if tips_node else ""
               count_node = raw_point.select_one("input.knowledgeJobCount")
               points.append(
                   {
                       "id": match.group(1),
                       "title": title,
                       "jobCount": count_node.get("value", "1") if count_node else "1",
                       "has_finished": "已完成" in tips,
                       "need_unlock": "解锁" in tips,
                   }
               )
       return points

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
       with Http.Client(
           headers=self.User.ice.headers,
           cookies=self.User.cookie,
           proxies=self.User.ice.proxy,
           follow_redirects=True,
       ) as r:
           for num in "0123456":
               response = r.get(Api.Course_Cards, params={**params, "num": num})
               if response.status_code != 200:
                   self.iLog(f"Get job list failed: {point['title']}", 3)
                   self.iLog(response.text, 0)
                   return [], {}
               current_jobs, current_info = self.parse_course_cards(response.text)
               if current_info.get("notOpen"):
                   return [], current_info
               jobs.extend(current_jobs)
               job_info.update(current_info)
       unique_jobs = []
       seen_jobids = set()
       for job in jobs:
           jobid = job.get("jobid") or job.get("mid") or f"{job.get('type')}:{job.get('name')}"
           if jobid in seen_jobids:
               continue
           seen_jobids.add(jobid)
           unique_jobs.append(job)
       return unique_jobs, job_info

   def parse_course_cards(self, html_text: str) -> tuple[list[dict], dict]:
       if "章节未开放" in html_text:
           return [], {"notOpen": True}
       match = re.search(r"mArg\s*=\s*(\{.*?\});", html_text, re.S)
       if match is None:
           return [], {}
       try:
           cards_data = json.loads(match.group(1))
       except json.JSONDecodeError:
           return [], {}
       defaults = cards_data.get("defaults", {})
       job_info = {
           "ktoken": defaults.get("ktoken", ""),
           "cpi": defaults.get("cpi", ""),
           "knowledgeid": defaults.get("knowledgeid", ""),
       }
       jobs = []
       for card in cards_data.get("attachments", []):
           if card.get("isPassed"):
               continue
           card_type = str(card.get("type", "")).lower()
           if card.get("job") is None and card_type == "read" and not card.get("property", {}).get("read", False):
               jobs.append(
                   {
                       "type": "read",
                       "jobid": card.get("jobid", ""),
                       "name": card.get("property", {}).get("title", "read"),
                       "jtoken": card.get("jtoken", ""),
                   }
               )
               continue
           other_info = str(card.get("otherInfo", ""))
           if other_info:
               other_info = other_info.split("&")[0]
           job = {
               "type": card_type,
               "jobid": card.get("jobid", ""),
               "name": card.get("property", {}).get("name")
                   or card.get("property", {}).get("title")
                   or card_type
                   or "job",
               "otherinfo": other_info,
               "jtoken": card.get("jtoken", ""),
               "mid": card.get("mid", ""),
               "enc": card.get("enc", ""),
               "aid": card.get("aid", ""),
               "objectid": card.get("objectId", "") or card.get("property", {}).get("objectid", ""),
               "playTime": card.get("playTime", 0),
               "rt": card.get("property", {}).get("rt", ""),
               "duration": card.get("property", {}).get("duration", 0),
               "attDuration": card.get("attDuration", ""),
               "attDurationEnc": card.get("attDurationEnc", ""),
               "videoFaceCaptureEnc": card.get("videoFaceCaptureEnc", ""),
           }
           if card_type == "workid":
               jobs.append(job)
               continue
           if card_type in {"video", "document", "read", "audio"}:
               jobs.append(job)
       return jobs, job_info

   def dispatch_job(self, course: dict, point: dict, job: dict, job_info: dict):
       job_type = job.get("type", "")
       self.iLog(f"Job start: {job_type} - {job.get('name', '')}")
       if job_type == "read":
           if self.study_read(course, job, job_info):
               self.summary["completed"] += 1
           else:
               self.summary["skipped"] += 1
           return
       if job_type == "document":
           if self.study_document(course, job, job_info):
               self.summary["completed"] += 1
           else:
               self.summary["skipped"] += 1
           return
       if job_type in {"video", "audio"}:
           if self.study_media(course, job, media_type=job_type):
               self.summary["completed"] += 1
           else:
               self.summary["failed"] += 1
           return
       if job_type == "workid":
           if self.study_work(course, job, job_info):
               self.summary["completed"] += 1
           else:
               self.summary["failed"] += 1
           return
       self.iLog(f"Unknown job type: {job_type}", 2)
       self.summary["unsupported"] += 1

   def study_read(self, course: dict, job: dict, job_info: dict) -> bool:
       with Http.Client(
           headers=self.User.ice.headers,
           cookies=self.User.cookie,
           proxies=self.User.ice.proxy,
           follow_redirects=True,
       ) as r:
           response = r.get(
               Api.Job_Read,
               params={
                   "jobid": job["jobid"],
                   "knowledgeid": job_info.get("knowledgeid", ""),
                   "jtoken": job.get("jtoken", ""),
                   "courseid": course["courseid"],
                   "clazzid": course["classid"],
               },
           )
       if response.status_code != 200:
           self.iLog(f"Read failed: {response.text}", 3)
           return False
       try:
           payload = response.json()
       except ValueError:
           self.iLog(f"Read result: {response.text}", 0)
           return False
       self.iLog(f"Read finished: {payload.get('msg', 'ok')}")
       return True

   def study_document(self, course: dict, job: dict, job_info: dict) -> bool:
       knowledge_match = re.search(r"nodeId_(.*?)-", job.get("otherinfo", ""))
       knowledgeid = knowledge_match.group(1) if knowledge_match else job_info.get("knowledgeid", "")
       with Http.Client(
           headers=self.User.ice.headers,
           cookies=self.User.cookie,
           proxies=self.User.ice.proxy,
           follow_redirects=True,
       ) as r:
           response = r.get(
               Api.Job_Document,
               params={
                   "jobid": job["jobid"],
                   "knowledgeid": knowledgeid,
                   "courseid": course["courseid"],
                   "clazzid": course["classid"],
                   "jtoken": job.get("jtoken", ""),
                   "_dc": int(time.time() * 1000),
               },
           )
       if response.status_code != 200:
           self.iLog(f"Document failed: {response.text}", 3)
           return False
       self.iLog(f"Document finished: {job.get('name', '')}")
       return True

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

   def parse_work_questions(self, html_text: str) -> dict:
       soup = BeautifulSoup(html_text, "html.parser")
       form = soup.find("form")
       if form is None:
           return {"fields": {}, "questions": []}
       fields = {}
       for node in form.find_all(["input", "textarea"]):
           name = node.get("name", "")
           if not name or name.startswith("answer") or name.startswith("answertype"):
               continue
           fields[name] = node.get("value", "") if node.name == "input" else node.get_text("", strip=False)
       questions = []
       for block in form.find_all("div", class_="singleQuesId"):
           qid = block.get("data", "")
           timu = block.find("div", class_="TiMu")
           qtype_code = timu.get("data", "") if timu else ""
           title_node = block.find("div", class_="Zy_TItle")
           title = title_node.get_text(" ", strip=True) if title_node else qid
           options = []
           for li in block.select("ul li"):
               text = li.get("aria-label") or li.get_text(" ", strip=True)
               text = re.sub(r"\s+", " ", text).strip()
               if text.endswith("选择"):
                   text = text[:-2].rstrip()
               if text:
                   options.append(text)
           questions.append(
               {
                   "id": qid,
                   "type_code": qtype_code,
                   "title": title,
                   "options": options,
               }
           )
       fields["answerwqbid"] = ",".join(q["id"] for q in questions if q["id"]) + ("," if questions else "")
       return {"fields": fields, "questions": questions}

   def tiku_work_answer(self, question: dict) -> tuple[str, str, str, str]:
       qid = question["id"]
       answer, answer_text, source = self.tiku.query(question)
       self.iLog(f"Tiku query[{source}]: {question.get('title', '')} -> {answer or '[empty]'}", 0 if source == "local" else 2)
       return f"answer{qid}", answer, answer_text, source

   def study_work(self, course: dict, job: dict, job_info: dict) -> bool:
       if not job.get("jobid"):
           self.iLog(f"Work job id missing: {job}", 2)
           return False
       params = {
           "api": "1",
           "workId": job["jobid"].replace("work-", ""),
           "jobid": job["jobid"],
           "originJobId": job["jobid"],
           "needRedirect": "true",
           "skipHeader": "true",
           "knowledgeid": str(job_info.get("knowledgeid", "")),
           "ktoken": job_info.get("ktoken", ""),
           "cpi": job_info.get("cpi") or course.get("cpi", ""),
           "ut": "s",
           "clazzId": course["classid"],
           "type": "",
           "enc": job.get("enc", ""),
           "mooc2": "1",
           "courseid": course["courseid"],
       }
       with Http.Client(
           headers=self.User.ice.headers,
           cookies=self.User.cookie,
           proxies=self.User.ice.proxy,
           follow_redirects=True,
       ) as client:
           response = client.get(Api.Work_Api, params=params)
           if response.status_code != 200:
               self.iLog(f"Work page failed: {response.status_code} {response.text[:200]}", 3)
               return False
           if "教师未创建完成该测验" in response.text:
               self.iLog(f"Work not ready, skip: {job.get('name', '')}", 2)
               return False
           parsed = self.parse_work_questions(response.text)
           questions = parsed["questions"]
           if not questions:
               self.iLog(f"Work has no questions or already finished: {job.get('name', '')}")
               return True
           fields = parsed["fields"]
           answered = []
           missing = []
           for question in questions:
               answer_name, answer, answer_text, source = self.tiku_work_answer(question)
               answer_type_name = f"answertype{question['id']}"
               if answer:
                   fields[answer_name] = answer
                   answered.append((question, answer, answer_text, source))
                   self.iLog(f"Work answer[{source}]: {question.get('title', '')} -> {answer}", 0)
               else:
                   fields[answer_name] = ""
                   missing.append(question)
                   self.iLog(f"Work answer not found, will save only: {question.get('title', '')}", 2)
               fields[answer_type_name] = question.get("type_code", "")
           total_questions = len(questions)
           answer_rate = 0 if total_questions == 0 else int(len(answered) * 100 / total_questions)
           should_submit = answer_rate >= 90 and not missing
           fields["pyFlag"] = "" if should_submit else "1"
           self.iLog(
               f"Work answer rate: {len(answered)}/{total_questions} ({answer_rate}%), "
               f"mode={'submit' if should_submit else 'save'}"
           )
           if self.collect_tiku:
               saved_count = 0
               for index, (question, answer, answer_text, source) in enumerate(answered, start=1):
                   if self.tiku.is_answer_shape_valid(question, answer):
                       self.tiku.save(question, answer, answer_text, source=f"collect-{source}")
                       saved_count += 1
                       self.iLog(
                           f"Collect progress: {index}/{len(answered)} saved={saved_count} | "
                           f"Q: {question.get('title', '')} | A: {answer} | source={source}"
                       )
                   else:
                       self.iLog(
                           f"Collect skipped invalid answer: {index}/{len(answered)} | "
                           f"Q: {question.get('title', '')} | A: {answer}",
                           2,
                       )
               self.iLog(
                   f"Work collected without submit: saved={saved_count}, answered={len(answered)}, missing={len(missing)}"
               )
               return True
           submit = client.post(Api.Work_Submit, data=fields, headers=self.get_work_headers())
       if submit.status_code != 200:
           self.iLog(f"Work submit failed: {submit.status_code} {submit.text[:200]}", 3)
           return False
       try:
           payload = submit.json()
       except ValueError:
           self.iLog(f"Work submit invalid: {submit.text[:200]}", 3)
           return False
       if payload.get("status"):
           saved_count = 0
           for index, (question, answer, answer_text, source) in enumerate(answered, start=1):
               if self.tiku.is_answer_shape_valid(question, answer):
                   self.tiku.save(question, answer, answer_text, source=source)
                   saved_count += 1
                   self.iLog(
                       f"Tiku saved: {index}/{len(answered)} saved={saved_count} | "
                       f"Q: {question.get('title', '')} | A: {answer} | source={source}"
                   )
           action = "submitted" if fields.get("pyFlag") == "" else "saved"
           self.iLog(f"Work {action}: {payload.get('msg', job.get('name', ''))}")
           return True
       self.iLog(f"Work submit rejected: {payload.get('msg', payload)}", 3)
       return False

   def study_empty_page(self, course: dict, point: dict) -> bool:
       with Http.Client(
           headers=self.User.ice.headers,
           cookies=self.User.cookie,
           proxies=self.User.ice.proxy,
           follow_redirects=True,
       ) as r:
           response = r.get(
               Api.Course_Empty,
               params={
                   "courseId": course["courseid"],
                   "clazzid": course["classid"],
                   "chapterId": point["id"],
                   "cpi": course["cpi"],
                   "verificationcode": "",
                   "mooc2": 1,
                   "microTopicId": 0,
                   "editorPreview": 0,
               },
           )
       if response.status_code != 200:
           self.iLog(f"Empty page failed: {point['title']}", 3)
           return False
       self.iLog(f"Empty page finished: {point['title']}")
       return True

   def get_uid(self) -> str:
       for key in ("_uid", "UID"):
           value = self.User.cookie.get(key)
           if value:
               return str(value)
       return ""

   def get_fid(self) -> str:
       return str(self.User.cookie.get("fid", ""))

   def get_media_headers(self, media_type: str) -> dict:
       headers = dict(self.User.ice.headers)
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

   def get_media_status(self, client, job: dict, media_type: str) -> Optional[dict]:
       response = client.get(
           f"{Api.Media_Status}{job['objectid']}",
           params={
               "k": self.get_fid(),
               "flag": "normal",
           },
           headers=self.get_media_headers(media_type),
       )
       if response.status_code != 200:
           self.iLog(f"Media status failed: {response.status_code}", 2)
           return None
       try:
           payload = response.json()
       except ValueError:
           self.iLog(f"Media status invalid: {response.text[:200]}", 2)
           return None
       if payload.get("status") != "success":
           self.iLog(f"Media status not ready: {payload}", 2)
           return None
       return payload

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

   def media_progress_log(
       self,
       client,
       course: dict,
       job: dict,
       status_payload: dict,
       duration: int,
       playing_time: int,
       media_type: str,
   ) -> tuple[bool, int]:
       userid = self.get_uid()
       if not userid:
           self.iLog("Cannot resolve UID for media log", 3)
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
           params.update({
               "rt": rt,
               "_t": int(time.time() * 1000),
           })
           response = client.get(
               f"{Api.Media_Log}{course['cpi']}/{status_payload['dtoken']}",
               params=params,
               headers=self.get_media_headers(media_type),
           )
       else:
           for current_rt in ("0.9", "1"):
               params.update({
                   "rt": current_rt,
                   "_t": int(time.time() * 1000),
               })
               response = client.get(
                   f"{Api.Media_Log}{course['cpi']}/{status_payload['dtoken']}",
                   params=params,
                   headers=self.get_media_headers(media_type),
               )
               if response.status_code == 200:
                   break
               if response.status_code != 403:
                   break

       if response is None:
           return False, 0
       if response.status_code != 200:
           self.iLog(f"Media log failed: {response.status_code} {response.text[:200]}", 2)
           return False, response.status_code
       try:
           payload = response.json()
       except ValueError:
           self.iLog(f"Media log invalid: {response.text[:200]}", 2)
           return False, 0
       return bool(payload.get("isPassed")), 200

   def study_media(self, course: dict, job: dict, media_type: str) -> bool:
       if not job.get("objectid"):
           self.iLog(f"Media object id missing: {job}", 2)
           return False
       with Http.Client(
           headers=self.User.ice.headers,
           cookies=self.User.cookie,
           proxies=self.User.ice.proxy,
           follow_redirects=True,
       ) as client:
           status_payload = self.get_media_status(client, job, media_type)
           if status_payload is None:
               return False
           duration = int(float(status_payload.get("duration") or job.get("duration") or 0))
           if duration <= 0:
               self.iLog(f"Media duration invalid: {job.get('name', '')}", 2)
               return False
           play_time = self.normalize_play_time(job.get("playTime", 0))
           if status_payload.get("isPassed"):
               self.iLog(f"Media already finished: {job.get('name', '')}")
               return True
           if status_payload.get("playingTime") is not None:
               play_time = max(play_time, self.normalize_play_time(status_payload.get("playingTime", 0)))
           self.iLog(f"Media start: {job.get('name', '')} {self.format_media_progress(play_time, duration)}")

           passed, state = self.media_progress_log(client, course, job, status_payload, duration, play_time, media_type)
           if passed:
               self.iLog(f"Media finished instantly: {job.get('name', '')}")
               return True
           if state == 403:
               return False

           passed, state = self.media_progress_log(client, course, job, status_payload, duration, duration, media_type)
           if passed:
               self.iLog(f"Media finished instantly: {job.get('name', '')}")
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
                   self.iLog(
                       f"Media progress: {job.get('name', '')} {self.format_media_progress(current, duration)}"
                   )
                   last_progress_output = now

               if current - last_reported >= wait_seconds or current == duration:
                   passed, state = self.media_progress_log(
                       client,
                       course,
                       job,
                       status_payload,
                       duration,
                       current,
                       media_type,
                   )
                   if passed:
                       self.iLog(f"Media finished: {job.get('name', '')}")
                       return True
                   if state == 403:
                       refreshed = self.get_media_status(client, job, media_type)
                       if refreshed is None:
                           return False
                       status_payload = refreshed
                       self.iLog(
                           f"Media status refreshed: {job.get('name', '')} {self.format_media_progress(current, duration)}",
                           2,
                       )
                   last_reported = current
                   wait_seconds = random.randint(30, 90)
               time.sleep(1)

           passed, _ = self.media_progress_log(client, course, job, status_payload, duration, duration, media_type)
           if passed:
               self.iLog(f"Media finished: {job.get('name', '')}")
               return True
       self.iLog(f"Media failed: {job.get('name', '')}", 2)
       return False
