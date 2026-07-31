# mydns_notifier
MyDNS.jpへIPアドレスの通知を自動化するスクリプトです。  
cron等により周期的に実行することを想定しています。  
前回の通知から24時間経過、またはIPアドレスが変更をトリガーに通知を行います。  
IPv4/IPv6の両方に対応しています。

## 設定ファイル
以下の設定ファイルサンプルを参考にJSONファイルにID、パスワード、urlを記入して、  
スクリプトと同じ階層に```mydns.json```のファイル名で保存してください。  
アカウント名はオブジェクト名以上の意味はありませんのでなんでも良いです。  
last以下の項目は前回の通知時のIPと日時を記録しています。  
アカウントの数は何個でも良いですが、一度に全て通知しに行くのでほどほどの数がよいかもしれません。

```json
{
    "account1": {
        "url": "your.domain.mydnsjp",
        "id": "your_mydns_id",
        "pw": "your_password",
        "last": {
            "ipv4": "203.0.113.5",
            "ipv4_time": "2026-08-01T12:00:00+09:00",
            "ipv6": "2001:db8::5",
            "ipv6_time": "2026-08-01T12:00:00+09:00"
        }
    },
    "account2": {
        "url": "your.domain2.mydnsjp",
        "id": "your_mydns_id2",
        "pw": "your_password2",
        "last": {
            "ipv4": "203.0.113.6",
            "ipv4_time": "2026-08-01T12:00:00+09:00",
            "ipv6": null,
            "ipv6_time": null
        }
    }
}
```

古い形式の```ip```/```time```も読み込みは可能ですが、書き出し後は新しい```ipv4```/```ipv6```形式になります。

## インストール

依存関係は `pyproject.toml` に移行しました。

```bash
python3 -m pip install --upgrade pip
python3 -m pip install --no-cache-dir ".[dev]"
```

## 今後やるかも
* 通知周期を24時間固定ではなく、JSONで指定できるようにする？
* JSONの設定をさらに柔軟にする