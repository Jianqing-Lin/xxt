import json
import re
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup


class CourseTaskParser:
    def parse_course_points(self, html_text: str) -> list[dict]:
        soup = BeautifulSoup(html_text, "html.parser")
        points = []
        for chapter_unit in soup.find_all("div", class_="chapter_unit"):
            for raw_point in chapter_unit.find_all("li"):
                point = raw_point.find("div")
                if point is None:
                    continue
                point_id = point.get("id", "")
                if not point_id.startswith("cur"):
                    continue
                point_value = point_id.replace("cur", "", 1)
                title_node = raw_point.select_one("a.clicktitle")
                title = title_node.get_text(strip=True) if title_node else point_value
                tips_node = raw_point.select_one("span.bntHoverTips")
                tips = tips_node.get_text(strip=True) if tips_node else ""
                count_node = raw_point.select_one("input.knowledgeJobCount")
                points.append(
                    {
                        "id": point_value,
                        "title": title,
                        "jobCount": count_node.get("value", "1") if count_node else "1",
                        "has_finished": "已完成" in tips,
                        "need_unlock": "解锁" in tips,
                    }
                )
        return points

    def parse_course_cards(self, html_text: str) -> tuple[list[dict], dict]:
        if "章节未开放" in html_text:
            return [], {"notOpen": True}
        cards_data = None
        for marker in ("mArg =", "mArg=", "window.AttachmentSetting =", "AttachmentSetting =", "attachments:"):
            start = html_text.find(marker)
            if start < 0:
                continue
            next_marker = html_text.find(marker, start + len(marker))
            if next_marker >= 0 and next_marker - start < 300:
                start = next_marker
            assignment = html_text.find("=", start, start + 80)
            if assignment >= 0:
                start = assignment + 1
            start = html_text.find("{", start)
            if start < 0:
                continue
            depth = 0
            in_string = False
            escape = False
            quote = ""
            end = -1
            for index in range(start, len(html_text)):
                char = html_text[index]
                if in_string:
                    if escape:
                        escape = False
                    elif char == "\\":
                        escape = True
                    elif char == quote:
                        in_string = False
                    continue
                if char == '"':
                    in_string = True
                    quote = char
                    continue
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        end = index + 1
                        break
            if end < 0:
                continue
            raw_json = html_text[start:end]
            try:
                cards_data = json.loads(raw_json)
                break
            except json.JSONDecodeError:
                try:
                    cards_data = json.loads(raw_json.replace("'", '"'))
                    break
                except json.JSONDecodeError:
                    continue
        if cards_data is None:
            return [], {}
        defaults = cards_data.get("defaults", {})
        job_info = {
            "ktoken": defaults.get("ktoken", ""),
            "cpi": defaults.get("cpi", ""),
            "knowledgeid": defaults.get("knowledgeid", ""),
        }
        jobs = []
        attachments = cards_data.get("attachments", []) or cards_data.get("jobList", []) or cards_data.get("cards", [])
        for card in attachments:
            # In collect mode callers filter non-work jobs later. Keep passed media
            # jobs parseable so study-mode diagnostics and interface checks can see them.
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
                "name": card.get("property", {}).get("name") or card.get("property", {}).get("title") or card_type or "job",
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
            if card_type in {"workid", "work", "quiz", "test"} or job.get("jobid", "").startswith("work-"):
                job["type"] = "workid"
                jobs.append(job)
                continue
            if card_type in {"video", "document", "read", "audio"}:
                jobs.append(job)
        return jobs, job_info

    def dedupe_jobs(self, jobs: list[dict]) -> list[dict]:
        unique_jobs = []
        seen_jobids = set()
        for job in jobs:
            jobid = job.get("jobid") or job.get("mid") or f"{job.get('type')}:{job.get('name')}"
            if jobid in seen_jobids:
                continue
            seen_jobids.add(jobid)
            unique_jobs.append(job)
        return unique_jobs

    def clean_work_text(self, value: str) -> str:
        value = " ".join(str(value or "").split()).strip()
        return value[:-2].rstrip() if value.endswith("选择") else value

    def parse_review_score(self, value: str):
        value = self.clean_work_text(value)
        if not value:
            return None
        matched = re.search(r"-?\d+(?:\.\d+)?", value)
        if not matched:
            return None
        try:
            return float(matched.group(0))
        except ValueError:
            return None

    def detect_source_kind(self, html_text: str, fields: dict, questions: list[dict]) -> str:
        soup = BeautifulSoup(html_text, "html.parser")
        visible_title = " ".join(
            node.get_text(" ", strip=True)
            for node in soup.select("h1,h2,h3,.mark_title,.ZyTop h3,.Cy_TItle,.work-title,.tit,.title,.TestTitle_name,.newTestType,.ceyan_name")
        )
        field_text = " ".join(str(value) for value in fields.values())
        text_excerpt = " ".join(soup.get_text(" ", strip=True).split())[:6000]
        title_parts = [fields.get("workAnswerId", ""), fields.get("title", ""), visible_title, field_text, text_excerpt]
        content = "\n".join(str(part) for part in title_parts if part).lower()
        if any(keyword in content for keyword in ("章节测验", "章节测试", "课后", "chapter", "quiz", "练习")):
            return "chapter_quiz"
        if any(keyword in content for keyword in ("考试", "期中", "期末", "exam")):
            return "exam"
        if questions:
            return "homework"
        return "unknown"

    def parse_work_questions(self, html_text: str) -> dict:
        soup = BeautifulSoup(html_text, "html.parser")
        form = soup.find("form")
        if form is None:
            return {"fields": {}, "questions": [], "source_kind": "unknown"}
        fields = {}
        for node in form.find_all(["input", "textarea"]):
            name = node.get("name", "")
            if not name or name.startswith("answer") or name.startswith("answertype"):
                continue
            fields[name] = node.get("value", "") if node.name == "input" else node.get_text("", strip=False)
        questions = []
        blocks = form.find_all("div", class_="singleQuesId")
        if not blocks:
            blocks = soup.find_all("div", class_="singleQuesId")
        if not blocks:
            blocks = form.select("div[data]")
        for index, block in enumerate(blocks, start=1):
            qid = block.get("data") or block.get("data-id") or block.get("id") or str(index)
            timu = block.find("div", class_="TiMu") or block.select_one("[data-type]")
            qtype_code = ""
            if timu is not None:
                qtype_code = timu.get("data") or timu.get("data-type") or ""
            if not qtype_code:
                type_input = block.select_one("input[name^=answertype]")
                qtype_code = type_input.get("value", "") if type_input else ""
            title_node = block.find("div", class_="Zy_TItle") or block.find("div", class_="clearfix") or block.find("h3") or block.find("p")
            title_text = title_node.get_text(" ", strip=True) if title_node else ""
            if not qtype_code:
                if "多选题" in title_text:
                    qtype_code = "1"
                elif "判断题" in title_text:
                    qtype_code = "3"
                elif "单选题" in title_text:
                    qtype_code = "0"
                elif "填空题" in title_text:
                    qtype_code = "2"
                elif "简答题" in title_text or "问答题" in title_text:
                    qtype_code = "4"
            title = self.clean_work_text(title_text)
            if not title:
                title = self.clean_work_text(block.get_text(" ", strip=True))[:300] or qid
            options = []
            option_nodes = block.select("ul li") or block.select(".answerList li") or block.select("label")
            for li in option_nodes:
                text = li.get("aria-label") or li.get_text(" ", strip=True)
                text = self.clean_work_text(text)
                if text:
                    options.append(text)
            review_box = block.select_one(".newAnswerBx")
            my_answer_text = ""
            is_correct = None
            score = None
            if review_box is not None:
                answer_node = review_box.select_one(".answerCon")
                if answer_node is not None:
                    my_answer_text = self.clean_work_text(answer_node.get_text(" ", strip=True))
                if review_box.select_one(".marking_dui") is not None:
                    is_correct = True
                elif review_box.select_one("[class*='marking_']") is not None:
                    is_correct = False
                score_node = review_box.select_one(".scoreNum")
                if score_node is not None:
                    score = self.parse_review_score(score_node.get_text(" ", strip=True))
            questions.append(
                {
                    "id": qid,
                    "type_code": str(qtype_code),
                    "title": title,
                    "options": options,
                    "my_answer_text": my_answer_text,
                    "is_correct": is_correct,
                    "score": score,
                }
            )
        source_kind = self.detect_source_kind(html_text, fields, questions)
        for question in questions:
            question["source_kind"] = source_kind
        fields["answerwqbid"] = ",".join(q["id"] for q in questions if q["id"]) + ("," if questions else "")
        return {"fields": fields, "questions": questions, "source_kind": source_kind}
