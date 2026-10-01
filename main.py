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

# 1순위 모델 및 과부하(503) 시 순차적으로 시도할 구글 정식 지원 모델 풀
MODELS_TO_TRY = [
    'gemini-2.0-flash',
    'gemini-1.5-flash',
    'gemini-1.5-pro'
]

# 1. 연합뉴스 주요 기사 수집 (다중 셀렉터 적용)
def fetch_yonhap_news():
    url = "https://www.yna.co.kr/theme/topnews"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    news_items = []
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        
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
    raise RuntimeError("연합뉴스 기사를 수집하지 못했습니다.")

news_context = "\n".join([f"- {item}" for item in news_list])

# 2. 제미나이 데스킹 프롬프트 (팩트 뉘앙스 보존 및 사내 가이드 준수)
prompt = f"""
당신은 경제일간지 뉴스국 엘리베이터 미디어 전용 베테랑 데스크입니다.
수집된 기사 중에서 빌딩 입주사 임직원 및 직장인들이 출근길에 주목할 만한 가장 가치 있는 기사를 최대 15개(최소 10개 이상) 엄선해 16자 2줄 헤드라인으로 다듬으세요.

[선별 및 배제 기준 (엄격 준수)]
1. 적극 선정:
   - 국내 경제, 대기업/산업 동향, IT/테크 트렌드, 부동산, 정책, 일자리, 국민적 보건·복지 이슈 등 굵직한 스트레이트 기사.
   - 직장인과 기업인들의 이목을 집중시키는 인사/이직, 채용, 연봉, 근무환경 등 체감도 높은 경제·사회 통계 이슈 우선 선별.
2. 엄격 배제:
   - 장중 증시 시황(코스피/코스닥 등락), 가상화폐 단순 시세, 연예, 가십, 문화, 비인기 스포츠.
   - 체감도 없는 타국 내각 정치 싸움, 자극적 단발성 해외 사건·사고·르포.
   - 국제 뉴스는 관세, 환율, 반도체 공급망 등 국내 경제/독자에게 직접 영향을 미치는 사안만 채택.
3. 수량 유연성: 기준에 부합하는 양질의 기사만 선별하세요. (최소 10개, 최대 15개)

[헤드라인 편집 및 팩트 보존 원칙 (절대 왜곡 금지)]
1. 팩트 및 미확정 뉘앙스 보존 (최우선 순위):
   - 원문의 '가능성', '전망', '추진', '검토', '유력', '관측' 등 미확정 사실을 기정사실화(확정형)하여 왜곡하지 마세요.
   - 글자 수가 부족할 경우 탈락시키지 말고 짧은 압축 표현('~할 듯', '관측', '유력', '검토')으로 대체해 뉘앙스를 반드시 살리세요.
   - (오답 예: 韓 540억달러 투자 발표 ➔ 확정형 오보)
   - (정답 예: 韓 540억달러 투자할 듯 / 韓 540억달러 투자 관측)
2. 사내 금액 표기 원칙:
   - '천만원' 단위는 원칙적으로 아라비아 숫자로 표기합니다. (예: 5000만원, 13억5000만원)
   - 16자 초과 시 '13.5억원'처럼 소수점 표기로 축약하세요.
3. 단일 인용구 따옴표(" ") 중복 금지:
   - 하나의 인용문은 줄이 나뉘더라도 각 줄마다 따옴표를 열고 닫지 마세요.
   - 올바른 예: 北외무성 "핵보유국 지위 / 되돌릴 수 없어"
4. 억지 축약 금지 및 원문 호흡 존중:
   - 공식 명칭을 무리하게 줄이지 말고 불필요한 수식어를 덜어내세요.

[규격 및 양식 규칙 (글자수 엄수)]
1. 형식: 01번부터 순번대로 '번호. 1행 헤드라인 / 2행 헤드라인' 형태로 작성합니다.
2. 글자 수 규격:
   - 1행(슬래시 앞): 공백 및 문장부호 포함 '최소 10자 ~ 최대 16자' (절대 16자 초과 금지!)
   - 2행(슬래시 뒤): 공백 및 문장부호 포함 '최소 10자 ~ 최대 16자' (절대 16자 초과 금지!)
3. [어젯밤] 식별 태그:
   - 수집 목록에 '[기사시간:어젯밤]' 표시가 있는 기사는 2행 헤드라인(16자 이내) 작성 후 맨 뒤에 한 칸 띄우고 `[어젯밤]`을 붙이세요. (글자 수 계산 제외)
4. [분야] 태그나 글자 수 표기 등 불필요한 부가 정보는 일절 적지 마세요.
5. 한자 약칭(美, 中, 日, 韓, 北, 尹, 車, 産 등)을 적극 활용해 글자 수를 절약하세요.

[수집된 연합뉴스 목록]
{news_context}

[출력 양식 예시]
01. 대기업 51% "대졸 뽑는다" / 하반기 신규 채용 장 선다
02. 엔비디아 사상 최대 규모 / 204조원 자사주 추가 매입 [어젯밤]
...
"""

# 3. 제미나이 호출 (모델별 Fallback 및 503 과부하 지수 백오프)
print("2. 제미나이 데스킹 진행 중...")
result_text = None
max_retries_per_model = 3

for current_model in MODELS_TO_TRY:
    print(f"\n[모델 시도] '{current_model}' 호출을 시작합니다.")
    model_success = False

    for attempt in range(1, max_retries_per_model + 1):
        try:
            print(f"-> [{current_model}] 호출 시도 ({attempt}/{max_retries_per_model})...")
            
            # AFC 경고 방지 및 안정적인 응답 처리를 위해 chat 세션 사용
            chat = client.chats.create(model=current_model)
            response = chat.send_message(prompt)
            
            if response and response.text:
                result_text = response.text.strip()
                print(f"-> [{current_model}] 데스킹 완료!")
                model_success = True
                break
        except Exception as e:
            err_msg = str(e)
            
            # 지원하지 않거나 오타 난 모델(404)은 무의미한 재시도 없이 즉시 다음 모델로 패스
            if "404" in err_msg or "NOT_FOUND" in err_msg:
                print(f"   [{current_model}] 모델명이 유효하지 않음(404). 즉시 대체 모델로 전환합니다.")
                break
                
            # 일시적 503(서버 과부하) 또는 429(속도 제한)인 경우 대기 후 재시도
            wait_seconds = attempt * 5
            print(f"   [{current_model}] ({attempt}/{max_retries_per_model}차) 일시 지연: {err_msg[:60]}... {wait_seconds}초 대기 후 재시도")
            time.sleep(wait_seconds)

    if model_success:
        break
    else:
        print(f"   ⚠️ [{current_model}] 호출 실패. 다음 대체 모델로 전환합니다.")

if not result_text:
    raise RuntimeError("구글 서버 과부하로 모든 대체 모델 처리를 완료하지 못했습니다.")

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
