import logging
from dataclasses import dataclass, field

from database import CustomerDatabase
from dotenv import load_dotenv
from utils import load_prompt

from livekit.agents import JobContext, WorkerOptions, cli
from livekit.agents.llm import function_tool
from livekit.agents.voice import Agent, AgentSession, RunContext
from livekit.plugins import openai, silero

logger = logging.getLogger("personal-shopper")
logger.setLevel(logging.INFO)

load_dotenv()

# 顧客データベースの初期化
db = CustomerDatabase()


@dataclass
class UserData:
    """通話中のユーザーデータとエージェントを格納するクラス。"""

    personas: dict[str, Agent] = field(default_factory=dict)
    prev_agent: Agent | None = None
    ctx: JobContext | None = None

    # 顧客情報
    first_name: str | None = None
    last_name: str | None = None
    customer_id: str | None = None
    current_order: dict | None = None

    def is_identified(self) -> bool:
        """顧客が識別されているかどうかを確認します。"""
        return self.first_name is not None and self.last_name is not None

    def reset(self) -> None:
        """顧客情報をリセットします。"""
        self.first_name = None
        self.last_name = None
        self.customer_id = None
        self.current_order = None

    def summarize(self) -> str:
        """ユーザーデータの要約を返します。"""
        if self.is_identified():
            return f"顧客: {self.first_name} {self.last_name} (ID: {self.customer_id})"
        return "顧客はまだ識別されていません。"


RunContext_T = RunContext[UserData]


class BaseAgent(Agent):
    async def on_enter(self) -> None:
        agent_name = self.__class__.__name__
        logger.info(f"エージェント {agent_name} に入りました")

        userdata: UserData = self.session.userdata
        if userdata.ctx and userdata.ctx.room:
            await userdata.ctx.room.local_participant.set_attributes({"agent": agent_name})

        # 顧客識別に基づいてパーソナライズされたプロンプトを作成
        custom_instructions = self.instructions
        if userdata.is_identified():
            custom_instructions += f"\n\n{userdata.last_name} {userdata.first_name}様と会話しています。"

        chat_ctx = self.chat_ctx.copy()

        # 前のエージェントが存在する場合は、そのコンテキストをコピー
        if userdata.prev_agent:
            items_copy = self._truncate_chat_ctx(userdata.prev_agent.chat_ctx.items, keep_function_call=True)
            existing_ids = {item.id for item in chat_ctx.items}
            items_copy = [item for item in items_copy if item.id not in existing_ids]
            chat_ctx.items.extend(items_copy)

        chat_ctx.add_message(role="system", content=f"あなたは {agent_name} です。{userdata.summarize()}")
        await self.update_chat_ctx(chat_ctx)
        self.session.generate_reply()

    def _truncate_chat_ctx(
        self,
        items: list,
        keep_last_n_messages: int = 6,
        keep_system_message: bool = False,
        keep_function_call: bool = False,
    ) -> list:
        """チャットコンテキストを最後のnメッセージまで切り詰めます。"""

        def _valid_item(item) -> bool:
            if not keep_system_message and item.type == "message" and item.role == "system":
                return False
            if not keep_function_call and item.type in ["function_call", "function_call_output"]:
                return False
            return True

        new_items = []
        for item in reversed(items):
            if _valid_item(item):
                new_items.append(item)
            if len(new_items) >= keep_last_n_messages:
                break
        new_items = new_items[::-1]

        while new_items and new_items[0].type in ["function_call", "function_call_output"]:
            new_items.pop(0)

        return new_items

    async def _transfer_to_agent(self, name: str, context: RunContext_T) -> Agent:
        """コンテキストを保持しながら別のエージェントに転送します。"""
        userdata = context.userdata
        current_agent = context.session.current_agent
        next_agent = userdata.personas[name]
        userdata.prev_agent = current_agent

        return next_agent


