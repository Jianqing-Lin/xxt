import json
import uuid
import unittest
from unittest.mock import patch

from adapters.tiku_adapter_client import TikuAdapterClient
from app.runtime import RuntimeContext
from auth.cookie_store import CookieStore
from clients.session import SessionFactory
from courses.course_repository import CourseRepository
from handlers.work_handler import WorkHandler
from local_tiku_adapter import build_adapter_answer_payload, select_best_candidate
from model.tiku import TikuStore
from parsers.course_parser import CourseParser
from parsers.course_task_parser import CourseTaskParser
from repositories.tiku_repository import TikuRepository
from services.tiku_service import TikuService
from workflow.course_workflow import CourseWorkflow
from workflow.course_study_workflow import CourseStudyWorkflow
from workflow.job_dispatcher import JobDispatcher


class DummyClient:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class DummySessionFactory:
    def __init__(self):
        self.client = DummyClient()

    def get_shared_client(self):
        return self.client

    def close(self):
        self.client.close()


class DummyRepository:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True

    def fetch_course_page(self, course):
        return {
            **course,
            "html": "<html></html>",
            "status_code": 200,
        }


class DummyTiku:
    def __init__(self, answers=None):
        self.answers = answers or {}
        self.saved = []
        self.missed = []
        self.last_error = ""

    def query(self, question):
        return self.answers.get(question["id"], ("", "", "none:dummy"))

    def is_answer_shape_valid(self, question, answer):
        return bool(answer)

    def save(self, question, answer, answer_text="", source="manual"):
        self.saved.append((question["id"], question.get("source_kind", "unknown"), answer, answer_text, source))

    def save_missing(self, question, reason="", source="miss"):
        self.missed.append((question["id"], question.get("source_kind", "unknown"), reason, source))

    def question_hash(self, question):
        return f"hash-{question['source_kind']}-{question['id']}"


class DummyTaskClientForWork:
    def __init__(self, html, submit_payload=None):
        self.html = html
        self.submit_payload = submit_payload or {"status": True, "msg": "ok"}

    class Response:
        def __init__(self, status_code, text, payload=None):
            self.status_code = status_code
            self.text = text
            self._payload = payload

        def json(self):
            if self._payload is None:
                raise ValueError("no json")
            return self._payload

    def get_work_page(self, params):
        return self.Response(200, self.html)

    def submit_work(self, fields, headers):
        return self.Response(200, json.dumps(self.submit_payload, ensure_ascii=False), self.submit_payload)


