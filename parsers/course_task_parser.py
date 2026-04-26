import json
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
        marker = "mArg ="
        alt_marker = "mArg="
        start = html_text.find(marker)
        if start < 0:
            start = html_text.find(alt_marker)
            if start < 0:
                return [], {}
        start = html_text.find("{", start)
        end = html_text.find("};", start)
        if start < 0 or end < 0:
            return [], {}
        try:
            cards_data = json.loads(html_text[start:end + 1])
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
            if card_type == "workid":
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

    def detect_source_kind(self, html_text: str, fields: dict, questions: list[dict]) -> str:
        soup = BeautifulSoup(html_text, "html.parser")
        visible_title = " ".join(
            node.get_text(" ", strip=True)
            for node in soup.select("h1,h2,h3,.mark_title,.ZyTop h3,.Cy_TItle,.work-title,.tit,.title")
        )
        field_text = " ".join(str(value) for value in fields.values())
        title_parts = [fields.get("workAnswerId", ""), fields.get("title", ""), visible_title, field_text, html_text[:3000]]
        content = "\n".join(str(part) for part in title_parts if part).lower()
        if any(keyword in content for keyword in ("章节测验", "章节测试", "课后", "chapter", "quiz", "练习")):
            return "chapter_quiz"
        if any(keyword in content for keyword in ("考试", "期中", "期末", "exam", "test")):
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
            title = self.clean_work_text(title_node.get_text(" ", strip=True) if title_node else "")
            if not title:
                title = self.clean_work_text(block.get_text(" ", strip=True))[:300] or qid
            options = []
            option_nodes = block.select("ul li") or block.select(".answerList li") or block.select("label")
            for li in option_nodes:
                text = li.get("aria-label") or li.get_text(" ", strip=True)
                text = self.clean_work_text(text)
                if text:
                    options.append(text)
            questions.append(
                {
                    "id": qid,
                    "type_code": str(qtype_code),
                    "title": title,
                    "options": options,
                }
            )
        source_kind = self.detect_source_kind(html_text, fields, questions)
        for question in questions:
            question["source_kind"] = source_kind
        fields["answerwqbid"] = ",".join(q["id"] for q in questions if q["id"]) + ("," if questions else "")
        return {"fields": fields, "questions": questions, "source_kind": source_kind}
