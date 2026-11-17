#!/usr/bin/env python3

import json
import logging
import os
import socket
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Final
from zoneinfo import ZoneInfo  # python -m pip install tzdata(Windowsのみ)

import requests  # pip3 install requests

MYDNS_IPV4_NOTIFIER_URL: Final[str] = 'https://ipv4.mydns.jp/login.html'
MYDNS_IPV6_NOTIFIER_URL: Final[str] = 'https://ipv6.mydns.jp/login.html'
PUBLIC_IP_URLS: Final[dict[str, str]] = {
    'ipv4': 'https://v4.ident.me',
    'ipv6': 'https://v6.ident.me',
}
IPV4: Final[str] = 'ipv4'
IPV6: Final[str] = 'ipv6'
NOTIFIER_URLS: Final[dict[str, str]] = {
    IPV4: MYDNS_IPV4_NOTIFIER_URL,
    IPV6: MYDNS_IPV6_NOTIFIER_URL,
}
SCRIPT_DIR: Final[Path] = Path(__file__).resolve().parent
JSON_PATH: Final[Path] = SCRIPT_DIR / 'mydns.json'
LOG_DIR: Final[Path] = SCRIPT_DIR / 'log'
LOG_PATH: Final[Path] = LOG_DIR / 'mydns_notifier.log'

# ensure log directory exists and configure logging
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOG_MAX_BYTES: Final[int] = 1_000_000
LOG_BACKUP_COUNT: Final[int] = 5
handler = RotatingFileHandler(
    filename=str(LOG_PATH),
    maxBytes=LOG_MAX_BYTES,
    backupCount=LOG_BACKUP_COUNT,
    encoding='utf-8',
)
handler.setFormatter(
    logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
)
logging.basicConfig(level=logging.INFO, handlers=[handler])

# module logger
logger = logging.getLogger(__name__)

REQUESTS_TIMEOUT: Final[int] = 5
HTTP_STATUS_CODE_OK: Final[int] = 200

JST: Final[ZoneInfo] = ZoneInfo('Asia/Tokyo')           # 日本標準時(UTC+0900)
ONE_DAY_SECONDS: Final[int] = 24 * 60 * 60  # 24時間の秒数
NOTIFIER_TIMEOUT: Final[int] = (
    ONE_DAY_SECONDS - 30
)  # タイムアウト時間(少しずつ遅れないように30秒分余裕しろを持つ)

@dataclass
class Last:
    """前回の通知履歴（IPアドレスおよび通知日時）を保持するデータクラス。"""

    ipv4: str | None = None
    ipv6: str | None = None
    ipv4_time: datetime | None = None
    ipv6_time: datetime | None = None