class SmokeAssemblyTest(unittest.TestCase):
    def test_runtime_context_basic_flow(self):
        runtime = RuntimeContext(version="test", headers={"User-Agent": "ua"})
        self.assertEqual(runtime.version, "test")
        self.assertEqual(runtime.normalize_speed("2"), 2.0)
        self.assertEqual(runtime.normalize_speed("100"), 16.0)

    def test_cookie_store_roundtrip(self):
        store = CookieStore("config/test_cookies_smoke.json")
        payload = {"u": {"token": "v"}}
        written = store.write_all(payload)
        self.assertEqual(written, payload)
        self.assertEqual(store.read_all(), payload)

    def test_session_factory_shared_client_reuse(self):
        factory = SessionFactory(headers={"User-Agent": "ua"}, cookies={"k": "v"})
        client1 = factory.get_shared_client()
        client2 = factory.get_shared_client()
        self.assertIs(client1, client2)
        factory.close()

    def test_course_parser_html(self):
        parser = CourseParser()
        html = """
        <div class='course'>
          <a href='https://example.test?cpi=999'></a>
          <input class='clazzId' value='class-1' />
          <input class='courseId' value='course-1' />
          <span class='course-name' title='课程A'></span>
          <p class='color3'>教师A</p>
        </div>
        <div class='course'>
          <div class='not-open-tip'></div>
        </div>
        """
        parsed = parser.parse_course_list(html)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["classid"], "class-1")
        self.assertEqual(parsed[0]["courseid"], "course-1")
        self.assertEqual(parsed[0]["cpi"], "999")
        self.assertEqual(parsed[0]["name"], "课程A")
        self.assertEqual(parsed[0]["teacher"], "教师A")

    def test_course_parser_json(self):
        parser = CourseParser()
        payload = {
            "channelList": [
                {
                    "key": "class-json",
                    "cpi": "cpi-json",
                    "content": {
                        "course": {
                            "data": [
                                {
                                    "id": "course-json",
                                    "name": "课程JSON",
                                    "teacherfactor": "教师JSON",
                                }
                            ]
                        }
                    },
                }
            ]
        }
        parsed = parser.parse_course_list(json.dumps(payload, ensure_ascii=False))
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["classid"], "class-json")
        self.assertEqual(parsed[0]["courseid"], "course-json")
        self.assertEqual(parsed[0]["cpi"], "cpi-json")

    def test_course_task_parser_points(self):
        parser = CourseTaskParser()
        html = """
        <div class='chapter_unit'>
          <li>
            <div id='cur101'></div>
            <a class='clicktitle'>第一章</a>
            <span class='bntHoverTips'>已完成</span>
            <input class='knowledgeJobCount' value='3' />
          </li>
          <li>
            <div id='cur202'></div>
            <a class='clicktitle'>第二章</a>
            <span class='bntHoverTips'>待解锁</span>
          </li>
        </div>
        """
        points = parser.parse_course_points(html)
        self.assertEqual(len(points), 2)
        self.assertEqual(points[0]["id"], "101")
        self.assertTrue(points[0]["has_finished"])
        self.assertEqual(points[0]["jobCount"], "3")
        self.assertTrue(points[1]["need_unlock"])

    def test_course_task_parser_cards_and_dedupe(self):
        parser = CourseTaskParser()
        html = """
        <script>
        mArg = {
          "defaults": {"ktoken": "kt", "cpi": "cpix", "knowledgeid": "kid"},
          "attachments": [
            {
              "type": "read",
              "job": null,
              "jobid": "read-1",
              "jtoken": "jt-read",
              "property": {"title": "阅读任务", "read": false}
            },
            {
              "type": "video",
              "jobid": "video-1",
              "property": {"name": "视频任务", "objectid": "obj-1", "rt": "1", "duration": 120},
              "objectId": "obj-1",
              "otherInfo": "nodeId_1-foo&bar",
              "playTime": 10,
              "attDuration": "120",
              "attDurationEnc": "enc-a",
              "videoFaceCaptureEnc": "enc-v"
            },
            {
              "type": "video",
              "jobid": "video-1",
              "property": {"name": "视频任务", "objectid": "obj-1", "rt": "1", "duration": 120},
              "objectId": "obj-1"
            },
            {
              "type": "workid",
              "jobid": "work-1",
              "enc": "enc-work",
              "property": {"name": "作业任务"}
            }
          ]
        };
        </script>
        """
        jobs, info = parser.parse_course_cards(html)
        self.assertEqual(info["ktoken"], "kt")
        self.assertEqual(info["knowledgeid"], "kid")
        self.assertEqual(len(jobs), 4)
        deduped = parser.dedupe_jobs(jobs)
        self.assertEqual(len(deduped), 3)
        self.assertEqual(deduped[0]["type"], "read")
        self.assertEqual(deduped[1]["type"], "video")
        self.assertEqual(deduped[2]["type"], "workid")

    def test_course_task_parser_work_questions(self):
        parser = CourseTaskParser()
        html = """
        <form>
          <input name='courseId' value='course-1' />
          <input name='title' value='课后练习第一章' />
          <div class='singleQuesId' data='101'>
            <div class='TiMu' data='0'></div>
            <div class='Zy_TItle'>1. 题目一 选择</div>
            <ul>
              <li>A. 选项A</li>
              <li>B. 选项B</li>
            </ul>
          </div>
          <div class='singleQuesId' data='202'>
            <input name='answertype202' value='3' />
            <div class='clearfix'>2. 判断题</div>
            <label>正确</label>
            <label>错误</label>
          </div>
        </form>
        """
        parsed = parser.parse_work_questions(html)
        self.assertEqual(parsed["fields"]["courseId"], "course-1")
        self.assertEqual(parsed["fields"]["answerwqbid"], "101,202,")
        self.assertEqual(parsed["source_kind"], "chapter_quiz")
        self.assertEqual(len(parsed["questions"]), 2)
        self.assertEqual(parsed["questions"][0]["type_code"], "0")
        self.assertEqual(parsed["questions"][0]["title"], "1. 题目一")
        self.assertEqual(parsed["questions"][0]["options"], ["A. 选项A", "B. 选项B"])
        self.assertEqual(parsed["questions"][0]["source_kind"], "chapter_quiz")
        self.assertEqual(parsed["questions"][1]["type_code"], "3")

    def test_course_task_parser_work_review_fields(self):
        parser = CourseTaskParser()
        html = """
        <form>
          <input name='title' value='章节测验第一章' />
          <div class='singleQuesId' data='101'>
            <div class='Zy_TItle'><span class='newZy_TItle'>【判断题】</span>宋太祖灭北汉后成功收复了燕云十六州。</div>
            <div class='newAnswerBx'>
              <div class='answerCon'>错</div>
              <span class='marking_dui'></span>
              <span class='scoreNum'>100.0</span>
            </div>
          </div>
        </form>
        """
        parsed = parser.parse_work_questions(html)
        question = parsed["questions"][0]
        self.assertEqual(question["my_answer_text"], "错")
        self.assertTrue(question["is_correct"])
        self.assertEqual(question["score"], 100.0)

    def test_course_task_parser_detects_chapter_quiz_from_review_page_text(self):
        parser = CourseTaskParser()
        html = """
        <html>
          <head><title>查看已批阅作业</title></head>
          <body>
            <form>
            <div class='newTestTitle'><div class='TestTitle_name'>章节测验</div></div>
            <div class='ceyan_name'><h3>第三章</h3></div>
            <div class='singleQuesId' data='101'>
              <div class='Zy_TItle'><span class='newZy_TItle'>【单选题】</span>测试题</div>
              <ul><li>A. 甲</li><li>B. 乙</li></ul>
            </div>
            </form>
          </body>
        </html>
        """
        parsed = parser.parse_work_questions(html)
        self.assertEqual(parsed["source_kind"], "chapter_quiz")

    def test_course_task_parser_not_open(self):
        parser = CourseTaskParser()
        jobs, info = parser.parse_course_cards("章节未开放")
        self.assertEqual(jobs, [])
        self.assertTrue(info["notOpen"])

    def test_tiku_store_construct_with_temp_db(self):
        tiku = TikuStore(db_path="test_smoke_tiku.db", adapter_url="", use="", tokens={})
        stats = tiku.stats()
        self.assertIn("work_answers", stats)
        self.assertIn("work_answer_misses", stats)

    def test_tiku_service_match_adapter_answer_compatible_fields(self):
        service = TikuService(db_path="test_smoke_tiku_service.db", adapter_url="", use="", tokens={})
        question = {
            "id": "1",
            "type_code": "0",
            "title": "测试题",
            "options": ["A. 选项A", "B. 选项B"],
            "source_kind": "chapter_quiz",
        }
        payload = {
            "data": {
                "answer": {
                    "answerkey": "A",
                    "answercontent": "选项A",
                }
            }
        }
        answer, answer_text = service.match_adapter_answer(question, payload)
        self.assertEqual(answer, "A")
        self.assertIn("选项A", answer_text)

    def test_tiku_service_question_hash_includes_source_kind(self):
        service = TikuService(db_path="test_smoke_tiku_service_hash.db", adapter_url="", use="", tokens={})
        q1 = {"id": "1", "title": "同题", "options": ["A. 甲"], "type_code": "0", "source_kind": "exam"}
        q2 = {"id": "1", "title": "同题", "options": ["A. 甲"], "type_code": "0", "source_kind": "homework"}
        self.assertNotEqual(service.question_hash(q1), service.question_hash(q2))

    def test_tiku_service_answer_from_page_review(self):
        service = TikuService(db_path="test_smoke_tiku_service_review.db", adapter_url="", use="", tokens={})
        single = {
            "id": "1",
            "type_code": "0",
            "title": "单选题",
            "options": ["A. 甲", "B. 乙", "C. 丙", "D. 丁"],
            "source_kind": "chapter_quiz",
            "my_answer_text": "D",
            "is_correct": True,
        }
        judgement = {
            "id": "2",
            "type_code": "3",
            "title": "判断题",
            "options": [],
            "source_kind": "chapter_quiz",
            "my_answer_text": "错",
            "is_correct": True,
        }
        answer1, _, source1 = service.answer_from_page_review(single)
        answer2, _, source2 = service.answer_from_page_review(judgement)
        self.assertEqual(answer1, "D")
        self.assertEqual(answer2, "false")
        self.assertEqual(source1, "page-review")
        self.assertEqual(source2, "page-review")

    def test_tiku_adapter_client_reference_protocol_payload(self):
        client = TikuAdapterClient("https://example.test/query", use="TikuAdapter", tokens={"token": "abc"})

        class DummyHttpClient:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def post(self, url, json=None, params=None):
                self.url = url
                self.json = json
                self.params = params
                class Resp:
                    status_code = 200
                    def json(self_inner):
                        return {"ok": True, "payload": json}
                return Resp()

        with patch("adapters.tiku_adapter_client.Http.Client", return_value=DummyHttpClient()):
            payload = {"question": "题目", "type": 0, "options": ["A", "B"]}
            result = client.query(payload)
            self.assertTrue(result["ok"])
            self.assertEqual(result["payload"]["question"], "题目")
            self.assertEqual(result["payload"]["provider"], "TikuAdapter")
            self.assertEqual(result["payload"]["token"], "abc")

    def test_local_tiku_adapter_build_choice_payload(self):
        payload = build_adapter_answer_payload(
            {
                "type_code": "1",
                "answer": "BD",
                "answer_text": "B. 第二项#D. 第四项",
            }
        )
        self.assertEqual(payload["answerKey"], ["B", "D"])
        self.assertIn("第四项", payload["answercontent"])

    def test_local_tiku_adapter_build_judgement_payload(self):
        payload = build_adapter_answer_payload(
            {
                "type_code": "3",
                "answer": "true",
                "answer_text": "",
            }
        )
        self.assertEqual(payload["content"], "正确")

    def test_local_tiku_adapter_selects_exact_option_match(self):
        selected = select_best_candidate(
            [
                {"id": 1, "options_norm_json": json.dumps(["甲", "乙"], ensure_ascii=False), "correct_count": 9, "updated_at": 10},
                {"id": 2, "options_norm_json": json.dumps(["甲", "丙"], ensure_ascii=False), "correct_count": 99, "updated_at": 99},
            ],
            ["甲", "乙"],
        )
        self.assertEqual(selected["id"], 1)

    def test_tiku_repository_count_answers(self):
        repository = TikuRepository("test_smoke_tiku_repo_count.db")
        repository.init_db()
        self.assertEqual(repository.count_answers(), 0)

    def test_work_handler_collect_mode_records_metadata(self):
        html = """
        <form>
          <input name='courseId' value='course-1' />
          <input name='title' value='章节测验第一章' />
          <div class='singleQuesId' data='101'>
            <div class='TiMu' data='0'></div>
            <div class='Zy_TItle'>1. 单选题 选择</div>
            <ul><li>A. 选项A</li><li>B. 选项B</li></ul>
          </div>
          <div class='singleQuesId' data='202'>
            <div class='TiMu' data='0'></div>
            <div class='Zy_TItle'>2. 单选题 选择</div>
            <ul><li>A. 选项A</li><li>B. 选项B</li></ul>
          </div>
        </form>
        """
        handler = WorkHandler(
            task_client=DummyTaskClientForWork(html),
            tiku=DummyTiku({"101": ("A", "选项A", "adapter")}),
            parser=CourseTaskParser(),
            logger=lambda *args, **kwargs: None,
            collect_tiku=True,
            headers_provider=lambda: {},
        )
        result = handler.handle(
            course={"classid": "c1", "courseid": "c2", "cpi": "c3"},
            job={"jobid": "work-1", "name": "作业", "enc": "enc"},
            job_info={"knowledgeid": "kid", "ktoken": "kt", "cpi": "c3"},
        )
        self.assertTrue(result)
        self.assertEqual(len(handler.tiku.saved), 1)
        self.assertEqual(handler.tiku.saved[0][1], "chapter_quiz")
        self.assertGreaterEqual(len(handler.tiku.missed), 1)

    def test_work_handler_collect_mode_fallback_to_page_review(self):
        html = """
        <form>
          <input name='title' value='章节测验第一章' />
          <div class='singleQuesId' data='101'>
            <div class='Zy_TItle'><span class='newZy_TItle'>【单选题】</span>测试题</div>
            <ul><li>A. 甲</li><li>B. 乙</li><li>C. 丙</li><li>D. 丁</li></ul>
            <div class='newAnswerBx'>
              <div class='answerCon'>D</div>
              <span class='marking_dui'></span>
              <span class='scoreNum'>100.0</span>
            </div>
          </div>
        </form>
        """
        db_path = f"test_smoke_tiku_handler_review_{uuid.uuid4().hex}.db"
        handler = WorkHandler(
            task_client=DummyTaskClientForWork(html),
            tiku=TikuService(db_path=db_path, adapter_url="", use="", tokens={}),
            parser=CourseTaskParser(),
            logger=lambda *args, **kwargs: None,
            collect_tiku=True,
            headers_provider=lambda: {},
        )
        result = handler.handle(
            course={"classid": "c1", "courseid": "c2", "cpi": "c3"},
            job={"jobid": "work-1", "name": "章节测验", "enc": "enc"},
            job_info={"knowledgeid": "kid", "ktoken": "kt", "cpi": "c3"},
        )
        self.assertTrue(result)
        stored = handler.tiku.get_local({"id": "101", "title": "【单选题】 测试题", "options": ["A. 甲", "B. 乙", "C. 丙", "D. 丁"], "type_code": "0", "source_kind": "chapter_quiz"})
        self.assertIsNotNone(stored)
        self.assertEqual(stored["answer"], "D")

    def test_course_study_workflow_collect_keeps_non_empty_job_info(self):
        parser = CourseTaskParser()

        class DummyTaskClient:
            class Response:
                def __init__(self, status_code, text, headers=None):
                    self.status_code = status_code
                    self.text = text
                    self.headers = headers or {"content-type": "text/html;charset=UTF-8"}

                def json(self):
                    raise ValueError("not json")

            def get_chapter_info(self, classid, courseid):
                return self.Response(403, "<html>403</html>")

            def get_job_cards(self, params, num):
                responses = {
                    "0": """
                    <script>
                    mArg = {
                      "defaults": {"ktoken": "kt-live", "cpi": "cpi-live", "knowledgeid": "kid-live"},
                      "attachments": [
                        {"type": "video", "jobid": "video-1", "property": {"name": "视频任务", "objectid": "obj-1"}, "objectId": "obj-1"}
                      ]
                    };
                    </script>
                    """,
                    "1": """
                    <script>
                    mArg = {
                      "defaults": {"ktoken": "kt-live", "cpi": "cpi-live", "knowledgeid": "kid-live"},
                      "attachments": [
                        {"type": "workid", "jobid": "work-1", "enc": "enc-work", "property": {"name": "作业任务"}}
                      ]
                    };
                    </script>
                    """,
                }
                return self.Response(200, responses.get(num, "<html><body>empty</body></html>"))

            def close(self):
                return None

        workflow = CourseStudyWorkflow(
            parser=parser,
            dispatcher=JobDispatcher({}, lambda *args, **kwargs: None),
            task_client=DummyTaskClient(),
            logger=lambda *args, **kwargs: None,
            collect_tiku=True,
        )
        jobs, info = workflow.get_job_list(
            {"classid": "class-1", "courseid": "course-1", "cpi": "cpi-course"},
            {"id": "kid-point", "title": "第一章"},
        )
        self.assertEqual(info["ktoken"], "kt-live")
        self.assertEqual(info["cpi"], "cpi-live")
        self.assertEqual(info["knowledgeid"], "kid-live")
        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[1]["type"], "workid")

    def test_runtime_context_collect_threads_normalized(self):
        runtime = RuntimeContext(version="test")
        self.assertEqual(runtime.normalize_collect_threads("0"), 1)
        self.assertEqual(runtime.normalize_collect_threads("99"), 32)
        self.assertEqual(runtime.normalize_collect_threads("3"), 3)

    def test_course_workflow_close_propagates(self):
        repository = DummyRepository()
        workflow = CourseWorkflow(
            repository=repository,
            selector=None,
            logger=lambda *args, **kwargs: None,
            formatter=lambda *args, **kwargs: None,
            runtime=RuntimeContext(version="test"),
        )
        workflow.close()
        self.assertTrue(repository.closed)

    def test_course_study_workflow_close_propagates(self):
        class DummyTaskClient:
            def __init__(self):
                self.closed = False

            def close(self):
                self.closed = True

        task_client = DummyTaskClient()
        workflow = CourseStudyWorkflow(
            parser=CourseTaskParser(),
            dispatcher=JobDispatcher({}, lambda *args, **kwargs: None),
            task_client=task_client,
            logger=lambda *args, **kwargs: None,
            collect_tiku=False,
        )
        workflow.close()
        self.assertTrue(task_client.closed)

    @patch("courses.course_repository.CourseClient")
    def test_course_repository_constructs(self, mock_client_cls):
        mock_client_cls.return_value = object()
        runtime = RuntimeContext(version="test", headers={"User-Agent": "ua"}, proxy=None)
        repository = CourseRepository(runtime, {"k": "v"})
        self.assertIsInstance(repository, CourseRepository)


if __name__ == "__main__":
    unittest.main()
