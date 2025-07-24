# app.py
import json
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

URL = "https://signal.beboundless.xyz/prove/leaderboard"

app = FastAPI(title="Leaderboard JSON API")

async def fetch_html() -> str:
    async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0"}) as client:
        r = await client.get(URL, timeout=20)
        r.raise_for_status()
        return r.text

def cut_json_block(raw: str, anchor='{"success"'):
    """
    anchor 로 시작하는 JSON 객체(중괄호 밸런싱)만 깔끔히 잘라낸다.
    - HTML 안에 이스케이프된 문자열("...{\"success\"...}")일 수도 있으므로 1차로 그 부분을 뽑아낸 뒤
      필요한 경우 unicode_escape 디코딩을 한 번 더 한다.
    """
    idx = raw.find(anchor)
    if idx == -1:
        # 문자열 자체가 \"success\" 로 이스케이프 되어 있는 경우를 다시 탐색
        esc_idx = raw.find('{\\\"success\\\"')
        if esc_idx == -1:
            raise ValueError("Can't find JSON starting with {\"success\"")
        # 이 경우 뽑아낸 뒤 unicode_escape 로 역-이스케이프 후 다시 파싱
        json_esc = _brace_cut(raw, esc_idx)
        # 역이스케이프
        json_unescaped = bytes(json_esc, "utf-8").decode("unicode_escape")
        return json_unescaped
    # 그냥 평문 JSON이면 바로 잘라낸다
    return _brace_cut(raw, idx)

def _brace_cut(text: str, start_idx: int) -> str:
    """start_idx 에서 시작하는 { ... } 블록을 중괄호 개수로 찾아 문자열로 반환"""
    depth = 0
    in_str = False
    escape = False
    for i in range(start_idx, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == '\\':
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
        if not in_str:
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return text[start_idx:i+1]
    raise ValueError("Unbalanced braces, couldn't cut JSON")

@app.get("/leaderboard")
async def leaderboard():
    try:
        html = await fetch_html()
        json_str = cut_json_block(html)               # 문자열
        data = json.loads(json_str)                   # dict로 파싱
        return JSONResponse(content=data)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"HTTP error: {e}")
    except (ValueError, json.JSONDecodeError) as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def root():
    return {"message": "GET /leaderboard 로 호출하세요."}
