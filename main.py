import os
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
from google import genai

# 환경변수(Secrets) 불러오기
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
APP_PASSWORD = os.environ.get("APP_PASSWORD")
RECEIVER_EMAIL = os.environ.get("RECEIVER_EMAIL")

client = genai.Client(api_key=GEMINI_API_KEY)

# 1. 연합뉴스 기사 수집 (어젯밤 21시~자정 기사 추적)
def fetch_yonhap_news():
    url = "https://media.naver.com/press/001"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    res = requests.get(url, headers=headers)
    soup = BeautifulSoup(res.text, 'html.parser')
    
    now_kst = datetime.utcnow() + timedelta(hours=9)
    cutoff_time = (now_kst - timedelta(days=1)).replace(hour=21, minute=0, second=0, microsecond=0)
    today_start = now_kst.replace(hour=0, minute=0, second=0, microsecond=0)
    
    collected_articles = []
    items = soup.select('.press_edit_news .press_edit_news_link') + soup.select('.press_news_title')
    seen_urls = set()

    for item in items:
        link = item.get('href')
        title = item.get_text(strip=True)
        if not link or not title or link in seen_urls:
            continue
        seen_urls.add(link)
        
        try:
            art_res = requests.get(link, headers=headers, timeout=5)
            art_soup = BeautifulSoup(art_res.text, 'html.parser')
            time_tag = art_soup.select_one('._ARTICLE_DATE_TIME') or art_soup.select_one('.media_end_head_info_datestamp_time')
            
            if time_tag and time_tag.has_attr('data-date-time'):
                article_time = datetime.strptime(time_tag['data-date-time'], '%Y-%m-%d %H:%M:%S')
                if article_time >= cutoff_time:
                    if article_time < today_start:
                        title = f"{title} [기사시간:어젯밤]"
                    collected_articles.append(title)
            else:
                collected_articles.append(title)
        except Exception:
            collected_articles.append(title)
            
        if len(collected_articles) >= 35:
            break
            
    return collected_articles

print("1. 연합뉴스 기사 수집 중...")
raw_news_list = fetch_yonhap_news()
print(f"-> {len(raw_news_list)}개 뉴스 수집 완료!")
news_context = "\n".join([f"- {t}" for t in raw_news_list])

# 2. 제미나이 데스킹 프롬프트
prompt = f"""
당신은 경제일간지 뉴스국 엘리베이터 미디어 전용 베테랑 데스크입니다.
수집된 기사 중에서 빌딩 입주사 임직원 및 직장인들이 출근길에 주목할 만한 가장 가치 있는 기사 15개를 엄선해 16자 2줄 헤드라인으로 다듬으세요.

[선별 및 배제 기준 (엄격 준수)]
1. 적극 선정:
   - 국내 경제, 대기업/산업 동향, IT/테크 트렌드, 부동산, 정책, 일자리, 국민적 보건·복지 이슈 등 굵직한 스트레이트 기사.
   - 직장인과 기업인들의 이목을 집중시키는 인사/이직(예: 퇴직공직자 대기업행 등), 채용, 연봉, 근무환경 등 체감도 높은 경제·사회 통계 이슈도 적극 포함.
2. 엄격 배제:
   - 장중 증시 시황(코스피/코스닥 등락), 가상화폐 단순 시세, 연예, 가십, 문화, 비인기 스포츠.
   - 체감도 없는 타국 내각 정치 싸움, 자극적 단발성 해외 사건·사고·르포.
   - 국제 뉴스는 관세, 환율, 반도체 공급망 등 국내 경제/독자에게 직접 영향을 미치는 사안만 채택.

[헤드라인 편집 및 문장 다듬기 원칙]
1. 원문 인용부호 유지: 원문 제목에 큰따옴표(" ")로 묶인 주요 발언이나 핵심 멘트(예: "대졸 뽑는다", "상응조치 단행")는 임의로 없애지 말고 생동감을 살리기 위해 그대로 유지하세요.
2. 억지 축약 금지: '소아청소년과'를 억지로 '소청과'로 줄이는 식의 거친 은어식 축약을 지양하세요. '전국' 같은 불필요한 수식어를 덜어내어 공식 명칭을 살리는 것이 올바른 편집입니다.
3. 원문 호흡 존중: 원문 제목이 이미 명확하고 글자 수가 충족된다면 굳이 다른 말로 뜯어고치지 말고 원문의 자연스러운 어휘를 활용하세요.

[규격 및 양식 규칙 (글자수 엄수)]
1. 형식: 01번부터 15번까지 순번대로 '번호. 1행 헤드라인 / 2행 헤드라인' 형태로 작성합니다. [백업] 같은 별도 태그는 절대 붙이지 마세요.
2. 글자 수 규격 (엘리베이터 송출 문구 기준):
   - 1행(슬래시 앞): 공백 및 문장부호 포함 '최소 10자 ~ 최대 16자' (절대 16자 초과 금지!)
   - 2행(슬래시 뒤): 공백 및 문장부호 포함 '최소 10자 ~ 최대 16자' (절대 16자 초과 금지!)
3. [어젯밤] 표기 안내:
   - 수집 목록에 '[기사시간:어젯밤]' 표시가 있는 기사라면, 2행 헤드라인(16자 이내)을 온전히 다 작성한 후, 문장 맨 뒤에 한 칸 띄우고 `[어젯밤]`을 덧붙이세요.
   - [어젯밤]은 식별용 표식이므로 2행 자체의 16자 글자 수 카운팅에서 제외됩니다.
4. [분야] 태그나 (14자) 같은 글자 수 표기 등 불필요한 부가 정보는 일절 적지 마세요.
5. 한자 약칭(美, 中, 日, 韓, 北, 尹, 車, 産 등)을 적극 활용해 글자 수를 절약하세요.

[수집된 연합뉴스 목록]
{news_context}

[출력 양식 예시]
01. 대기업 51% "대졸 뽑는다" / 하반기 신규 채용 장 선다
02. 엔비디아 사상 최대 규모 / 204조원 자사주 추가 매입 [어젯밤]
...
15. ...
"""

