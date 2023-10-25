# mydns_notifier
MyDNS.jpへIPアドレスの通知を自動化するスクリプトです。  
cron等により周期的に実行することを想定しています。  
前回の通知から24時間経過、またはIPアドレスが変更をトリガーに通知を行います。  
以下の設定ファイルサンプルを参考にJSONファイルにID、パスワードを記入してください。
urlについては、結果表示のみに使用するので適当でも大丈夫です。  
アカウント名もオブジェクト名以上の意味はありませんのでなんでも良いです。  

## 設定ファイルのサンプル
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
