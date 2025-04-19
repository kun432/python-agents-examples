import logging
from dataclasses import dataclass, field

from dotenv import load_dotenv
from utils import load_prompt

from livekit.agents import JobContext, WorkerOptions, cli
from livekit.agents.llm import function_tool
from livekit.agents.voice import Agent, AgentSession, RunContext
from livekit.plugins import openai, silero

logger = logging.getLogger("medical-office-triage")
logger.setLevel(logging.INFO)

load_dotenv()


@dataclass
class UserData:
    """セッションをまたいでデータとエージェントを共有するためのデータクラス"""

    personas: dict[str, Agent] = field(default_factory=dict)
    prev_agent: Agent | None = None
    ctx: JobContext | None = None

    def summarize(self) -> str:
        return "ユーザーデータ: 医療機関窓口振り分けシステム"


RunContext_T = RunContext[UserData]


class BaseAgent(Agent):
    async def on_enter(self) -> None:
        agent_name = self.__class__.__name__
        logger.info(f"{agent_name} エージェントが開始されました")

        userdata: UserData = self.session.userdata
        if userdata.ctx and userdata.ctx.room:
            await userdata.ctx.room.local_participant.set_attributes({"agent": agent_name})

        chat_ctx = self.chat_ctx.copy()

        if userdata.prev_agent:
            items_copy = self._truncate_chat_ctx(userdata.prev_agent.chat_ctx.items, keep_function_call=True)
            existing_ids = {item.id for item in chat_ctx.items}
            items_copy = [item for item in items_copy if item.id not in existing_ids]
            chat_ctx.items.extend(items_copy)

        chat_ctx.add_message(role="system", content=f"あなたは、{agent_name} です。{userdata.summarize()}")
        await self.update_chat_ctx(chat_ctx)
        self.session.generate_reply()

    def _truncate_chat_ctx(
        self,
        items: list,
        keep_last_n_messages: int = 6,
        keep_system_message: bool = False,
        keep_function_call: bool = False,
    ) -> list:
        """最後のn個のメッセージを保持するためにチャットコンテキストを切り捨てる"""

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
        """コンテキストを保持しながら別のエージェントに転送する"""
        userdata = context.userdata
        current_agent = context.session.current_agent
        next_agent = userdata.personas[name]
        userdata.prev_agent = current_agent

        return next_agent


class TriageAgent(BaseAgent):
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
    async def transfer_to_support(self, context: RunContext_T) -> Agent:
        await self.session.say(
            "医療サービスに関するご用件については、患者サポートチームがお手伝いしますので、そちらにおつなぎします。"
        )
        return await self._transfer_to_agent("support", context)

    @function_tool
    async def transfer_to_billing(self, context: RunContext_T) -> Agent:
        await self.session.say(
            "保険やお支払いに関するご質問には、医療費請求部門が対応いたしますので、そちらにおつなぎします。"
        )
        return await self._transfer_to_agent("billing", context)


class SupportAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(
            instructions=load_prompt("support_prompt.yaml"),
            # stt=deepgram.STT(),
            stt=openai.STT(model="gpt-4o-mini-transcribe", language="ja"),
            llm=openai.LLM(model="gpt-4o-mini"),
            # tts=cartesia.TTS(),
            tts=openai.TTS(model="gpt-4o-mini-tts", voice="ballad"),
            vad=silero.VAD.load(),
        )

    @function_tool
    async def transfer_to_triage(self, context: RunContext_T) -> Agent:
        await self.session.say("ご用件をより適切にご案内できるよう、医療窓口の振り分け担当にお戻しします。")
        return await self._transfer_to_agent("triage", context)

    @function_tool
    async def transfer_to_billing(self, context: RunContext_T) -> Agent:
        await self.session.say(
            "保険やお支払いに関するご質問には、医療費請求部門が対応いたしますので、そちらにおつなぎします。"
        )
        return await self._transfer_to_agent("billing", context)


class BillingAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(
            instructions=load_prompt("billing_prompt.yaml"),
            # stt=deepgram.STT(),
            stt=openai.STT(model="gpt-4o-mini-transcribe", language="ja"),
            llm=openai.LLM(model="gpt-4o-mini"),
            # tts=cartesia.TTS(),
            tts=openai.TTS(model="gpt-4o-mini-tts", voice="coral"),
            vad=silero.VAD.load(),
        )

    @function_tool
    async def transfer_to_triage(self, context: RunContext_T) -> Agent:
        await self.session.say("ご用件をより適切にご案内できるよう、医療窓口の振り分け担当にお戻しします。")
        return await self._transfer_to_agent("triage", context)

    @function_tool
    async def transfer_to_support(self, context: RunContext_T) -> Agent:
        await self.session.say(
            "医療サービスに関するご用件については、患者サポートチームがお手伝いしますので、そちらにおつなぎします。"
        )
        return await self._transfer_to_agent("support", context)


async def entrypoint(ctx: JobContext):
    await ctx.connect()

    userdata = UserData(ctx=ctx)
    triage_agent = TriageAgent()
    support_agent = SupportAgent()
    billing_agent = BillingAgent()

    # すべてのエージェントをユーザーデータに登録
    userdata.personas.update({"triage": triage_agent, "support": support_agent, "billing": billing_agent})

    session = AgentSession[UserData](userdata=userdata)

    await session.start(
        agent=triage_agent,  # 医療窓口振り分けエージェントから開始
        room=ctx.room,
    )


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
