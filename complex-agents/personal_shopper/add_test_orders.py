#!/usr/bin/env python3
import logging
import os
import sqlite3

from database import CustomerDatabase

# ロギングの設定
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("test-orders")


def clear_database(db):
    """データベースの内容をクリアします。"""
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM orders")
    cursor.execute("DELETE FROM customers")
    # SQLiteのAUTOINCREMENTをリセット
    cursor.execute("DELETE FROM sqlite_sequence")
    conn.commit()
    conn.close()
    logger.info("データベースの内容をクリアしました")


def add_test_orders():
    """山田太郎と鈴木花子のテスト注文データを追加します。"""
    # 日本語版データベースの初期化
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(script_dir, "customer_data_ja.db")
    db = CustomerDatabase(db_path)

    # 既存データをクリア
    clear_database(db)

    # 鈴木花子を作成
    first_name = "花子"
    last_name = "鈴木"
    customer_id = db.get_or_create_customer(first_name, last_name)
    logger.info(f"{last_name} {first_name}様の顧客ID: {customer_id}")

    # 山田太郎を作成
    first_name = "太郎"
    last_name = "山田"
    customer_id = db.get_or_create_customer(first_name, last_name)
    logger.info(f"{last_name} {first_name}様の顧客ID: {customer_id}")

    # テスト注文を追加

    # 注文1: 電子機器
    order1 = {
        "items": [
            {"name": "スマートフォン XS Pro", "quantity": 1, "price": 99999},
            {"name": "ワイヤレスイヤホン", "quantity": 1, "price": 14999},
            {"name": "スマートフォンケース（ブラック）", "quantity": 1, "price": 2999},
        ],
        "total": 117997,
        "payment_method": "クレジットカード",
        "shipping_address": "東京都渋谷区渋谷1-1-1",
    }

    # 注文2: 衣類
    order2 = {
        "items": [
            {"name": "メンズカジュアルシャツ（ブルー）", "quantity": 2, "price": 3999},
            {"name": "ジーンズ（ダークウォッシュ）", "quantity": 1, "price": 5999},
            {"name": "レザーベルト", "quantity": 1, "price": 3499},
        ],
        "total": 17496,
        "payment_method": "PayPay",
        "shipping_address": "東京都渋谷区渋谷1-1-1",
    }

    # 注文3: 家庭用品
    order3 = {
        "items": [
            {"name": "コーヒーメーカー", "quantity": 1, "price": 8999},
            {"name": "タオルセット", "quantity": 1, "price": 4999},
            {"name": "クッション", "quantity": 2, "price": 2499},
        ],
        "total": 18996,
        "payment_method": "クレジットカード",
        "shipping_address": "東京都渋谷区渋谷1-1-1",
    }

    # 注文をデータベースに追加
    order1_id = db.add_order(customer_id, order1)
    logger.info(f"注文 #{order1_id} を追加: 電子機器 - 合計: ¥{order1['total']}")

    order2_id = db.add_order(customer_id, order2)
    logger.info(f"注文 #{order2_id} を追加: 衣類 - 合計: ¥{order2['total']}")

    order3_id = db.add_order(customer_id, order3)
    logger.info(f"注文 #{order3_id} を追加: 家庭用品 - 合計: ¥{order3['total']}")

    # 注文が追加されたことを確認
    order_history = db.get_customer_order_history(first_name, last_name)
    logger.info(f"{last_name} {first_name}様の注文履歴:\n{order_history}")

    return order1_id, order2_id, order3_id


if __name__ == "__main__":
    order_ids = add_test_orders()
    print(f"テスト注文を追加しました。注文ID: {order_ids}")
    print("山田太郎様と鈴木花子様のテスト注文の追加が完了しました。")
