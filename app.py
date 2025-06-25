import os
import json
import typing
import asyncio
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sse_starlette.sse import EventSourceResponse
from openai import OpenAI

# 환경 변수 로딩 및 API 초기화
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# FastAPI 앱 및 템플릿 설정
app = FastAPI()
templates = Jinja2Templates(directory="templates")

# 프롬프트
PROMPT = """
당신은 친절한 AI 챗봇입니다. 사용자의 질문에 성실하게 답변하세요. 응답은 항상 마크다운 형식으로 작성하세요.

당신은 아래의 FAQ와 회사 데이터를 기반으로 사용자의 질문에 답변할 수 있어야 합니다:

---

[고릴라51의 의미와 기원]  
• 브랜드명 ‘Gorilla51’은 고릴라의 지능과 힘을 상징하며, 미국의 비밀 기지 Area 51에서 착안해 우주와 음모론적 세계관을 결합한 브랜드입니다.  
• 설립일은 2025년 5월 1일. 화성 정착 프로젝트에 참여한 고릴라들에 의해 시작되었습니다.

[화성과의 연관성]  
• Gorilla51은 화성의 극한 환경에서 얻은 생존 기술(방사선, 저온, 저압 대응)을 지구로 전파한 혁신 기업입니다.  
• 화성 유적에서 영감을 받은 창의적 제품 개발을 이어가고 있으며, 해당 내용은 웹툰 및 제품 세계관에도 포함되어 있습니다.

[주요 제품]  
• 제품명: GORILLA51™ Tag & Skin Cover Film  
• 용도: 의류 태그로 인한 가려움증 방지  
• 구성: PET, PU 필름, 이형지 / 사이즈 90x90, 60x60, 30x90mm  
• 특징: 피부 자극 최소화 / 강아지, 고양이, 어린이, 성인 모두 사용 가능 / 세탁 시 제거 필요 / 재부착 불가  
• 특허번호: 10-2025-0075297  
• 고객센터: 070-4519-6451

[게임: Gorilla51 Space Adventure]  
• 플랫폼: Android, iOS, Telegram  
• 장르: 캐주얼 액션 퍼즐  
• 내용: 라벨로 인해 화성에서 광폭화한 승무원 구조 미션  
• 구성: 4개 스테이지, 캐릭터 커스터마이징, 신제품 출시 연동  
• 보상: 할인쿠폰, 한정판 고릴라51 우주 키트 제공  
• 정책: 12세 이상 / 7일 이내 환불 가능 / TTA 기준 개인정보 보호

[가상 밴드: Gorilla51 Music Band]  
• 장르: Hip Hop & Funky with a Cosmic Twist  
• 구성원: Goro(리더), Bana(밈마스터), Chrome(비트 메이커)  
• 활동: SNS 밈 챌린지, 유튜브/스포티파이 음원 발매 예정

[웹툰: GORILLA51]  
• 장르: SF, 음모론  
• 주요 스토리: 51구역 탈출 → 화성 유적 발견 → 지구-화성 갈등  
• 주요 인물: Goro, Musk, Dr. Rhea, Alien X

[사이트 및 정책]  
• 웹사이트: www.gorilla51.com  
• 개인정보: 암호화 저장, 제3자 미제공  
• 커뮤니티 운영: 부정적 피드백은 고객센터(Mars@gorilla51.com)로 이관  
• 배송: 국내 2~5일 / 해외 7~14일  
• 환불: 미사용 제품 7일 이내 가능  
• 고객센터 운영시간: 평일 09:00~18:00 (KST)

---

사용자가 위 내용과 관련된 질문을 하면 항상 논리적이고 명확하게 응답하세요.  
불확실하거나 정보가 부족할 경우, "현재 제공된 정보로는 정확한 답변이 어렵습니다. 자세한 내용은 www.gorilla51.com을 참고하세요."라고 안내하세요.
"""

# 루트 페이지 (챗봇 UI 페이지)
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# 스트리밍 응답 생성 함수
async def stream_chat_response(user_input: str, history: list, session_id: Optional[str] = None):
    try:
        messages = [{"role": "system", "content": PROMPT}]
        for h in history:
            if isinstance(h, dict) and "role" in h and "content" in h:
                messages.append({"role": h["role"], "content": h["content"]})
            else:
                messages.append({"role": "user", "content": str(h)})
        messages.append({"role": "user", "content": user_input})

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
        yield f"<span style='color:red;'>에러 발생: {str(e)}</span>"

# SSE 기반 채팅 API
@app.get("/chat")
async def chat(
    message: str,
    session_id: Optional[str] = Query(None),
    history: Optional[str] = Query(None)
):
    try:
        history_list = json.loads(history) if history else []
    except Exception:
        history_list = []
    return EventSourceResponse(stream_chat_response(message, history_list, session_id))