import json
import logging
import os
import sqlite3
from typing import Any

logger = logging.getLogger("personal-shopper-db")
logger.setLevel(logging.INFO)


class CustomerDatabase:
    def __init__(self, db_path: str = None):
        """顧客データベースを初期化します。"""
        if db_path is None:
            # このファイルと同じディレクトリにデフォルトのパスを使用
            script_dir = os.path.dirname(os.path.abspath(__file__))
            db_path = os.path.join(script_dir, "customer_data_ja.db")

        self.db_path = db_path
        self._initialize_db()

    def _initialize_db(self):
        """データベースとテーブルが存在しない場合は作成します。"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # customersテーブルを作成
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # ordersテーブルを作成
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            order_details TEXT NOT NULL,
            order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers (id)
        )
        """)

        conn.commit()
        conn.close()
        logger.info(f"データベースを初期化しました: {self.db_path}")

    def get_or_create_customer(self, first_name: str, last_name: str) -> int:
        """
        顧客を名前で検索し、存在しない場合は新規作成します。顧客IDを返します。

        Args:
            first_name: 顧客の名
            last_name: 顧客の姓

        Returns:
            int: 顧客ID
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 顧客が存在するか確認
        cursor.execute("SELECT id FROM customers WHERE first_name = ? AND last_name = ?", (first_name, last_name))
        result = cursor.fetchone()

        if result:
            customer_id = result[0]
            logger.info(f"既存の顧客が見つかりました: {last_name} {first_name} (ID: {customer_id})")
        else:
            # 新規顧客を作成
            cursor.execute("INSERT INTO customers (first_name, last_name) VALUES (?, ?)", (first_name, last_name))
            customer_id = cursor.lastrowid
            logger.info(f"新規顧客を作成しました: {last_name} {first_name} (ID: {customer_id})")

        conn.commit()
        conn.close()
        return customer_id

    def add_order(self, customer_id: int, order_details: dict[str, Any]) -> int:
        """
        顧客の新規注文を追加します。注文IDを返します。

        Args:
            customer_id: 顧客ID
            order_details: 注文の詳細情報を含む辞書

        Returns:
            int: 注文ID
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 注文詳細をJSON文字列に変換
        order_json = json.dumps(order_details)

        cursor.execute("INSERT INTO orders (customer_id, order_details) VALUES (?, ?)", (customer_id, order_json))

        order_id = cursor.lastrowid
        logger.info(f"顧客ID: {customer_id} の新規注文 (ID: {order_id}) を追加しました")

        conn.commit()
        conn.close()
        return order_id

    def get_customer_orders(self, customer_id: int) -> list[dict[str, Any]]:
        """
        顧客の全注文を取得します。

        Args:
            customer_id: 顧客ID

        Returns:
            List[Dict[str, Any]]: 注文情報のリスト
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # カラム名でアクセスできるようにする
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id, order_details, order_date FROM orders WHERE customer_id = ? ORDER BY order_date DESC",
            (customer_id,),
        )

        orders = []
        for row in cursor.fetchall():
            order_data = json.loads(row["order_details"])
            orders.append({"id": row["id"], "date": row["order_date"], "details": order_data})

        conn.close()
        return orders

    def get_customer_order_history(self, first_name: str, last_name: str) -> str:
        """
        顧客の注文履歴を取得し、LLM用にフォーマットした文字列を返します。

        Args:
            first_name: 顧客の名
            last_name: 顧客の姓

        Returns:
            str: フォーマットされた注文履歴
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # 顧客IDを取得
        cursor.execute("SELECT id FROM customers WHERE first_name = ? AND last_name = ?", (first_name, last_name))
        result = cursor.fetchone()

        if not result:
            conn.close()
            return "この顧客の注文履歴は見つかりませんでした。"

        customer_id = result[0]
        orders = self.get_customer_orders(customer_id)

        if not orders:
            return f"顧客 {last_name} {first_name} の注文履歴はありません。"

        # 注文履歴をフォーマット
        history = f"顧客 {last_name} {first_name} の注文履歴:\n\n"

        for order in orders:
            history += f"注文 #{order['id']} (日時: {order['date']}):\n"
            details = order["details"]

            if "items" in details:
                for item in details["items"]:
                    history += f"- {item.get('quantity', 1)}x {item.get('name', '不明な商品')}"
                    if "price" in item:
                        history += f" (¥{item['price']})"
                    history += "\n"
            else:
                # 注文詳細が異なるフォーマットの場合の処理
                history += f"- {json.dumps(details)}\n"

            history += "\n"

        conn.close()
        return history