class MydnsDomain:
    """MyDNSで管理するドメインの情報と通知処理を扱うクラス。"""

    def __init__(
        self,
        name: str,
        url: str,
        id: str,
        pw: str,
        last: Last | None = None,
    ) -> None:
        """
        MydnsDomainのインスタンスを初期化する。

        Parameters
        ----------
        name : str
            ドメイン名（識別用キー）
        url : str
            対象ドメインのURL（ホスト名）
        id : str
            MyDNSのログインID
        pw : str
            MyDNSのログインパスワード
        last : Last | None, optional
            前回の通知情報。省略時はNone
        """
        self._name = name
        self._id = id
        self._pw = pw
        self._url = url
        self._ipv4: str | None = None
        self._ipv6: str | None = None
        self._last = last

    @property
    def name(self) -> str:
        """ドメイン名（識別用キー）を取得する。"""
        return self._name

    @property
    def id(self) -> str:
        """MyDNSログインIDを取得する。"""
        return self._id

    @property
    def pw(self) -> str:
        """MyDNSログインパスワードを取得する。"""
        return self._pw

    @property
    def url(self) -> str:
        """対象ドメインのURL（ホスト名）を取得する。"""
        return self._url

    @property
    def ipv4(self) -> str | None:
        """DNSから名前解決したIPv4アドレスを取得する。"""
        return self._ipv4

    @property
    def ipv6(self) -> str | None:
        """DNSから名前解決したIPv6アドレスを取得する。"""
        return self._ipv6

    @property
    def last(self) -> Last | None:
        """前回の通知情報を取得する。"""
        return self._last

    @classmethod
    def import_json(cls, path: str | Path) -> list['MydnsDomain']:
        """
        設定ファイル（JSON）からドメイン設定を読み込み、MydnsDomainのリストを生成する。

        Parameters
        ----------
        path : str | Path
            読み込むJSONファイルのパス

        Returns
        -------
        list[MydnsDomain]
            生成されたMydnsDomainインスタンスのリスト

        Raises
        ------
        FileNotFoundError
            設定ファイルが存在しない場合
        json.JSONDecodeError
            設定ファイルが正しいJSON形式でない場合
        """
        try:
            with open(path) as fp:
                data = json.load(fp)
        except FileNotFoundError:
            logger.error('Config file not found: %s', path)
            raise
        except json.JSONDecodeError as e:
            logger.error('Config JSON decode error: %s', e)
            raise

        domains: list[MydnsDomain] = []
        for key, entry in data.items():
            url = entry.get('url')
            id_ = entry.get('id')
            pw = entry.get('pw')
            last = entry.get('last')

            d = cls(key, url, id_, pw)

            if last:
                try:
                    ipv4 = last.get('ipv4')
                    if ipv4 is None and 'ip' in last:
                        ipv4 = last.get('ip')

                    ipv6 = last.get('ipv6')

                    ipv4_time = None
                    ipv6_time = None
                    if ipv4 is not None:
                        ipv4_time = _parse_datetime(last.get('ipv4_time') or last.get('time'))
                    if ipv6 is not None:
                        ipv6_time = _parse_datetime(last.get('ipv6_time'))

                    d._last = Last(
                        ipv4=ipv4,
                        ipv6=ipv6,
                        ipv4_time=ipv4_time,
                        ipv6_time=ipv6_time,
                    )
                except (ValueError, TypeError) as e:
                    logger.warning('Invalid last entry for %s: %s', key, e)
                    d._last = Last()
            else:
                now = datetime.now(JST)
                try:
                    ipv4 = get_global_ip(IPV4)
                except requests.RequestException:
                    ipv4 = None
                try:
                    ipv6 = get_global_ip(IPV6)
                except requests.RequestException:
                    ipv6 = None
                d._last = Last(
                    ipv4=ipv4,
                    ipv6=ipv6,
                    ipv4_time=now if ipv4 else None,
                    ipv6_time=now if ipv6 else None,
                )

            d.refresh_ip()
            domains.append(d)
        return domains

    @classmethod
    def export_json(cls, domains: list['MydnsDomain'], path: str | Path) -> None:
        """
        ドメイン一覧の現在の設定および最新通知状態をJSONファイルに保存する。

        Parameters
        ----------
        domains : list[MydnsDomain]
            保存対象のMydnsDomainインスタンスのリスト
        path : str | Path
            保存先のJSONファイルパス
        """
        out: dict[str, object] = {}
        for d in domains:
            out[d.name] = {
                'url': d.url,
                'id': d.id,
                'pw': d.pw,
                'last': {
                    'ipv4': d.last.ipv4 if d.last else None,
                    'ipv4_time': (
                        d.last.ipv4_time.isoformat(timespec='seconds')
                        if d.last and d.last.ipv4_time
                        else None
                    ),
                    'ipv6': d.last.ipv6 if d.last else None,
                    'ipv6_time': (
                        d.last.ipv6_time.isoformat(timespec='seconds')
                        if d.last and d.last.ipv6_time
                        else None
                    ),
                },
            }
        with open(path, 'w') as fp:
            json.dump(out, fp, indent=4)

    def refresh_ip(self) -> None:
        """
        DNSから対象ドメインの最新のIPv4およびIPv6アドレスを取得してプロパティを更新する。
        """
        try:
            self._ipv4 = get_ip_from_dns(self.url, socket.AF_INET)
        except (socket.gaierror, ValueError):
            self._ipv4 = None

        try:
            self._ipv6 = get_ip_from_dns(self.url, socket.AF_INET6)
        except (socket.gaierror, ValueError):
            self._ipv6 = None

    def _update_last(self, family: str, ip: str) -> None:
        if not self._last:
            self._last = Last()
        now = datetime.now(JST)
        if family == IPV4:
            self._last.ipv4 = ip
            self._last.ipv4_time = now
        else:
            self._last.ipv6 = ip
            self._last.ipv6_time = now

    def notify_ipv4(self, ip: str) -> bool:
        """
        MyDNSにIPv4アドレスを通知する。

        Parameters
        ----------
        ip : str
            通知するIPv4アドレス

        Returns
        -------
        bool
            通知が成功した場合はTrue、失敗した場合はFalse
        """
        return self._notify(ip, NOTIFIER_URLS[IPV4], IPV4)

    def notify_ipv6(self, ip: str) -> bool:
        """
        MyDNSにIPv6アドレスを通知する。

        Parameters
        ----------
        ip : str
            通知するIPv6アドレス

        Returns
        -------
        bool
            通知が成功した場合はTrue、失敗した場合はFalse
        """
        return self._notify(ip, NOTIFIER_URLS[IPV6], IPV6)

    def _notify(self, ip: str, notifier_url: str, family: str) -> bool:
        """
        MyDNSにIPアドレスを通知する。

        Parameters
        ----------
        ip : str
            現在のサーバーIPアドレス
        notifier_url : str
            通知先URL
        family : str
            'ipv4' または 'ipv6'

        Returns
        -------
        bool
            通知の成否
        """
        try:
            res = requests.post(
                notifier_url,
                auth=requests.auth.HTTPBasicAuth(self._id, self._pw),
                timeout=REQUESTS_TIMEOUT,
            )
            res.raise_for_status()
        except requests.RequestException as e:
            logger.error('Failed to notify %s: %s', self._url, e)
            return False

        if res.status_code == HTTP_STATUS_CODE_OK:
            self._update_last(family, ip)
            return True

        logger.error('http response = %s', res.status_code)
        return False


