#!/usr/bin/env python3
# –*- coding: utf-8 –*-

import os
import json
import time
import socket
from pathlib import Path
import logging
import requests                             # pip3 install requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo               # python -m pip install tzdata(Windowsのみ)
from typing import Final

MYDNS_IPV4_NOTIFIER_URL:Final[str] = 'https://ipv4.mydns.jp/login.html'
MYDNS_IPV6_NOTIFIER_URL:Final[str] = 'https://ipv6.mydns.jp/login.html'
SCRIPT_DIR:Final[Path] = Path(__file__).resolve().parent
JSON_PATH:Final[Path] = SCRIPT_DIR / 'mydns.json'
LOG_DIR:Final[Path] = SCRIPT_DIR / 'log'
LOG_PATH:Final[Path] = LOG_DIR / 'mydns_notifier.log'

# ensure log directory exists and configure logging
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=str(LOG_PATH),
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)

REQUESTS_TIMEOUT:Final[int] = 5

IDX_ADDR_INFO_IP:Final[int] = 4
IDX_IP_STR:Final[int] = 0

HTTP_STATUS_CODE_OK:Final[int] = 200

JST:Final[ZoneInfo] = ZoneInfo('Asia/Tokyo')           # 日本標準時(UTC+0900)

ONE_DAY_SECONDS:Final[int] = 24 * 60 * 60              # 24時間の秒数
NOTIFIER_TIMEOUT:Final[int] = ONE_DAY_SECONDS - 30     # タイムアウト時間(少しずつ遅れないように30秒分余裕しろを持つ)

class JsonObject(dict):
    '''
    JSONにOBJECTのようにアクセス出来る（属性アクセスを提供）
    '''
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)

class MydnsDomain :
    '''
    MyDNS
    '''
    def __init__(self, name:str, url:str, id:str, pw:str, last=None) -> None:
        self._name = name
        self._id   = id
        self._pw   = pw
        self._url  = url
        # avoid network calls in __init__; populate ip/last in import_json or explicitly
        self._ip = None
        self._last = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def id(self) -> str:
        return self._id

    @property
    def pw(self) -> str:
        return self._pw

    @property
    def url(self) -> str:
        return self._url

    @property
    def ip(self) -> str:
        return self._ip

    @property
    def last(self) -> JsonObject:
        return self._last

    @classmethod
    def import_json(cls, path:str | Path) -> list['MydnsDomain']:
        '''
        設定用JSONの読み込み
        '''
        try:
            with open(path) as fp:
                data = json.load(fp)
        except FileNotFoundError:
            logging.error('Config file not found: %s', path)
            raise
        except json.JSONDecodeError as e:
            logging.error('Config JSON decode error: %s', e)
            raise

        domains = []
        for key, entry in data.items():
            url = entry.get('url')
            id_ = entry.get('id')
            pw = entry.get('pw')
            last = entry.get('last')

            d = cls(key, url, id_, pw, last=None)

            # parse last
            if last:
                try:
                    t_str = last.get('time')
                    t = datetime.fromisoformat(t_str).astimezone(JST)
                    d._last = JsonObject(ip=last.get('ip'), time=t)
                except Exception as e:
                    logging.warning('Invalid last entry for %s: %s', key, e)
                    d._last = JsonObject(ip=None, time=datetime.now(JST))
            else:
                try:
                    cur_ip = get_global_ip()
                except Exception:
                    cur_ip = None
                d._last = JsonObject(ip=cur_ip, time=datetime.now(JST))

            # resolve DNS for ip
            try:
                d._ip = get_ip_from_dns(d.url)
            except Exception:
                d._ip = None

            domains.append(d)
        return domains

    @classmethod
    def export_json(cls, domains:list['MydnsDomain'], path:str | Path) -> None:
        '''
        設定用JSONの書き込み
        '''
        out = {}
        for d in domains:
            time_iso = d.last.time.isoformat(timespec='seconds') if d.last and isinstance(d.last.time, datetime) else None
            out[d.name] = {
                'url': d.url,
                'id': d.id,
                'pw': d.pw,
                'last': {
                    'ip': d.last.ip if d.last else None,
                    'time': time_iso,
                }
            }
        with open(path, 'w') as fp:
            json.dump(out, fp, indent=4)

    def notify_ipv4(self, ip:str) -> bool :
        '''
        MyDNSにIPアドレスを通知する

        Parameters
        ----------
        ip : str
            現在のサーバーIPアドレス()

        Returns
        -------
        result : bool
            通知の成否
        '''
        try:
            res = requests.post(
                MYDNS_IPV4_NOTIFIER_URL,
                auth=requests.auth.HTTPBasicAuth(self._id, self._pw),
                timeout=REQUESTS_TIMEOUT,
            )
            res.raise_for_status()
        except requests.RequestException as e:
            logging.error('Failed to notify %s: %s', self._url, e)
            return False

        if res.status_code == HTTP_STATUS_CODE_OK:
            # update last
            if not self._last:
                self._last = JsonObject(ip=ip, time=datetime.now(JST))
            else:
                self._last.ip = ip
                self._last.time = datetime.now(JST)
            return True
        else:
            logging.error('http response = %s', res.status_code)
            return False

