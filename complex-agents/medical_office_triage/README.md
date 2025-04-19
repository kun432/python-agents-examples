# Medical Office Triage

患者の症状や病歴に基づいてトリアージを行うエージェントのデモです。

- 窓口振り分け担当エージェント
  - 患者が医療サービスに関するサポートを求めているのか、請求に関する問題を抱えているのかを判断し、以下のエージェントを呼び出す
    - 患者サポート担当エージェント
    - 医療費請求担当エージェント
- 患者サポート担当エージェント
  - 予約の手配、処方薬の再発行、医療記録の請求、その他医療に関する一般的な質問に対応
- 医療費請求担当エージェント
  - 保険情報、自己負担額（コペイ）、医療費の請求、支払い手続き、請求に関する問い合わせなどに対応

## 使い方

### 前提

- LiveKitサーバをインストール、起動しておく。
  -  参考: https://docs.livekit.io/home/self-hosting/server-setup/
- LiveKitクライアントを用意しておく。
  - Agents Playgroundがおすすめ。
  - https://github.com/livekit/agents-playground

本ディレクトリで以下を実行

1. `.env.local` をコピーして、`.env` を作成。
```shell
cp .env.local .env
```
2. `.env`に OpenAI APIキーをセット
3. エージェントを起動
```
uv run triage.py dev
```
4. LiveKitクライアントから接続