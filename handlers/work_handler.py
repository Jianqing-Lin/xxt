import os
import re
import time

from bs4 import BeautifulSoup


class WorkHandler:
    def __init__(self, task_client, tiku, parser, logger, collect_tiku: bool, headers_provider, collect_sources=None):
        self.task_client = task_client
        self.tiku = tiku
        self.parser = parser
        self.log = logger
        self.collect_tiku = collect_tiku
        self.headers_provider = headers_provider
        self.collect_sources = set(collect_sources or {"chapter_quiz", "homework", "exam", "unknown"})

    def save_work_debug_html(self, html_text: str, job: dict) -> str:
        os.makedirs("debug", exist_ok=True)
        safe_jobid = re.sub(r"[^A-Za-z0-9_.-]+", "_", job.get("jobid", "work"))
        path = os.path.join("debug", f"work_{safe_jobid}_{int(time.time())}.html")
        with open(path, "w", encoding="utf-8") as writer:
            writer.write(html_text)
        return path

    def get_work_page_headers(self, course: dict, knowledgeid: str) -> dict:
        headers = dict(self.headers_provider())
        headers.update(
            {
                "Host": "mooc1.chaoxing.com",
                "Referer": (
                    "https://mooc1.chaoxing.com/mooc-ans/knowledge/cards?"
                    f"clazzid={course['classid']}&courseid={course['courseid']}&knowledgeid={knowledgeid}"
                    f"&ut=s&cpi={course.get('cpi', '')}&v=2025-0424-1038-3&mooc2=1"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Upgrade-Insecure-Requests": "1",
            }
        )
        headers.pop("X-Requested-With", None)
        headers.pop("Content-Type", None)
        return headers

    def infer_source_kind(self, parsed_source: str, job: dict, html_text: str) -> str:
        soup = BeautifulSoup(html_text, "html.parser")
        text_excerpt = " ".join(soup.get_text(" ", strip=True).split())[:6000]
        hints = "\n".join(
            str(part or "")
            for part in (
                parsed_source,
                job.get("name", ""),
                job.get("jobid", ""),
                job.get("otherinfo", ""),
                text_excerpt,
            )
        ).lower()
        if any(keyword in hints for keyword in ("章节测验", "章节测试", "课后", "chapter", "quiz", "练习")):
            return "chapter_quiz"
        if any(keyword in hints for keyword in ("考试", "期中", "期末", "exam")):
            return "exam"
        if any(keyword in hints for keyword in ("作业", "homework", "work")):
            return "homework"
        return parsed_source or "unknown"

    def tiku_work_answer(self, question: dict) -> tuple[str, str, str, str]:
        qid = question["id"]
        answer, answer_text, source = self.tiku.query(question)
        self.log(
            f"Tiku query[{source}][{question.get('source_kind', 'unknown')}/{question.get('type_code', '')}]: "
            f"{question.get('title', '')} -> {answer or '[empty]'}",
            0 if source == "local" else 2,
        )
        return f"answer{qid}", answer, answer_text, source

    def page_review_work_answer(self, question: dict) -> tuple[str, str, str]:
        if not self.collect_tiku:
            return "", "", ""
        if not hasattr(self.tiku, "answer_from_page_review"):
            return "", "", "page-review:unsupported"
        answer, answer_text, source = self.tiku.answer_from_page_review(question)
        if answer and self.tiku.is_answer_shape_valid(question, answer):
            self.log(
                f"Collect answer source=page-review[{question.get('source_kind', 'unknown')}/{question.get('type_code', '')}]: "
                f"{question.get('title', '')} -> {answer}",
                0,
            )
            return answer, answer_text, "page-review"
        return "", answer_text, source

    def _record_collect_metadata(self, questions: list[dict], answered: list[tuple], missing: list[dict]):
        answered_by_hash = {self.tiku.question_hash(question): (question, answer, answer_text, source) for question, answer, answer_text, source in answered}
        for question in questions:
            qhash = self.tiku.question_hash(question)
            if qhash in answered_by_hash:
                continue
            self.tiku.save_missing(question, reason="collect:no-answer", source="collect")
        for question in missing:
            self.tiku.save_missing(question, reason="collect:missing", source="collect")

    def handle(self, course: dict, job: dict, job_info: dict) -> bool:
        if not job.get("jobid"):
            self.log(f"Work job id missing: {job}", 2)
            return False
        work_id = job["jobid"].replace("work-", "")
        knowledgeid = str(job_info.get("knowledgeid", ""))
        params = {
            "api": "1",
            "workId": work_id,
            "jobid": job["jobid"],
            "originJobId": job["jobid"],
            "needRedirect": "true",
            "skipHeader": "true",
            "knowledgeid": knowledgeid,
            "ktoken": job_info.get("ktoken", ""),
            "cpi": job_info.get("cpi") or course.get("cpi", ""),
            "ut": "s",
            "clazzId": course["classid"],
            "classId": course["classid"],
            "type": "",
            "enc": job.get("enc", ""),
            "mooc2": "1",
            "courseid": course["courseid"],
            "courseId": course["courseid"],
        }
        try:
            response = self.task_client.get_work_page(params, self.get_work_page_headers(course, knowledgeid))
        except TypeError:
            response = self.task_client.get_work_page(params)
        if response.status_code != 200:
            self.log(f"Work page failed: {response.status_code} {response.text[:200]}", 3)
            return False
        if "教师未创建完成该测验" in response.text:
            self.log(f"Work not ready, skip: {job.get('name', '')}", 2)
            return False
        parsed = self.parser.parse_work_questions(response.text)
        questions = parsed["questions"]
        parsed_source_kind = parsed.get("source_kind", "unknown")
        source_kind = self.infer_source_kind(parsed_source_kind, job, response.text)
        for question in questions:
            question["source_kind"] = source_kind
        self.log(
            f"Work parsed questions: {len(questions)} - {job.get('name', '')} | "
            f"source_kind={source_kind} parsed={parsed_source_kind}"
        )
        if self.collect_tiku and self.collect_sources and source_kind not in self.collect_sources:
            self.log(f"Collect source skipped: {source_kind} not in {sorted(self.collect_sources)} - {job.get('name', '')}", 2)
            return True
        for index, question in enumerate(questions, start=1):
            self.log(
                f"Work question[{index}/{len(questions)}]: id={question.get('id', '')} "
                f"source_kind={question.get('source_kind', 'unknown')} "
                f"type={question.get('type_code', '')} title={question.get('title', '')} "
                f"options={question.get('options', [])}"
            )
        if not questions:
            debug_path = self.save_work_debug_html(response.text, job)
            self.log(f"Work has no questions or already finished: {job.get('name', '')}")
            self.log(f"Work html preview: {response.text[:500]}", 0)
            self.log(f"Work debug html saved: {debug_path}", 2)
            return True
        fields = parsed["fields"]
        answered = []
        missing = []
        for question in questions:
            answer_name, answer, answer_text, source = self.tiku_work_answer(question)
            answer_type_name = f"answertype{question['id']}"
            if not answer:
                review_answer, review_answer_text, review_source = self.page_review_work_answer(question)
                if review_answer:
                    answer, answer_text, source = review_answer, review_answer_text, review_source
            if answer:
                fields[answer_name] = answer
                answered.append((question, answer, answer_text, source))
                self.log(
                    f"Work answer[{source}][{question.get('source_kind', 'unknown')}/{question.get('type_code', '')}]: "
                    f"{question.get('title', '')} -> {answer}",
                    0,
                )
            else:
                fields[answer_name] = ""
                missing.append(question)
                reason = source or "unknown"
                self.tiku.save_missing(question, reason=reason, source="collect" if self.collect_tiku else "study")
                self.log(
                    f"Work answer not found[{question.get('source_kind', 'unknown')}/{question.get('type_code', '')}], "
                    f"will save only: {question.get('title', '')}; reason={reason}",
                    2,
                )
            fields[answer_type_name] = question.get("type_code", "")
        total_questions = len(questions)
        answer_rate = 0 if total_questions == 0 else int(len(answered) * 100 / total_questions)
        should_submit = answer_rate >= 90 and not missing
        fields["pyFlag"] = "" if should_submit else "1"
        self.log(
            f"Work answer rate: {len(answered)}/{total_questions} ({answer_rate}%), "
            f"mode={'submit' if should_submit else 'save'}, source_kind={source_kind}"
        )
        if self.collect_tiku:
            saved_count = 0
            invalid_count = 0
            for index, (question, answer, answer_text, source) in enumerate(answered, start=1):
                if self.tiku.is_answer_shape_valid(question, answer):
                    self.tiku.save(question, answer, answer_text, source=f"collect-{source}")
                    saved_count += 1
                    self.log(
                        f"Collect progress: {index}/{len(answered)} saved={saved_count} | "
                        f"Q: {question.get('title', '')} | source_kind={question.get('source_kind', 'unknown')} "
                        f"| type={question.get('type_code', '')} | A: {answer} | source={source}"
                    )
                else:
                    invalid_count += 1
                    self.tiku.save_missing(question, reason="collect:invalid-answer-shape", source="collect")
                    self.log(
                        f"Collect skipped invalid answer: {index}/{len(answered)} | "
                        f"Q: {question.get('title', '')} | source_kind={question.get('source_kind', 'unknown')} "
                        f"| type={question.get('type_code', '')} | A: {answer}",
                        2,
                    )
            self._record_collect_metadata(questions, answered, missing)
            self.log(
                f"Work collected without submit: saved={saved_count}, answered={len(answered)}, "
                f"missing={len(missing)}, invalid={invalid_count}, total={total_questions}, "
                f"source_kind={source_kind}, last_error={self.tiku.last_error or 'none'}"
            )
            return True
        submit = self.task_client.submit_work(fields, self.headers_provider())
        if submit.status_code != 200:
            self.log(f"Work submit failed: {submit.status_code} {submit.text[:200]}", 3)
            return False
        try:
            payload = submit.json()
        except ValueError:
            self.log(f"Work submit invalid: {submit.text[:200]}", 3)
            return False
        if payload.get("status"):
            saved_count = 0
            for index, (question, answer, answer_text, source) in enumerate(answered, start=1):
                if self.tiku.is_answer_shape_valid(question, answer):
                    self.tiku.save(question, answer, answer_text, source=source)
                    saved_count += 1
                    self.log(
                        f"Tiku saved: {index}/{len(answered)} saved={saved_count} | "
                        f"Q: {question.get('title', '')} | source_kind={question.get('source_kind', 'unknown')} "
                        f"| type={question.get('type_code', '')} | A: {answer} | source={source}"
                    )
            action = "submitted" if fields.get("pyFlag") == "" else "saved"
            self.log(f"Work {action}: {payload.get('msg', job.get('name', ''))}")
            return True
        self.log(f"Work submit rejected: {payload.get('msg', payload)}", 3)
        return False
