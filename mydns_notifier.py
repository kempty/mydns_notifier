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
      JSONにOBJECTのようにアクセス出来る
      '''
      # PythonでJSONデータを扱う工夫 | TECHSCORE BLOG https://www.techscore.com/blog/2019/12/16/better-way-handling-json-data-in-python/
      __getattr__ = dict.get

class MydnsDomain :
    '''
    MyDNS
    '''
    def __init__(self, name:str, url:str, id:str, pw:str, last=None) -> None:
        self.__name = name
        self.__id   = id
        self.__pw   = pw
        self.__url  = url
        self.__ip   = get_ip_from_dns(url)
        if(last==None):
            self.__last = JsonObject(ip=get_global_ip(), time=datetime.now(JST))
        else:
            self.__last = JsonObject(ip=last.ip, time=datetime.fromisoformat(last.time))

    @property
    def name(self) -> str:
        return self.__name

    @property
    def id(self) -> str:
        return self.__id

    @property
    def pw(self) -> str:
        return self.__pw

    @property
    def url(self) -> str:
        return self.__url

    @property
    def ip(self) -> str:
        return self.__ip

    @property
    def last(self) -> JsonObject:
        return self.__last

    @classmethod
    def import_json(cls, path:str) -> list['MydnsDomain']:
        '''
        設定用JSONの読み込み
        '''
        with open(path) as fp:
            data = json.load(fp, object_hook=JsonObject)
        domains = []
        for key in data:
            domains.append(cls(key, data[key].url, data[key].id, data[key].pw, data[key].last))
        return domains

    @classmethod
    def export_json(cls, domains:list['MydnsDomain'], path:str) -> None:
        '''
        設定用JSONの書き込み
        '''
        out = JsonObject()
        for d in domains:
            out[d.name] = JsonObject(url=d.url,
                                     id=d.id,
                                     pw=d.pw,
                                     last=JsonObject(ip=d.last.ip,
                                                     time=d.last.time.isoformat(timespec='seconds')))
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
                auth=requests.auth.HTTPBasicAuth(self.__id, self.__pw),
                timeout=REQUESTS_TIMEOUT,
            )
            res.raise_for_status()
        except requests.RequestException as e:
            logging.error('Failed to notify %s: %s', self.__url, e)
            return False

        if res.status_code == HTTP_STATUS_CODE_OK:
            self.__last.ip = ip
            self.__last.time = datetime.now(JST)
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
