import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai

# 환경변수(Secrets) 불러오기
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
APP_PASSWORD = os.environ.get("APP_PASSWORD")
RECEIVER_EMAIL = os.environ.get("RECEIVER_EMAIL")

# 1. 제미나이 설정 (최신 gemini-3.0-flash 지정)
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-3.0-flash')

# 2. 연합뉴스 기사 수집 (전날 21시 이후 ~ 당일 아침 기사 필터링)
def fetch_yonhap_news():
    url = "https://media.naver.com/press/001"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    res = requests.get(url, headers=headers)
    soup = BeautifulSoup(res.text, 'html.parser')
    
    # 한국 시간(KST) 기준 어제 밤 21:00 이후 기사 필터링
    now_kst = datetime.utcnow() + timedelta(hours=9)
    cutoff_time = (now_kst - timedelta(days=1)).replace(hour=21, minute=0, second=0, microsecond=0)
    
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
                    collected_articles.append(title)
            else:
                collected_articles.append(title)
        except Exception:
            collected_articles.append(title)
            
        if len(collected_articles) >= 25:
            break
            
    return collected_articles

print("1. 연합뉴스 기사 수집 중 (전날 21시 이후 ~ 당일 기사)...")
raw_news_list = fetch_yonhap_news()
print(f"-> {len(raw_news_list)}개 뉴스 수집 완료!")
news_context = "\n".join([f"- {t}" for t in raw_news_list])

# 3. 제미나이 데스킹 프롬프트 (분야/글자수 표기 없는 16자 2줄 슬래시 포맷)
prompt = f"""
당신은 경제일간지 뉴스국 엘리베이터 전용 미디어 편집 데스크입니다.
아래 제공된 [수집된 연합뉴스 목록]에서 원칙에 맞게 기사 10개를 선별하고 지정된 슬래시(/) 줄바꿈 포맷으로 헤드라인을 작성하세요.

[선별 및 배제 기준]
1. 선정: 경제, 산업, 국제, 테크, 부동산 등 굵직한 스트레이트 기사. 하루 2번 교체하므로 오후까지 유효한 기사.
2. 엄격 배제: 장중 증시 시황(코스피/코스닥 등락), 가상화폐(코인) 시세, 단순 연예, 가십, 문화, 비인기 스포츠.
3. 예외: 노벨문학상 수상, 올림픽/아시안게임 축구 결승 등 초대형 국가적 관심사만 허용.

[글자 수 및 표기 절대 규칙]
1. 반드시 '번호. 1행 헤드라인 / 2행 헤드라인' 형태로 슬래시(/) 앞뒤 띄어쓰기를 포함해 한 줄로 출력합니다.
2. 1행(슬래시 앞): 공백 및 문장부호 포함 '최소 10자 ~ 최대 16자' (절대 16자 초과 금지!)
3. 2행(슬래시 뒤): 공백 및 문장부호 포함 '최소 10자 ~ 최대 16자' (절대 16자 초과 금지!)
4. [분야] 태그나 글자 수 표기(예: (14자)) 등 불필요한 부가 정보는 일절 적지 마세요.
5. 글자 수를 줄이고 시각적 리듬감을 살리기 위해 널리 쓰이는 한자(美, 中, 日, 韓, 北, 尹, 車, 産 등)를 적극 사용하세요.

[수집된 연합뉴스 목록]
{news_context}

[출력 양식 예시]
01. 北외무성 부상 "핵보유국 지위 / 무엇으로도 되돌릴 수 없어"
02. 한은, 기준금리 0.25%p / 38개월 만에 전격 인하
03. 삼성전자 3분기 잠정실적 / 영업익 9조원대 머물러
...
10. ...
"""

print("2. 제미나이 데스킹 진행 중...")
response = model.generate_content(prompt)
result_text = response.text
print("\n--- [데스킹 결과 미리보기] ---")
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
    server.login(SENDER_EMAIL, APP_PASSWORD.replace(" ", ""))
    server.send_message(msg)
    server.quit()
    print("\n🎉 성공: 메일 발송 완료!")

today_str = (datetime.utcnow() + timedelta(hours=9)).strftime("%m월 %d일")
mail_title = f"[{today_str} 오전판] 본사 엘리베이터 뉴스 송출 10선"
send_email(mail_title, result_text)
