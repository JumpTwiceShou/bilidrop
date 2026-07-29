from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse

import httpx

from bilibili_drops_miner.client_parts.cookies import DEFAULT_USER_AGENT
from bilibili_drops_miner.utils import join_cookie


QR_GENERATE_URL = (
    "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
)
QR_POLL_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
LOGIN_COOKIE_NAMES = (
    "SESSDATA",
    "bili_jct",
    "DedeUserID",
    "DedeUserID__ckMd5",
    "sid",
    "buvid3",
    "b_nut",
)


class QrLoginState(str, Enum):
    PENDING = "pending"
    SCANNED = "scanned"
    SUCCESS = "success"
    EXPIRED = "expired"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class QrLoginSession:
    url: str
    key: str


@dataclass(frozen=True, slots=True)
class QrLoginPollResult:
    state: QrLoginState
    message: str
    cookie: str = ""


class BilibiliQrLoginService:
    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._transport = transport
        self._timeout_seconds = timeout_seconds
        self._headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Referer": "https://www.bilibili.com/",
        }

    def create_session(self) -> QrLoginSession:
        response = self._get(QR_GENERATE_URL)
        payload = self._payload(response, "获取登录二维码")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise RuntimeError("二维码接口没有返回有效数据")
        url = str(data.get("url") or "").strip()
        key = str(data.get("qrcode_key") or "").strip()
        if not url or not key:
            raise RuntimeError("二维码接口没有返回登录地址或密钥")
        return QrLoginSession(url=url, key=key)

    def poll(self, session: QrLoginSession) -> QrLoginPollResult:
        response = self._get(QR_POLL_URL, params={"qrcode_key": session.key})
        payload = self._payload(response, "检查二维码状态")
        data = payload.get("data")
        if not isinstance(data, dict):
            return QrLoginPollResult(QrLoginState.ERROR, "二维码状态数据无效")
        code = int(data.get("code") or 0)
        if code == 86101:
            return QrLoginPollResult(QrLoginState.PENDING, "等待手机扫描二维码")
        if code == 86090:
            return QrLoginPollResult(QrLoginState.SCANNED, "已扫描，请在手机上确认")
        if code == 86038:
            return QrLoginPollResult(QrLoginState.EXPIRED, "二维码已过期，请重新打开")
        if code != 0:
            return QrLoginPollResult(
                QrLoginState.ERROR,
                f"二维码登录失败（状态码 {code}）",
            )

        cookie = self._extract_cookie(response, str(data.get("url") or ""))
        if not cookie:
            return QrLoginPollResult(
                QrLoginState.ERROR,
                "登录成功，但响应中没有可用 Cookie",
            )
        return QrLoginPollResult(QrLoginState.SUCCESS, "扫码登录成功", cookie)

    def _get(self, url: str, *, params: dict[str, str] | None = None) -> httpx.Response:
        with httpx.Client(
            transport=self._transport,
            timeout=self._timeout_seconds,
            headers=self._headers,
            follow_redirects=False,
        ) as client:
            response = client.get(url, params=params)
        response.raise_for_status()
        return response

    @staticmethod
    def _payload(response: httpx.Response, action: str) -> dict:
        try:
            payload = response.json()
        except Exception:
            raise RuntimeError(f"{action}返回了无法解析的数据") from None
        if not isinstance(payload, dict):
            raise RuntimeError(f"{action}返回格式错误")
        code = int(payload.get("code") or 0)
        if code != 0:
            raise RuntimeError(f"{action}失败（状态码 {code}）")
        return payload

    @staticmethod
    def _extract_cookie(response: httpx.Response, callback_url: str) -> str:
        values: dict[str, str] = {}
        for item in response.cookies.jar:
            if item.name in LOGIN_COOKIE_NAMES and item.value:
                values[item.name] = item.value

        if callback_url:
            for part in urlparse(callback_url).query.split("&"):
                name, separator, value = part.partition("=")
                if separator and name in LOGIN_COOKIE_NAMES and value:
                    values.setdefault(name, value)

        return join_cookie(
            {name: values[name] for name in LOGIN_COOKIE_NAMES if values.get(name)}
        )
