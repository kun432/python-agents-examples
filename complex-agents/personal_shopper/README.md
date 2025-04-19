# Personal Shopper

ユーザーの好みに基づいて商品を見つけるお手伝いをするAIショッピングアシスタントのデモです。

- 窓口振り分け担当エージェント
- 販売担当エージェント
- 返品担当エージェント

## 使い方

### 前提

- LiveKitサーバをインストール、起動しておく。
  -  参考: https://docs.livekit.io/home/self-hosting/server-setup/
- LiveKitクライアントを用意しておく。
  - Agents Playgroundがおすすめ。
  - https://github.com/livekit/agents-playground

### データベース情報

データベースはSQLite3を使用。日本語向けに customer_database_ja.db を作成している。

- データベースに登録されているデータの内容については add_test_orders.py を参照。
- データベースを再作成したい場合は `uv run add_test_orders.py` で初期化される。

### エージェントの実行

本ディレクトリで以下を実行

1. `.env.local` をコピーして、`.env` を作成。
```shell
cp .env.local .env
```
2. `.env`に OpenAI APIキーをセット
3. エージェントを起動
```
uv run personal_shopper.py dev
```
4. LiveKitクライアントから接続