def _parse_datetime(datetime_str: str | None) -> datetime | None:
    if not datetime_str:
        return None
    try:
        return datetime.fromisoformat(datetime_str).astimezone(JST)
    except (ValueError, TypeError):
        raise


def get_ip_from_dns(url: str, family: int = socket.AF_UNSPEC) -> str:
    """
    指定されたURL（ホスト名）をDNSで名前解決し、IPアドレスを取得する。

    Parameters
    ----------
    url : str
        名前解決したいURL（ホスト名）
    family : int, optional
        解決するアドレスファミリ。`socket.AF_INET`, `socket.AF_INET6`,
        または `socket.AF_UNSPEC`（デフォルトは `socket.AF_UNSPEC`）

    Returns
    -------
    str
        名前解決されたIPアドレス

    Raises
    ------
    socket.gaierror
        DNSの名前解決に失敗した場合
    ValueError
        アドレス情報が見つからなかった場合
    """
    try:
        addr_inf = socket.getaddrinfo(url, None, family)
        for ai in addr_inf:
            sockaddr = ai[4]
            try:
                dns_ip = sockaddr[0]
                return dns_ip
            except (IndexError, TypeError, AttributeError) as e:
                logger.debug('Skipping addrinfo entry: %s', e)
                continue
        raise ValueError(f'no address found for {url}')
    except socket.gaierror as e:
        logger.error('DNS lookup failed for %s: %s', url, e)
        raise


def get_global_ip(ip_version: str = IPV4) -> str:
    """
    外部サービスを利用して、このマシンのグローバルIPアドレスを取得する。

    Parameters
    ----------
    ip_version : str, optional
        取得するIPバージョン（'ipv4' または 'ipv6'、デフォルトは 'ipv4'）

    Returns
    -------
    str
        取得されたグローバルIPアドレス

    Raises
    ------
    ValueError
        無効なip_versionが指定された場合
    requests.RequestException
        IPアドレスの取得リクエストが失敗した場合
    """
    url = PUBLIC_IP_URLS.get(ip_version)
    if not url:
        raise ValueError('Invalid IP version: %s' % ip_version)

    try:
        r = requests.get(url, timeout=REQUESTS_TIMEOUT)
        r.raise_for_status()
        return r.text.strip()
    except requests.RequestException as e:
        logger.error('Failed to get global IP (%s): %s', ip_version, e)
        raise