def get_ip_from_dns(url:str) -> str :
    '''
    Parameters
    ----------
    url:str
        名前解決したいURL

    Returns
    -------
    dns_ip : str
        urlを名前解決したIPアドレス
    '''
    try:
        addr_inf = socket.getaddrinfo(url, None)
        for ai in addr_inf:
            try:
                sockaddr = ai[IDX_ADDR_INFO_IP]
                dns_ip = sockaddr[IDX_IP_STR]
                return dns_ip
            except Exception:
                continue
        raise ValueError(f'no address found for {url}')
    except socket.gaierror as e:
        logging.error('DNS lookup failed for %s: %s', url, e)
        raise

def get_global_ip() -> str :
    '''
    Returns
    -------
    global_ip : str
        This machine's Global IP Address
    '''
    try:
        r = requests.get('https://ifconfig.me/ip', timeout=REQUESTS_TIMEOUT)
        r.raise_for_status()
        return r.text.strip()
    except requests.RequestException as e:
        logging.error('Failed to get global IP: %s', e)
        raise

def check_timeout(last_time:datetime, timeout_sec:float) -> bool :
    '''
    基準時刻から、タイムアウト秒数以上経過(タイムアウト)しているか判定する
    基準時刻に未来を指定された場合は、必ずタイムアウト

    Parameters
    ----------
    last_time: 基準時刻
    timeout_sec: タイムアウト時間

    Returns
    -------
    is_timeout : bool
        True: タイムアウト発生
        False: タイムアウト未発生
    '''
    time_out = last_time + timedelta(seconds=timeout_sec)     # タイムアウト発生時刻を算出
    is_timeout = (datetime.now(JST) > time_out)               # 現在時刻がタイムアウト発生時刻以降か判定
    return is_timeout

def puts_log(msg:str) :
    # ひとまずやっつけ起動ログ
    msg = datetime.now(JST).isoformat(timespec='seconds') + ', ' + msg
    print(msg)
    logging.info(msg)

def main() -> None :
    puts_log(os.path.basename(__file__) + '起動')
    # 各ドメインのインスタンスを作る
    domains = MydnsDomain.import_json(JSON_PATH)

    # 現在のグローバルIPを確認
    cur_ip  = get_global_ip()

    # 各ドメインのDNSに登録されたIPと現在のIPを比較し不一致か、前回から24時間経過していればIP通知する
    for d in domains :
        is_need_notifier = (cur_ip != d.ip) or check_timeout(d.last.time, NOTIFIER_TIMEOUT)
        if is_need_notifier :
            if(d.notify_ipv4(cur_ip)):
                # 通知成功
                puts_log(d.url + ' (' + cur_ip + ') : IP ADDRESS NOTIFICATION SUCCESS!')
                # 結果をJSONファイルに書き出し
                MydnsDomain.export_json(domains, JSON_PATH)
                time.sleep(1)                           #通知した場合は次まで1秒Waitする
            else:
                # 通知失敗
                puts_log(d.url + ' : IP ADDRESS NOTIFICATION FAILED!')
        else :
            puts_log(d.url + ' (' + d.ip + ') : NO NOTIFICATION NECESSARY.')
    puts_log(os.path.basename(__file__) + '終了')

if __name__ == '__main__' : 
    main()
