# app.py
import json
import httpx
from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

URL = "https://signal.beboundless.xyz/prove/leaderboard"

app = FastAPI(title="Leaderboard JSON API")

async def fetch_html() -> str:
    async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0"}) as client:
        r = await client.get(URL, timeout=20)
        r.raise_for_status()
        return r.text

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

def cut_all_json_blocks(raw: str) -> List[str]:
    """
    HTML 안에서 JSON 블록( {"success"...} )을 모두 잘라 리스트로 반환.
    - 평문(JSON 그대로)과 이스케이프된 경우( \"success\" ) 모두 지원.
    - 이스케이프된 경우 unicode_escape 로 역-이스케이프.
    """
    blocks: List[str] = []

    # 1) 평문 JSON 스캔
    idx = 0
    while True:
        i = raw.find('{"success"', idx)
        if i == -1:
            break
        cut = _brace_cut(raw, i)
        blocks.append(cut)
        idx = i + 1

    # 2) 이스케이프 JSON 스캔
    idx = 0
    while True:
        i = raw.find('{\\\"success\\\"', idx)
        if i == -1:
            break
        cut = _brace_cut(raw, i)
        # 역-이스케이프
        unescaped = bytes(cut, "utf-8").decode("unicode_escape")
        blocks.append(unescaped)
        idx = i + 1

    if not blocks:
        raise ValueError("Can't find any JSON blocks starting with {\"success\"")
    return blocks

def parse_seasons(raw_html: str) -> List[Dict[str, Any]]:
    """
    HTML에서 시즌 JSON들을 파싱하여 리스트로 반환.
    각 아이템은 원본 JSON(dict)에 'seasonNumber' 를 추가한다.
    """
    json_str_list = cut_all_json_blocks(raw_html)
    seasons: List[Dict[str, Any]] = []
    for s in json_str_list:
        data = json.loads(s)
        # season: "Season 1" 같은 문자열이므로 숫자만 추출 시도
        season_text: Optional[str] = data.get("season")
        season_num: Optional[int] = None
        if isinstance(season_text, str):
            # "Season X" 패턴
            try:
                season_num = int(season_text.split()[-1])
            except Exception:
                season_num = None
        data["seasonNumber"] = season_num
        seasons.append(data)

    # 최신이 먼저 오도록 정렬:
    # 1) endDate == None (현재 진행중) 우선
    # 2) 그 다음 startDate 내림차순
    def parse_dt(s: Optional[str]) -> datetime:
        # 예: "2025-08-20 04:00:00"
        if not s:
            return datetime.min
        try:
            return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
        except Exception:
            return datetime.min

    seasons.sort(
        key=lambda d: (
            d.get("endDate") is not None,                 # False(진행중) < True(종료)
            -parse_dt(d.get("startDate")).timestamp(),    # 시작일 최신 우선
        )
    )
    return seasons

@app.get("/leaderboard")
async def leaderboard_all():
    try:
        html = await fetch_html()
        seasons = parse_seasons(html)
        return JSONResponse(content=seasons)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"HTTP error: {e}")
    except (ValueError, json.JSONDecodeError) as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/leaderboard/latest")
async def leaderboard_latest():
    try:
        html = await fetch_html()
        seasons = parse_seasons(html)
        return JSONResponse(content=seasons[0])
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"HTTP error: {e}")
    except (ValueError, json.JSONDecodeError, IndexError) as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/leaderboard/season/{season_no}")
async def leaderboard_by_season(season_no: int):
    try:
        html = await fetch_html()
        seasons = parse_seasons(html)
        for s in seasons:
            # 우선 숫자 매칭
            if s.get("seasonNumber") == season_no:
                return JSONResponse(content=s)
            # 숫자 파싱이 실패했을 수도 있으니 문자열 비교도 지원
            if s.get("season") == f"Season {season_no}":
                return JSONResponse(content=s)
        raise HTTPException(status_code=404, detail=f"Season {season_no} not found")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"HTTP error: {e}")
    except (ValueError, json.JSONDecodeError) as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def root():
    return {
        "message": "Use /leaderboard (all), /leaderboard/latest, or /leaderboard/season/{n}"
    }