def should_notify(
    cur_ip: str | None,
    dns_ip: str | None,
    last_ip: str | None,
    last_time: datetime | None,
) -> bool:
    """
    MyDNSへのIPアドレス通知が必要かどうかを判定する。

    Parameters
    ----------
    cur_ip : str | None
        現在のグローバルIPアドレス
    dns_ip : str | None
        DNSに登録されているIPアドレス
    last_ip : str | None
        最後に通知したIPアドレス
    last_time : datetime | None
        最後に通知した時刻

    Returns
    -------
    bool
        通知が必要な場合はTrue、不要な場合はFalse
    """
    if not cur_ip or not dns_ip:
        return False
    if last_ip != cur_ip:
        return True
    if not last_time:
        return True
    return check_timeout(last_time, NOTIFIER_TIMEOUT)


def check_timeout(last_time: datetime, timeout_sec: float) -> bool:
    """
    基準時刻から指定された秒数以上経過（タイムアウト）しているかを判定する。

    基準時刻に未来の日時が指定された場合は、必ずタイムアウト（True）と判定する。

    Parameters
    ----------
    last_time : datetime
        基準時刻
    timeout_sec : float
        タイムアウト時間（秒）

    Returns
    -------
    bool
        タイムアウトが発生した場合はTrue、未発生の場合はFalse
    """
    time_out = (
        last_time + timedelta(seconds=timeout_sec)
    )  # タイムアウト発生時刻を算出
    is_timeout = (
        datetime.now(JST) > time_out
    )  # 現在時刻がタイムアウト発生時刻以降か判定
    return is_timeout


def puts_log(msg: str) -> None:
    """
    タイムスタンプ付きのログメッセージを標準出力とログファイルに出力する。

    Parameters
    ----------
    msg : str
        出力するログメッセージ
    """
    # ひとまずやっつけ起動ログ
    msg = datetime.now(JST).isoformat(timespec='seconds') + ', ' + msg
    print(msg)
    logger.info(msg)


def main() -> None:
    """
    メイン処理。設定ファイルを読み込み、各ドメインのIP確認・更新・通知を実行する。
    """
    puts_log(os.path.basename(__file__) + '起動')
    # 各ドメインのインスタンスを作る
    domains = MydnsDomain.import_json(JSON_PATH)

    # 現在のグローバルIPを確認
    global_ips: dict[str, str | None] = {}
    for family in (IPV4, IPV6):
        try:
            global_ips[family] = get_global_ip(family)
        except requests.RequestException:
            global_ips[family] = None

    for d in domains:
        notified = False
        for family in (IPV4, IPV6):
            cur_ip = global_ips[family]
            if family == IPV4:
                dns_ip = d.ipv4
                last_ip = d.last.ipv4 if d.last else None
                last_time = d.last.ipv4_time if d.last else None
            else:
                dns_ip = d.ipv6
                last_ip = d.last.ipv6 if d.last else None
                last_time = d.last.ipv6_time if d.last else None

            if should_notify(cur_ip, dns_ip, last_ip, last_time):
                if family == IPV4:
                    success = d.notify_ipv4(cur_ip)
                else:
                    success = d.notify_ipv6(cur_ip)

                if success:
                    puts_log(
                        f'{d.url} ({family}={cur_ip}) : IP ADDRESS NOTIFICATION SUCCESS!'
                    )
                    notified = True
                else:
                    puts_log(f'{d.url} ({family}) : IP ADDRESS NOTIFICATION FAILED!')

        if notified:
            MydnsDomain.export_json(domains, JSON_PATH)
            time.sleep(1)  # 通知した場合は次まで1秒Waitする
        else:
            ip_info: list[str] = []
            if d.ipv4:
                ip_info.append(f'ipv4={d.ipv4}')
            if d.ipv6:
                ip_info.append(f'ipv6={d.ipv6}')
            puts_log(
                d.url + ' (' + ', '.join(ip_info) + ') : NO NOTIFICATION NECESSARY.'
            )

    puts_log(os.path.basename(__file__) + '終了')

if __name__ == '__main__':
    main()