class TriageAgent(BaseAgent):
    """受付エージェント。顧客の問い合わせを適切なエージェントに振り分けます。"""

    def __init__(self) -> None:
        super().__init__(
            instructions=load_prompt("triage_prompt.yaml"),
            # stt=deepgram.STT(),
            stt=openai.STT(model="gpt-4o-mini-transcribe", language="ja"),
            llm=openai.LLM(model="gpt-4o-mini"),
            # tts=cartesia.TTS(),
            tts=openai.TTS(model="gpt-4o-mini-tts", voice="ash"),
            vad=silero.VAD.load(),
        )

    @function_tool
    async def identify_customer(self, first_name: str, last_name: str):
        """
        顧客を姓と名で識別します。

        Args:
            first_name: 顧客の名
            last_name: 顧客の姓
        """
        userdata: UserData = self.session.userdata
        userdata.first_name = first_name
        userdata.last_name = last_name
        userdata.customer_id = db.get_or_create_customer(first_name, last_name)

        return f"{first_name}様、ご登録ありがとうございます。アカウントを確認しました。"

    @function_tool
    async def transfer_to_sales(self, context: RunContext_T) -> Agent:
        # 顧客が識別されている場合は、パーソナライズされたメッセージを作成
        userdata: UserData = self.session.userdata
        if userdata.is_identified():
            message = (
                f"{userdata.first_name}様、販売担当者におつなぎいたします。お客様にぴったりの商品をご案内いたします。"
            )
        else:
            message = "販売担当者におつなぎいたします。お客様にぴったりの商品をご案内いたします。"

        await self.session.say(message)
        return await self._transfer_to_agent("sales", context)

    @function_tool
    async def transfer_to_returns(self, context: RunContext_T) -> Agent:
        # 顧客が識別されている場合は、パーソナライズされたメッセージを作成
        userdata: UserData = self.session.userdata
        if userdata.is_identified():
            message = f"{userdata.first_name}様、返品・交換担当者におつなぎいたします。返品・交換のご案内をいたします。"
        else:
            message = "返品・交換担当者におつなぎいたします。返品・交換のご案内をいたします。"

        await self.session.say(message)
        return await self._transfer_to_agent("returns", context)


class SalesAgent(BaseAgent):
    """販売担当エージェント。顧客の注文を処理し、商品の案内を行います。"""

    def __init__(self) -> None:
        super().__init__(
            instructions=load_prompt("sales_prompt.yaml"),
            # stt=deepgram.STT(),
            stt=openai.STT(model="gpt-4o-mini-transcribe", language="ja"),
            llm=openai.LLM(model="gpt-4o-mini"),
            # tts=cartesia.TTS(),
            tts=openai.TTS(model="gpt-4o-mini-tts", voice="ballad"),
            vad=silero.VAD.load(),
        )

    @function_tool
    async def identify_customer(self, first_name: str, last_name: str):
        """
        顧客を姓と名で識別します。

        Args:
            first_name: 顧客の名
            last_name: 顧客の姓
        """
        userdata: UserData = self.session.userdata
        userdata.first_name = first_name
        userdata.last_name = last_name
        userdata.customer_id = db.get_or_create_customer(first_name, last_name)

        return f"{first_name}様、ご登録ありがとうございます。アカウントを確認しました。"

    @function_tool
    async def start_order(self):
        """顧客の新しい注文を開始します。"""
        userdata: UserData = self.session.userdata
        if not userdata.is_identified():
            return "まずは identify_customer 関数を使用して顧客識別を行ってください。"

        userdata.current_order = {"items": []}

        return "新しい注文を開始しました。何をお求めでしょうか？"

    @function_tool
    async def add_item_to_order(self, item_name: str, quantity: int, price: float):
        """
        現在の注文に商品を追加します。

        Args:
            item_name: 商品名
            quantity: 購入数量
            price: 商品単価
        """
        userdata: UserData = self.session.userdata
        if not userdata.is_identified():
            return "まずは identify_customer 関数を使用して顧客識別を行ってください。"

        if not userdata.current_order:
            userdata.current_order = {"items": []}

        item = {"name": item_name, "quantity": quantity, "price": price}

        userdata.current_order["items"].append(item)

        return f"注文に{quantity}個の{item_name}を追加しました。"

    @function_tool
    async def complete_order(self):
        """現在の注文を完了し、データベースに保存します。"""
        userdata: UserData = self.session.userdata
        if not userdata.is_identified():
            return "まずは identify_customer 関数を使用して顧客識別を行ってください。"

        if not userdata.current_order or not userdata.current_order.get("items"):
            return "現在の注文に商品が含まれていません。"

        # 注文合計を計算
        total = sum(item["price"] * item["quantity"] for item in userdata.current_order["items"])
        userdata.current_order["total"] = total

        # データベースに注文を保存
        order_id = db.add_order(userdata.customer_id, userdata.current_order)

        # 注文の要約を作成
        summary = f"注文番号 #{order_id} が完了しました。合計金額: ¥{total:,.0f}\n"
        summary += "注文内容:\n"
        for item in userdata.current_order["items"]:
            summary += f"- {item['quantity']}個 x {item['name']} (¥{item['price']} 個あたり)\n"

        # 現在の注文をリセット
        userdata.current_order = None

        return summary

    @function_tool
    async def transfer_to_triage(self, context: RunContext_T) -> Agent:
        # 顧客が識別されている場合は、パーソナライズされたメッセージを作成
        userdata: UserData = self.session.userdata
        if userdata.is_identified():
            message = f"{userdata.first_name}様、受付担当者におつなぎいたします。"
        else:
            message = "受付担当者におつなぎいたします。"

        await self.session.say(message)
        return await self._transfer_to_agent("triage", context)

    @function_tool
    async def transfer_to_returns(self, context: RunContext_T) -> Agent:
        # 顧客が識別されている場合は、パーソナライズされたメッセージを作成
        userdata: UserData = self.session.userdata
        if userdata.is_identified():
            message = f"{userdata.first_name}様、返品・交換担当者におつなぎいたします。"
        else:
            message = "返品・交換担当者におつなぎいたします。"

        await self.session.say(message)
        return await self._transfer_to_agent("returns", context)


