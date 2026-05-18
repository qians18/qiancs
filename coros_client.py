"""
COROS Training Hub 客户端（逆向API，中国区）
"""
import hashlib
import json
import os
import time
import requests

BASE_URL = "https://teamcnapi.coros.com"
TOKEN_FILE = os.path.join(os.path.dirname(__file__), "data", ".coros_token")


def _retry(func):
    """重试装饰器：处理SSL错误和限流"""
    def wrapper(*args, **kwargs):
        last_err = None
        for attempt in range(5):
            try:
                return func(*args, **kwargs)
            except requests.exceptions.SSLError as e:
                last_err = e
                wait = (attempt + 1) * 3
                time.sleep(wait)
            except Exception as e:
                msg = str(e)
                if "Service exception" in msg or "429" in msg or "rate" in msg.lower():
                    last_err = e
                    wait = (attempt + 1) * 5
                    time.sleep(wait)
                else:
                    raise
        raise last_err
    return wrapper


class CorosClient:
    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Content-Type": "application/json",
        })
        self.access_token = None
        self.user_id = None
        self._load_token()

    # ---------- Auth ----------
    @_retry
    def login(self) -> bool:
        """登录获取 access_token"""
        pwd_hash = hashlib.md5(self.password.encode()).hexdigest()
        resp = self.session.post(f"{BASE_URL}/account/login", json={
            "account": self.email,
            "pwd": pwd_hash,
            "accountType": 2,
        })
        data = resp.json()
        if data.get("result") != "0000":
            raise Exception(f"登录失败: {data.get('message', data)}")
        self.access_token = data["data"]["accessToken"]
        self.user_id = data["data"]["userId"]
        self.session.headers["accessToken"] = self.access_token
        self._save_token()
        return True

    def _load_token(self):
        if os.path.exists(TOKEN_FILE):
            try:
                with open(TOKEN_FILE) as f:
                    t = json.load(f)
                self.access_token = t["accessToken"]
                self.user_id = t["userId"]
                self.session.headers["accessToken"] = self.access_token
            except Exception:
                pass

    def _save_token(self):
        with open(TOKEN_FILE, "w") as f:
            json.dump({"accessToken": self.access_token, "userId": self.user_id}, f)

    def ensure_auth(self):
        if not self.access_token:
            self.login()

    # ---------- Activities ----------
    def list_activities(self, start_day=None, end_day=None, page=1, size=30,
                        sport_type=None, mode_list=None):
        """获取活动列表（需指定日期范围 YYYYMMDD）"""
        self.ensure_auth()
        if not start_day:
            import datetime
            start_day = (datetime.date.today() - datetime.timedelta(days=90)).strftime("%Y%m%d")
        if not end_day:
            import datetime
            end_day = datetime.date.today().strftime("%Y%m%d")
        params = {"startDay": start_day, "endDay": end_day, "pageNumber": page, "size": size}
        if sport_type:
            params["sportType"] = sport_type
        if mode_list:
            params["modeList"] = ",".join(str(m) for m in mode_list)
        resp = self.session.get(f"{BASE_URL}/activity/query", params=params)
        data = resp.json()
        if data.get("result") != "0000":
            raise Exception(f"获取活动列表失败: {data.get('message', data)}")
        result = data.get("data", {})
        return result.get("dataList", result.get("list", []))

    @_retry
    def get_activity_detail(self, label_id: str, sport_type: int):
        """获取单次活动详细数据（包含分段指标）"""
        self.ensure_auth()
        form_data = {"labelId": label_id, "userId": str(self.user_id),
                     "sportType": str(sport_type)}
        headers = {
            "accessToken": self.access_token,
            "yfheader": json.dumps({"userId": self.user_id}),
        }
        resp = requests.post(f"{BASE_URL}/activity/detail/query",
                             data=form_data, headers=headers)
        data = resp.json()
        if data.get("result") != "0000":
            raise Exception(f"获取活动详情失败: {data.get('message', data)}")
        return data["data"]

    def download_fit(self, label_id: str, sport_type: int, save_path: str) -> str:
        """下载FIT文件到本地"""
        self.ensure_auth()
        headers = {
            "accessToken": self.access_token,
            "yfheader": json.dumps({"userId": self.user_id}),
        }
        resp = requests.post(f"{BASE_URL}/activity/detail/download",
                             data={"labelId": label_id,
                                   "userId": str(self.user_id),
                                   "sportType": sport_type,
                                   "fileType": 4},
                             headers=headers)
        data = resp.json()
        if data.get("result") != "0000":
            raise Exception(f"获取下载链接失败: {data.get('message', data)}")
        file_url = data["data"]["fileUrl"]
        fit_data = self.session.get(file_url).content
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, "wb") as f:
            f.write(fit_data)
        return save_path

    def get_evolab(self, label_id: str, sport_type: int):
        """获取EvoLab分析数据（VO2max、训练负荷、恢复等）"""
        self.ensure_auth()
        try:
            headers = {
                "accessToken": self.access_token,
                "yfheader": json.dumps({"userId": self.user_id}),
            }
            resp = requests.post(f"{BASE_URL}/analyse/query",
                                 data={"labelId": label_id,
                                       "userId": str(self.user_id),
                                       "sportType": str(sport_type)},
                                 headers=headers)
            data = resp.json()
            if data.get("result") == "0000":
                return data["data"]
        except Exception:
            pass
        return None

    # ---------- Helpers ----------
    @staticmethod
    def sport_type_name(sport_type: int) -> str:
        mapping = {100: "跑步", 102: "越野跑", 103: "田径场跑步", 104: "徒步",
                   200: "公路骑行", 201: "室内骑行", 203: "砾石骑行", 204: "山地骑行",
                   400: "有氧运动", 402: "力量训练", 403: "瑜伽",
                   900: "步行", 9807: "通勤骑行"}
        return mapping.get(sport_type, f"运动({sport_type})")

    def get_recent_runs(self, count=30):
        """获取最近的跑步记录"""
        import datetime
        end_day = datetime.date.today().strftime("%Y%m%d")
        start_day = (datetime.date.today() - datetime.timedelta(days=365)).strftime("%Y%m%d")
        all_runs = []
        page = 1
        while len(all_runs) < count:
            activities = self.list_activities(start_day=start_day, end_day=end_day,
                                              page=page, size=50)
            if not activities:
                break
            runs = [a for a in activities if a.get("sportType") in (100, 102, 103, 900)]
            all_runs.extend(runs)
            if len(activities) < 50:
                break
            page += 1
        return all_runs[:count]
