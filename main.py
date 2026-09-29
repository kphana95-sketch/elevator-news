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

# 1. 연합뉴스 기사 수집 (어젯밤 21시~자정 기사는 [어젯밤] 자동 태깅)
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
                        title = f"[어젯밤] {title}"
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
수집된 기사 중에서 엘리베이터 탑승객(직장인, 입주사 임직원)에게 전달할 가장 중요한 기사 15개를 엄선해 16자 2줄 헤드라인으로 다듬으세요. (1~10번: 정규 송출용, 11~15번: 백업 후보군)

[선별 및 배제 기준 (엄격 준수)]
1. 적극 선정: 국내 경제, 주요 대기업/산업, IT/테크 트렌드, 부동산, 정책, 일자리, 국민적 보건·복지 이슈 등 하루 종일 유효한 굵직한 스트레이트 기사.
2. 엄격 배제:
   - 장중 증시 시황(코스피/코스닥 등락), 가상화폐 단순 시세, 연예, 가십, 문화, 비인기 스포츠.
   - 타국 내각 정치 싸움, 자극적 단발성 해외 사건·사고·르포(예: 외신 정치인 비리 폭로, 비밀감옥, 국경 분쟁 단신 등 체감도 없는 기사).
   - 국제 뉴스는 관세, 환율, 반도체 공급망, 미 대선 정책 등 '국내 경제/독자에게 직접 영향을 미치는 사안'만 채택.

[헤드라인 편집 및 문장 다듬기 원칙]
1. 원문 인용부호 유지: 원문 제목에 큰따옴표(" ")로 묶인 주요 발언이나 핵심 멘트(예: "대졸 뽑는다", "상응조치 단행")는 임의로 따옴표를 없애지 말고 생동감을 위해 그대로 살려두세요.
2. 억지 축약 금지: '소아청소년과'를 억지로 '소청과'로 줄이는 식의 거친 은어식 축약을 지양하세요. 대신 '전국' 같은 뻔한 수식어를 과감히 삭제하여 공식 명칭('소아청소년과 전공의 113명')을 살리는 것이 올바른 편집입니다.
3. 원문 호흡 존중: 원문 제목이 이미 명확하고 글자 수가 충족된다면 무리하게 문장을 뜯어고치지 말고 원문의 자연스러운 어휘를 활용하세요.
4. [어젯밤] 표기 유지: 기사 제목 앞에 `[어젯밤]` 태그가 붙어있는 기사는 반드시 헤드라인 앞에도 `[어젯밤]`을 그대로 명시하세요. (예: 01. [어젯밤] 엔비디아 사상 최대 / 204조 자사주 매입)

[규격 및 양식 규칙]
1. 형식: 반드시 '번호. 1행 헤드라인 / 2행 헤드라인' 형태로 작성 (슬래시 앞뒤 띄어쓰기 1칸 필수).
2. 글자 수:
   - 1행(슬래시 앞): 공백 포함 10자 ~ 16자 (절대 16자 초과 금지!)
   - 2행(슬래시 뒤): 공백 포함 10자 ~ 16자 (절대 16자 초과 금지!)
3. [분야] 태그나 글자 수 표기(예: (14자)) 등 불필요한 부가 표기는 일절 적지 마세요.
4. 한자 약칭(美, 中, 日, 韓, 北, 尹, 車, 産 등)을 적극 활용해 글자 수를 절약하세요.

[수집된 연합뉴스 목록]
{news_context}

[출력 양식]
01. ...
...
10. ...
11. [백업] ...
...
15. [백업] ...
"""

# 3. 제미나이 호출 (503 과부하 대비 재시도 로직)
print("2. 제미나이 데스킹 진행 중...")
models_to_try = ['gemini-3.8-flash', 'gemini-3.8-flash']
result_text = None

for attempt, model_name in enumerate(models_to_try, 1):
    try:
        print(f"-> 호출 시도 {attempt}/2 (모델: {model_name})...")
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
        )
        result_text = response.text
        if result_text:
            break
    except Exception as e:
        print(f"경고: {attempt}차 시도 실패 ({e}). 5초 대기 후 재시도합니다.")
        time.sleep(5)

if not result_text:
    raise RuntimeError("구글 서버 과부하로 응답을 가져오지 못했습니다. 잠시 후 다시 실행해 주세요.")

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
mail_title = f"[{today_str} 오전판] 본사 엘리베이터 뉴스 15선 (정규 10선 + 백업 5선)"
send_email(mail_title, result_text)
