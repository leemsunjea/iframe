import os
import json
import typing
import asyncio
from typing import Optional
from fastapi import FastAPI, Request, Query, Body
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from typing import Optional
import requests
import logging
from datetime import datetime
from openai import OpenAI
from sse_starlette.sse import EventSourceResponse

# 환경 변수 로딩 및 API 초기화
from dotenv import load_dotenv
load_dotenv()

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

client = OpenAI()  # api_key 인자 없이 환경변수 사용

# FastAPI 앱 및 템플릿 설정
app = FastAPI()
templates = Jinja2Templates(directory="templates")

# 프롬프트
PROMPT = """안녕하세요! 저는 고객 상담을 도와주는 챗봇입니다.
궁금한 점이나 도움이 필요하시면 언제든지 말씀해 주세요.
"""

# 루트 페이지 (챗봇 UI 페이지)
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    logger.info("[index] Serving chat.html to client")
    return templates.TemplateResponse("chat.html", {"request": request})

# 스트리밍 응답 생성 함수
async def stream_chat_response(user_input: str, history: list, session_id: Optional[str] = None):
    logger.info(f"[stream_chat_response] user_input: {user_input}, session_id: {session_id}")
    try:
        messages = [{"role": "system", "content": PROMPT}]
        for h in history:
            if isinstance(h, dict) and "role" in h and "content" in h:
                messages.append({"role": h["role"], "content": h["content"]})
            else:
                messages.append({"role": "user", "content": str(h)})
        messages.append({"role": "user", "content": user_input})
        logger.info(f"[stream_chat_response] messages: {messages}")
        response_stream = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=typing.cast(list, messages),
            stream=True
        )
        for chunk in response_stream:
            if chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content.replace("\n", "<br>")
                yield content
            await asyncio.sleep(0)
    except Exception as e:
        logger.error(f"[stream_chat_response] Error: {e}")
        yield f"<span style='color:red;'>에러 발생: {str(e)}</span>"

# SSE 기반 채팅 API
@app.get("/chat")
async def chat(
    message: str,
    session_id: Optional[str] = Query(None),
    history: Optional[str] = Query(None)
):
    logger.info(f"[/chat] message: {message}, session_id: {session_id}, history: {history}")
    try:
        history_list = json.loads(history) if history else []
    except Exception as e:
        logger.warning(f"[/chat] Failed to parse history: {e}")
        history_list = []
    return EventSourceResponse(stream_chat_response(message, history_list, session_id))

# 상담원 메시지 저장 (메모리)
agent_messages: list[dict] = []
N8N_WEBHOOK: str = os.getenv("N8N_WEBHOOK", "https://sunjea1149.app.n8n.cloud/webhook/chat-relay")

# ---------- 상담원: 프런트에서 메시지 보냄 → n8n Webhook 호출 ----------
@app.post("/send")
async def send_agent_message(data: dict = Body(...)):
    logger.info(f"[/send] data: {data}")
    if not data.get("session_id"):
        logger.warning("[/send] session_id is missing")
        return JSONResponse({"status": "error", "detail": "session_id is required"}, status_code=400)
    if not data.get("message"):
        logger.warning("[/send] message is missing")
        return JSONResponse({"status": "error", "detail": "message is required"}, status_code=400)
    try:
        response = requests.post(N8N_WEBHOOK, json=data, timeout=5)
        logger.info(f"[/send] Forwarded to N8N_WEBHOOK, status: {response.status_code}, response: {response.text}")
        response.raise_for_status()
    except Exception as e:
        logger.error(f"[/send] Error sending to N8N_WEBHOOK: {e}")
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=502)
    return {"status": "sent"}

# ---------- 상담원: n8n에서 메시지 받음 → 프런트로 보여주기 위해 저장 ----------
@app.post("/incoming-message")
async def incoming_message(data: dict = Body(...)):
    logger.info(f"[/incoming-message] data: {data}")
    if not data.get("session_id"):
        logger.warning("[/incoming-message] session_id is missing")
        return JSONResponse({"status": "error", "detail": "session_id is required"}, status_code=400)
    data["ts"] = datetime.utcnow().isoformat()
    data["from"] = "agent"  # 반드시 추가!
    agent_messages.append(data)
    logger.info(f"[/incoming-message] Message stored in memory: {data}")
    return {"status": "stored"}

# ---------- 상담원: 프런트가 메시지 조회 ----------
@app.get("/messages")
async def get_agent_messages(session_id: Optional[str] = Query(None)):
    logger.info(f"[/messages] session_id: {session_id}")
    if not session_id:
        logger.warning("[/messages] session_id is missing, returning empty list")
        return []
    messages = [m for m in agent_messages if m.get("session_id") == session_id]
    logger.info(f"[/messages] Returning {len(messages[-50:])} messages from memory")
    return messages[-50:]