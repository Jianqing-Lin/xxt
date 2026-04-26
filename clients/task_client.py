from core.api import Api


class TaskClient:
    def __init__(self, session_factory):
        self.session_factory = session_factory
        self.client = session_factory.get_shared_client()

    def close(self):
        self.session_factory.close()

    def get_job_cards(self, params: dict, num: str):
        return self.client.get(Api.Course_Cards, params={**params, "num": num})

    def get_read(self, params: dict):
        return self.client.get(Api.Job_Read, params=params)

    def get_document(self, params: dict):
        return self.client.get(Api.Job_Document, params=params)

    def get_work_page(self, params: dict):
        return self.client.get(Api.Work_Api, params=params)

    def submit_work(self, fields: dict, headers: dict):
        return self.client.post(Api.Work_Submit, data=fields, headers=headers)

    def get_empty_page(self, params: dict):
        return self.client.get(Api.Course_Empty, params=params)

    def get_media_status(self, object_id: str, params: dict, headers: dict):
        return self.client.get(f"{Api.Media_Status}{object_id}", params=params, headers=headers)

    def post_media_log(self, url: str, params: dict, headers: dict):
        return self.client.get(url, params=params, headers=headers)
