from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from ddgs import DDGS
import re
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def index():
    return FileResponse(os.path.join(os.path.dirname(__file__), "index.html"))


def ddg_text(query: str, max_results: int = 5):
    try:
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=max_results))
    except Exception:
        return []


def ddg_news(query: str, max_results: int = 5):
    try:
        with DDGS() as ddgs:
            return list(ddgs.news(query, max_results=max_results))
    except Exception:
        return []


def extract_number_eok(text: str):
    """텍스트에서 억원 단위 숫자 추출"""
    text = text.replace(",", "")
    match = re.search(r'(\d+\.?\d*)\s*조', text)
    if match:
        return int(float(match.group(1)) * 10000)
    match = re.search(r'(\d+\.?\d*)\s*억', text)
    if match:
        return int(float(match.group(1)))
    return None


@app.get("/api/check")
async def check_company(company: str):
    if not company.strip():
        raise HTTPException(status_code=400, detail="기업명을 입력해주세요")

    try:
        # ── 임직원 ──────────────────────────────────────────────
        employee = {"count": None, "text": "확인 불가", "source": None, "source_url": None, "pass": False}
        for r in ddg_text(f'"{company}" 임직원 직원 명', max_results=6):
            title = r.get("title", "")
            body = r.get("body", "") + " " + title
            if company not in title and company not in body[:150]:
                continue
            match = re.search(r'(\d[\d,]{1,4})\s*명', body)
            if match:
                count = int(match.group(1).replace(",", ""))
                if 10 <= count <= 50000:
                    employee = {
                        "count": count,
                        "text": f"약 {count:,}명",
                        "source": title[:40],
                        "source_url": r.get("href", ""),
                        "pass": count >= 100
                    }
                    break

        # ── 투자금 ──────────────────────────────────────────────
        investment = {"amount": None, "text": "확인 불가", "source": None, "source_url": None, "pass": False}
        for r in ddg_text(f'"{company}" 투자유치 시리즈 펀딩', max_results=6):
            body = r.get("body", "") + " " + r.get("title", "")
            # 제목에 회사명 포함 여부 확인 (오탐 방지)
            title = r.get("title", "")
            if company not in title and company not in body[:100]:
                continue
            # 시리즈 언급 (A~E만 유효)
            s = re.search(r'시리즈\s*([A-E])\b', body)
            if s:
                amt = extract_number_eok(body)
                investment = {
                    "amount": amt,
                    "text": f"시리즈 {s.group(1)} {f'{amt:,}억원' if amt else ''}".strip(),
                    "source": title[:40],
                    "source_url": r.get("href", ""),
                    "pass": True
                }
                break
            amt = extract_number_eok(body)
            if amt and amt >= 10:
                investment = {
                    "amount": amt,
                    "text": f"누적 {amt:,}억원",
                    "source": title[:40],
                    "source_url": r.get("href", ""),
                    "pass": amt >= 50
                }
                break

        # ── 매출 ──────────────────────────────────────────────
        revenue = {"amount": None, "text": "확인 불가", "source": None, "source_url": None, "pass": False}
        for r in ddg_text(f'"{company}" 연매출 매출액 실적 억원', max_results=6):
            title = r.get("title", "")
            body = r.get("body", "") + " " + title
            if company not in title and company not in body[:100]:
                continue
            amt = extract_number_eok(body)
            if amt and amt >= 1:
                year = re.search(r'(20\d{2})', body)
                yr = year.group(1) if year else ""
                revenue = {
                    "amount": amt,
                    "text": f"{yr}년 {amt:,}억원" if yr else f"{amt:,}억원",
                    "source": r.get("title", "")[:40],
                    "source_url": r.get("href", ""),
                    "pass": amt >= 100
                }
                break

        # ── 대기업 계열사 ───────────────────────────────────────
        # 공정위 상호출자제한 기업집단 주요 계열사 내장 목록
        CONGLOMERATE_MAP = {
            'CJ': ['CJ올리브영', '올리브영', 'CJ제일제당', 'CJ대한통운', 'CJ ENM', 'CJ푸드빌', 'CJ CGV', 'tvN'],
            '삼성': ['삼성전자', '삼성SDS', '삼성물산', '삼성생명', '삼성화재', '삼성증권', '호텔신라'],
            'SK': ['SK텔레콤', 'SKT', 'SK하이닉스', 'SK이노베이션', 'SK에너지', '11번가', 'SK플래닛'],
            'LG': ['LG전자', 'LG화학', 'LG유플러스', 'LG CNS', 'LG이노텍'],
            '롯데': ['롯데쇼핑', '롯데칠성', '롯데케미칼', '롯데마트', '롯데백화점', '롯데호텔'],
            '현대': ['현대자동차', '현대모비스', '기아', '현대건설', '현대중공업', 'HMM'],
            '카카오': ['카카오페이', '카카오뱅크', '카카오스타일', '지그재그', '카카오엔터', '카카오모빌리티', '멜론'],
            '네이버': ['네이버웹툰', '라인', '스노우', 'V LIVE', '네이버파이낸셜'],
            '신세계': ['이마트', '스타벅스코리아', 'SSG닷컴', '신세계백화점', '신세계인터내셔날'],
            '쿠팡': ['쿠팡로켓', '쿠팡이츠', '쿠팡플레이'],
            '한화': ['한화솔루션', '한화에어로스페이스', '한화생명', '갤러리아'],
            'GS': ['GS칼텍스', 'GS리테일', 'GS25', 'GS샵', 'GS건설'],
            '포스코': ['POSCO', '포스코퓨처엠', '포스코인터내셔널'],
            '두산': ['두산에너빌리티', '두산밥캣', '두산로보틱스'],
            'KT': ['KT', 'KT&G', 'KT클라우드', 'KT스튜디오지니'],
            '셀트리온': ['셀트리온헬스케어', '셀트리온제약'],
        }

        conglomerate = {"is_member": False, "parent": None, "pass": False}

        # 1차: 내장 목록에서 직접 확인
        for group, subsidiaries in CONGLOMERATE_MAP.items():
            for sub in subsidiaries:
                if sub in company or company in sub:
                    conglomerate = {"is_member": True, "parent": group, "pass": True}
                    break
            if conglomerate["pass"]:
                break

        # 2차: 내장 목록에 없으면 웹 검색으로 보완
        if not conglomerate["pass"]:
            for r in ddg_text(f'"{company}" 대기업집단 계열사 공정위 그룹', max_results=4):
                body = r.get("body", "") + " " + r.get("title", "")
                if re.search(r'대기업집단|상호출자제한', body):
                    parent = re.search(r'(\w{2,6})\s*(?:그룹|계열)', body)
                    conglomerate = {
                        "is_member": True,
                        "parent": parent.group(1) if parent else None,
                        "pass": True
                    }
                    break

        # ── 뉴스 ──────────────────────────────────────────────
        news = []
        for r in ddg_news(f'"{company}"', max_results=8):
            title = r.get("title", "")
            if company not in title and company not in r.get("body", "")[:100]:
                continue
            news.append({
                "title": title,
                "source": r.get("source", ""),
                "url": r.get("url", "")
            })
            if len(news) >= 5:
                break
        if not news:
            for r in ddg_text(f'"{company}" 기업', max_results=6):
                title = r.get("title", "")
                if company not in title and company not in r.get("body", "")[:100]:
                    continue
                news.append({
                    "title": title,
                    "source": "",
                    "url": r.get("href", "")
                })
                if len(news) >= 5:
                    break

        # ── 채용 공고 ──────────────────────────────────────────
        hiring = {"is_hiring": False, "jobs": [], "text": "채용 공고 없음"}
        job_sites = ["wanted.co.kr", "saramin.co.kr", "jobkorea.co.kr", "linkareer.com", "jumpit.co.kr"]
        seen_urls = set()
        for r in ddg_text(f'"{company}" 채용 공고 모집', max_results=10):
            title = r.get("title", "")
            body = r.get("body", "")
            url = r.get("href", "")
            if company not in title and company not in body[:150]:
                continue
            if not any(kw in title + body for kw in ["채용", "모집", "공고", "recruit"]):
                continue
            if url in seen_urls:
                continue
            seen_urls.add(url)
            hiring["jobs"].append({"title": title[:60], "url": url})
            if len(hiring["jobs"]) >= 5:
                break

        if not hiring["jobs"]:
            for r in ddg_text(f'{company} 채용 site:wanted.co.kr OR site:saramin.co.kr OR site:jobkorea.co.kr', max_results=6):
                title = r.get("title", "")
                url = r.get("href", "")
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                hiring["jobs"].append({"title": title[:60], "url": url})
                if len(hiring["jobs"]) >= 5:
                    break

        if hiring["jobs"]:
            hiring["is_hiring"] = True
            hiring["text"] = f"채용 공고 {len(hiring['jobs'])}건 발견"

        # ── 판정 ──────────────────────────────────────────────
        emp_pass = employee["pass"]
        add_pass = investment["pass"] or revenue["pass"] or conglomerate["pass"]
        verdict = "named" if (emp_pass or add_pass) else "not_named"

        parts = []
        if emp_pass:
            parts.append(employee["text"])
        if investment["pass"]:
            parts.append(investment["text"])
        if revenue["pass"]:
            parts.append(revenue["text"])
        if conglomerate["pass"]:
            parts.append("대기업집단 계열사")

        if verdict == "named":
            reason = " · ".join(parts) + " 기준 충족"
        elif not emp_pass:
            reason = "임직원 50명 기준 미충족 또는 확인 불가"
        else:
            reason = "투자금 · 매출 · 대기업집단 계열 조건 확인 불가"

        return {
            "company": company,
            "employee": employee,
            "investment": investment,
            "revenue": revenue,
            "conglomerate": conglomerate,
            "hiring": hiring,
            "news": news,
            "verdict": verdict,
            "reason": reason
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/jobs")
async def search_jobs(company: str, keyword: str = ""):
    if not company.strip():
        raise HTTPException(status_code=400, detail="기업명을 입력해주세요")
    try:
        query = f'"{company}" {keyword} 채용 공고' if keyword else f'"{company}" 채용 공고 모집'
        jobs = []
        seen = set()
        for r in ddg_text(query, max_results=10):
            title = r.get("title", "")
            body = r.get("body", "")
            url = r.get("href", "")
            if company not in title and company not in body[:150]:
                continue
            if not any(kw in title + body for kw in ["채용", "모집", "공고", "recruit"]):
                continue
            if keyword and keyword not in title and keyword not in body[:200]:
                continue
            if url in seen:
                continue
            seen.add(url)
            jobs.append({"title": title[:80], "url": url})
            if len(jobs) >= 8:
                break
        return {"company": company, "keyword": keyword, "jobs": jobs, "count": len(jobs)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