# 3. 제미나이 호출 (가용 모델 자동 식별 및 다중 후보 시도)
print("2. 제미나이 데스킹 진행 중...")

# 현재 API 키로 접근 가능한 텍스트 생성 모델 목록 탐색
available_models = []
try:
    for m in client.models.list():
        # generateContent를 지원하는 모델명만 추출
        name = m.name.replace("models/", "") if hasattr(m, 'name') else ""
        methods = getattr(m, 'supported_generation_methods', []) or getattr(m, 'supported_actions', [])
        if "generateContent" in methods or not methods:
            if "flash" in name.lower() or "gemini" in name.lower():
                available_models.append(name)
except Exception as e:
    print(f"모델 목록 조회 생략: {e}")

# 기본 우선순위 모델군 설정
priority_models = ['gemini-3.8-flash', 'gemini-1.5-flash', 'gemini-1.5-flash-latest', 'gemini-1.5-pro']
# 조회된 모델 중 우선순위 모델과 매칭 및 병합
test_queue = [m for m in priority_models if m in available_models]
if not test_queue:
    test_queue = priority_models + [m for m in available_models if m not in priority_models]

# 중복 제거
seen = set()
models_to_try = [x for x in test_queue if not (x in seen or seen.add(x))]

print(f"-> 시도 후보 모델 리스트: {models_to_try[:4]}")

result_text = None
for model_candidate in models_to_try:
    print(f"-> 모델 [{model_candidate}] 호출 시도 중...")
    for retry in range(1, 3):
        try:
            response = client.models.generate_content(
                model=model_candidate,
                contents=prompt,
            )
            if response and response.text:
                result_text = response.text
                print(f"-> [{model_candidate}] 데스킹 성공!")
                break
        except Exception as err:
            err_msg = str(err)
            if "404" in err_msg:
                print(f"-> [{model_candidate}] 미지원 모델 (404), 다음 모델로 이동.")
                break
            print(f"-> [{model_candidate}] ({retry}/2차) 과부하/오류 ({err_msg[:60]}...). 5초 대기.")
            time.sleep(5)
    if result_text:
        break

if not result_text:
    raise RuntimeError("모든 가용 제미나이 모델이 일시 과부하 상태입니다. 잠시 후 워크플로우를 다시 실행해 주세요.")

print("\n--- [데스킹 결과] ---")
print(result_text)

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
    print("\n🎉 성공: 메일 발송 완료!")

today_str = (datetime.utcnow() + timedelta(hours=9)).strftime("%m월 %d일")
mail_title = f"[{today_str} 오전판] 본사 엘리베이터 뉴스 15선"
send_email(mail_title, result_text)
