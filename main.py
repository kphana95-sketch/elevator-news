import os
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
from google import genai

# 환경변수 로드
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
APP_PASSWORD = os.environ.get("APP_PASSWORD")
RECEIVER_EMAIL = os.environ.get("RECEIVER_EMAIL")

client = genai.Client(api_key=GEMINI_API_KEY)
MODEL_NAME = 'gemini-3.8-flash'

# 1. 연합뉴스 주요 기사 수집 (다중 셀렉터 적용으로 빈 목록 방지)
def fetch_yonhap_news():
    url = "https://www.yna.co.kr/theme/topnews"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    news_items = []
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 1차 시도: 주요뉴스 테마 페이지 리스트
        for li in soup.select('div.content01 li, ul.list-type038 li, ul.box-type01 li'):
            title_elem = li.select_one('.tit-news, .tit, a strong')
            time_elem = li.select_one('.txt-time, .lead-time, .txt-time02')
            if title_elem:
                title = title_elem.get_text(strip=True)
                time_str = time_elem.get_text(strip=True) if time_elem else ""
                tag = " [기사시간:어젯밤]" if any(k in time_str for k in ['어제', '전날', '20:', '21:', '22:', '23:']) else ""
                if title and title not in [item.replace(" [기사시간:어젯밤]", "") for item in news_items]:
                    news_items.append(f"{title}{tag}")
    except Exception as e:
        print(f"1차 수집 경고: {e}")

    # 2차 보조 수집: 1차 수집이 부족할 경우 연합뉴스 메인 속보에서 보충
    if len(news_items) < 10:
        try:
            main_url = "https://www.yna.co.kr/"
            res_main = requests.get(main_url, headers=headers, timeout=10)
            soup_main = BeautifulSoup(res_main.text, 'html.parser')
            for a in soup_main.select('.tit-news, a.tit-wrap, strong.tit'):
                title = a.get_text(strip=True)
                if title and len(title) > 10 and title not in [item.replace(" [기사시간:어젯밤]", "") for item in news_items]:
                    news_items.append(title)
                if len(news_items) >= 35:
                    break
        except Exception as e:
            print(f"2차 보조 수집 경고: {e}")

    return news_items[:35]

print("1. 연합뉴스 기사 수집 중...")
news_list = fetch_yonhap_news()
print(f"-> {len(news_list)}개 뉴스 수집 완료!")

if not news_list:
    raise RuntimeError("연합뉴스 기사를 수집하지 못했습니다. 크롤러 URL 및 구조를 확인하세요.")

news_context = "\n".join([f"- {item}" for item in news_list])