class ReturnsAgent(BaseAgent):
    """返品・交換担当エージェント。顧客の返品・交換を処理します。"""

    def __init__(self) -> None:
        super().__init__(
            instructions=load_prompt("returns_prompt.yaml"),
            # stt=deepgram.STT(),
            stt=openai.STT(model="gpt-4o-mini-transcribe", language="ja"),
            llm=openai.LLM(model="gpt-4o-mini"),
            # tts=cartesia.TTS(),
            tts=openai.TTS(model="gpt-4o-mini-tts", voice="coral"),
            vad=silero.VAD.load(),
        )

    @function_tool
    async def identify_customer(self, first_name: str, last_name: str):
        """
        顧客を姓と名で識別します。

        Args:
            first_name: 顧客の名
            last_name: 顧客の姓
        """
        userdata: UserData = self.session.userdata
        userdata.first_name = first_name
        userdata.last_name = last_name
        userdata.customer_id = db.get_or_create_customer(first_name, last_name)

        return f"{first_name}様、ご登録ありがとうございます。アカウントを確認しました。"

    @function_tool
    async def get_order_history(self):
        """現在の顧客の注文履歴を取得します。"""
        userdata: UserData = self.session.userdata
        if not userdata.is_identified():
            return "まずは identify_customer 関数を使用して顧客識別を行ってください。"

        order_history = db.get_customer_order_history(userdata.first_name, userdata.last_name)
        return order_history

    @function_tool
    async def process_return(self, order_id: int, item_name: str, reason: str):
        """
        特定の注文からの商品の返品を処理します。

        Args:
            order_id: 返品する商品が含まれる注文のID
            item_name: 返品する商品名
            reason: 返品理由
        """
        userdata: UserData = self.session.userdata
        if not userdata.is_identified():
            return "まずは identify_customer 関数を使用して顧客識別を行ってください。"

        # 実際のシステムでは、データベースの注文を更新します
        # この例では、確認メッセージを返すだけです
        return (
            f"注文番号 #{order_id} の {item_name} の返品を処理しました。理由: {reason}。"
            "返金は3-5営業日以内に処理されます。"
        )

    @function_tool
    async def transfer_to_triage(self, context: RunContext_T) -> Agent:
        # 顧客が識別されている場合は、パーソナライズされたメッセージを作成
        userdata: UserData = self.session.userdata
        if userdata.is_identified():
            message = f"{userdata.first_name}様、受付担当者におつなぎいたします。"
        else:
            message = "受付担当者におつなぎいたします。"

        await self.session.say(message)
        return await self._transfer_to_agent("triage", context)

    @function_tool
    async def transfer_to_sales(self, context: RunContext_T) -> Agent:
        # 顧客が識別されている場合は、パーソナライズされたメッセージを作成
        userdata: UserData = self.session.userdata
        if userdata.is_identified():
            message = f"{userdata.first_name}様、販売担当者におつなぎいたします。新しい商品をご案内いたします。"
        else:
            message = "販売担当者におつなぎいたします。新しい商品をご案内いたします。"

        await self.session.say(message)
        return await self._transfer_to_agent("sales", context)


async def entrypoint(ctx: JobContext):
    await ctx.connect()

    # コンテキストを使用してユーザーデータを初期化
    userdata = UserData(ctx=ctx)

    # エージェントインスタンスの作成
    triage_agent = TriageAgent()
    sales_agent = SalesAgent()
    returns_agent = ReturnsAgent()

    # すべてのエージェントをユーザーデータに登録
    userdata.personas.update({"triage": triage_agent, "sales": sales_agent, "returns": returns_agent})

    # ユーザーデータを使用してセッションを作成
    session = AgentSession[UserData](userdata=userdata)

    await session.start(
        agent=triage_agent,  # 受付エージェントから開始
        room=ctx.room,
    )


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
