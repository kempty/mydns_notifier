# mydns_notifier
MyDNS.jpへIPアドレスの通知を自動化するスクリプトです。  
cron等により周期的に実行することを想定しています。  
前回の通知から24時間経過、またはIPアドレスが変更をトリガーに通知を行います。  
IPv4のみ対応。

## 設定ファイル
以下の設定ファイルサンプルを参考にJSONファイルにID、パスワード、urlを記入して、  
スクリプトと同じ改装に```mydns.json```のファイル名で保存してください。  
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
            "ip": "192.168.1.256",
            "time": "2023-10-22T17:40:26+09:00"
        }
    },
    "account2": {
        "url": "your.domain2.mydnsjp",
        "id": "your_mydns_id2",
        "pw": "your_password2",
        "last": {
            "ip": "192.168.1.256",
            "time": "2023-10-22T17:40:26+09:00"
        }
    }
}
```

## 今後やるかも
* 動作ログの出力
* 通知周期を24時間固定ではなく、JSONで指定できるようにする？
* IPv6への対応