# 2. 제미나이 데스킹 프롬프트 (사내 스타일 가이드 엄수)
prompt = f"""
당신은 경제일간지 뉴스국 엘리베이터 미디어 전용 베테랑 데스크입니다.
수집된 기사 중에서 빌딩 입주사 임직원 및 직장인들이 출근길에 주목할 만한 가장 가치 있는 기사를 최대 15개(최소 10개 이상) 엄선해 16자 2줄 헤드라인으로 다듬으세요.

[선별 및 배제 기준 (엄격 준수)]
1. 적극 선정:
   - 국내 경제, 대기업/산업 동향, IT/테크 트렌드, 부동산, 정책, 일자리, 국민적 보건·복지 이슈 등 굵직한 스트레이트 기사.
   - 직장인과 기업인들의 이목을 집중시키는 인사/이직(예: 퇴직공직자 대기업행 등), 채용, 연봉, 근무환경 등 체감도 높은 경제·사회 통계 이슈 우선 선별.
2. 엄격 배제:
   - 장중 증시 시황(코스피/코스닥 등락), 가상화폐 단순 시세, 연예, 가십, 문화, 비인기 스포츠.
   - 체감도 없는 타국 내각 정치 싸움, 자극적 단발성 해외 사건·사고·르포.
   - 국제 뉴스는 관세, 환율, 반도체 공급망 등 국내 경제/독자에게 직접 영향을 미치는 사안만 채택.
3. 수량 유연성: 기준에 부합하는 양질의 기사만 선별하세요. 무리하게 15개를 채우기 위해 가십성 기사를 억지로 포함하지 마세요. (최소 10개, 최대 15개)

[헤드라인 편집 및 문장 다듬기 원칙 (사내 스타일 가이드)]
1. 사내 금액 표기 원칙 (매우 중요):
   - '천만원' 단위는 원칙적으로 아라비아 숫자로 표기합니다. (예: 5천만원 ➔ 5000만원, 3천만원 ➔ 3000만원, 13억5천만원 ➔ 13억5000만원)
   - 만약 '13억5000만원' 표기로 인해 16자를 초과할 경우, '13.5억원'처럼 소수점 표기로 축약하세요.
   - 한글 '5천만원' 형태는 글자 수 조절이 도저히 불가능할 때만 최후의 수단으로 씁니다.
2. 단일 인용구 따옴표(" ") 중복 금지 (매우 중요):
   - 하나의 이어진 발화나 인용문은 줄이 나뉘더라도 따옴표를 각 줄마다 열고 닫지 마세요.
   - 잘못된 예: 北외무성 "핵보유국 지위" / "되돌릴 수 없어"
   - 올바른 예: 北외무성 "핵보유국 지위 / 되돌릴 수 없어" (1행 시작에 열고, 2행 끝에 한 번만 닫기)
3. 억지 축약 금지: '소아청소년과'를 억지로 '소청과'로 줄이지 마세요. 불필요한 수식어('전국' 등)를 덜어내어 공식 명칭을 살리세요.
4. 원문 호흡 존중: 원문 제목이 명확하고 글자 수가 충족된다면 원문의 자연스러운 어휘를 그대로 유지하세요.

[규격 및 양식 규칙 (글자수 엄수)]
1. 형식: 01번부터 순번대로 '번호. 1행 헤드라인 / 2행 헤드라인' 형태로 작성합니다. [백업] 같은 별도 태그는 절대 붙이지 마세요.
2. 글자 수 규격 (엘리베이터 송출 문구 기준):
   - 1행(슬래시 앞): 공백 및 문장부호 포함 '최소 10자 ~ 최대 16자' (절대 16자 초과 금지!)
   - 2행(슬래시 뒤): 공백 및 문장부호 포함 '최소 10자 ~ 최대 16자' (절대 16자 초과 금지!)
3. [어젯밤] 식별 태그:
   - 수집 목록에 '[기사시간:어젯밤]' 표시가 있는 기사는 2행 헤드라인(16자 이내)을 온전히 다 작성한 후 맨 뒤에 한 칸 띄우고 `[어젯밤]`을 붙이세요.
   - `[어젯밤]` 5글자는 관리자 식별용 태그이므로 2행 자체의 16자 글자 수 카운팅에서 제외됩니다.
4. [분야] 태그나 글자 수 표기(예: (14자)) 등 불필요한 부가 정보는 일절 적지 마세요.
5. 한자 약칭(美, 中, 日, 韓, 北, 尹, 車, 産 등)을 적극 활용해 글자 수를 절약하세요.

[수집된 연합뉴스 목록]
{news_context}

[출력 양식 예시]
01. 대기업 51% "대졸 뽑는다" / 하반기 신규 채용 장 선다
02. 엔비디아 사상 최대 규모 / 204조원 자사주 추가 매입 [어젯밤]
...
"""

# 3. 제미나이 호출 (5단계 지수 백오프)
print("2. 제미나이 데스킹 진행 중...")
result_text = None
max_retries = 5

for attempt in range(1, max_retries + 1):
    try:
        print(f"-> [{MODEL_NAME}] 호출 시도 ({attempt}/{max_retries})...")
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
        )
        if response and response.text:
            result_text = response.text.strip()
            print(f"-> [{MODEL_NAME}] 데스킹 완료!")
            break
    except Exception as e:
        wait_seconds = attempt * 5
        err_msg = str(e)
        print(f"-> [{MODEL_NAME}] ({attempt}/{max_retries}차) 일시 지연: {err_msg[:60]}... {wait_seconds}초 대기 후 재시도")
        time.sleep(wait_seconds)

if not result_text:
    raise RuntimeError("구글 서버 과부하로 처리를 완료하지 못했습니다.")

print("\n--- [데스킹 결과 미리보기] ---")
print(result_text[:400] + "...\n")

# 4. 이메일 자동 발송
def send_email(subject, body_text):
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECEIVER_EMAIL
    msg['Subject'] = subject
    msg.attach(MIMEText(body_text, 'plain', 'utf-8'))
    
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    clean_pw = APP_PASSWORD.replace(" ", "") if APP_PASSWORD else ""
    server.login(SENDER_EMAIL, clean_pw)
    server.send_message(msg)
    server.quit()
    print("🎉 모닝 엘리베이터 뉴스 발송 완료!")

now_str = (datetime.utcnow() + timedelta(hours=9)).strftime("%m월 %d일")
mail_title = f"[{now_str} 엘리베이터 뉴스] 모닝 브리핑 헤드라인"
send_email(mail_title, result_text)
