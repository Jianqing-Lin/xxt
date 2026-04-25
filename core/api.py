import time
# from model.courses import Courses
from model.enc import enc
from model.cipher import encrypt_login_value
class Api:
    SSL = "https://"
    HTTP = "http://"
    HOST = HTTP + "120.46.165.86/" #"www.iceh2o1.top/" #服务器以及域名皆完成备案
    HOST0 = SSL + "passport2.chaoxing.com/"
    HOST1 = SSL + "mooc2-ans.chaoxing.com/mooc2-ans/"
    HOST2 = SSL + "passport2-api.chaoxing.com/"

    Update = HOST + "update"

    Login = HOST0 + "fanyalogin"
    # POST 账密登录
    def Login_fn(user: str, passwd: str) -> dict:
        return {
                "fid": "-1",
                "uname": encrypt_login_value(user),
                "password": encrypt_login_value(passwd),
                "refer": "https%3A%2F%2Fi.chaoxing.com",
                "t": True,
                "forbidotherlogin": 0,
                "validate": "",
                "doubleFactorLogin": 0,
                "independentId": 0,
                }

    Login_sms = HOST2 + "api/sendcaptcha"
    # POST 验证码登录
    def Login_sms_fn(to: str, countrycode=86, enc=enc()):
        return {
                "to": str(to),
                "countrycode": str(countrycode),
                "time": enc[0],
                "enc": enc[1],
                }

    Courses_Get = HOST1 + "visit/courselistdata"
    Courses_Get_Referer = HOST1 + "visit/interaction?moocDomain=https://mooc1-1.chaoxing.com/mooc-ans"
    # POST 获取课程
    def Courses_Get_fn(course_folder_id=0, query="", course_type=1, superstar_class=0):
        return {
                "courseType": course_type,
                "courseFolderId": course_folder_id,
                "query": query,
                "superstarClass": superstar_class,
                }

    Course_Get = HOST1 + "mycourse/studentcourse"
    # GET 获取课程详情
    def Course_GET_fn(courseid, classid, cpi):
        return {
                "courseid": courseid,
                "clazzid": classid,
                "cpi": cpi,
                "ut": "s",
                }

    Course_Cards = SSL + "mooc1.chaoxing.com/mooc-ans/knowledge/cards"
    Course_Empty = SSL + "mooc1.chaoxing.com/mooc-ans/mycourse/studentstudyAjax"
    Job_Read = SSL + "mooc1.chaoxing.com/ananas/job/readv2"
    Job_Document = SSL + "mooc1.chaoxing.com/ananas/job/document"
    Work_Api = SSL + "mooc1.chaoxing.com/mooc-ans/api/work"
    Work_Submit = SSL + "mooc1.chaoxing.com/mooc-ans/work/addStudentWorkNew"
    Media_Status = SSL + "mooc1.chaoxing.com/ananas/status/"
    Media_Log = SSL + "mooc1.chaoxing.com/mooc-ans/multimedia/log/a/"
    Video_Referer = SSL + "mooc1.chaoxing.com/ananas/modules/video/index.html?v=2025-0725-1842"
    Audio_Referer = SSL + "mooc1.chaoxing.com/ananas/modules/audio/index_new.html?v=2025-0725-1842"

    Course_Get_Info = SSL + "mooc1-api.chaoxing.com/gas/knowledge"
    # GET Course Info
    def Course_Get_Info_fn(classid, courseid, i_enc=enc()):
        return {
                "id": classid,
                "courseid": courseid,
                "fields": "id,parentnodeid,indexorder,label,layer,name,begintime,createtime,lastmodifytime,status,jobUnfinishedCount,clickcount,openlock,card.fields(id,knowledgeid,title,knowledgeTitile,description,cardorder).contentcard(all)",
                "view": "json",
                "token": "4faa8662c59590c6f43ae9fe5b002b42",
                "_time": i_enc[0],
                "inf_enc": i_enc[1]
                }
