import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
import email.utils
from urllib.parse import quote
import requests
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
import re
import time
import random
import string

# ✅ 初始化語意模型
model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')

# ✅ 相似度門檻
SIMILARITY_THRESHOLD = 0.95

ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')
print("✅ Access Token 前 10 碼：", ACCESS_TOKEN[:10] if ACCESS_TOKEN else "未設定")

CATEGORY_KEYWORDS = {
    "新光金控": ["新光金", "新光人壽", "新壽", "吳東進"],
    "台新金控": ["台新金", "台新人壽", "台新壽", "吳東亮"],
    "金控": ["金控", "金融控股", "中信金", "玉山金", "永豐金", "國泰金", "富邦金", "台灣金"],
    "保險": ["保險", "壽險", "健康險", "意外險", "人壽"],
    "其他": []
}

EXCLUDED_KEYWORDS = ['保險套', '避孕套', '保險套使用', '太陽人壽', '大西部人壽', '美國海岸保險']

TW_TZ = timezone(timedelta(hours=8))
now = datetime.now(TW_TZ)
today = now.date()

# ✅ 標題正規化
def normalize_title(title):
    title = re.sub(r'[｜|‧\-－–—~～].*$', '', title)  # 移除媒體後綴
    title = re.sub(r'<[^>]+>', '', title)            # 移除 HTML 標籤
    title = re.sub(r'[^\w\u4e00-\u9fff\s]', '', title)  # 移除非文字符號
    title = re.sub(r'\s+', ' ', title)               # 多餘空白
    return title.strip().lower()

def create_anti_preview_url(long_url):
    """創建防預覽但可點擊的網址"""
    try:
        # 方法1: 使用多個短網址服務
        short_services = [
            f"http://tinyurl.com/api-create.php?url={quote(long_url, safe='')}",
            f"https://is.gd/create.php?format=simple&url={quote(long_url, safe='')}",
        ]
        
        for api_url in short_services:
            try:
                res = requests.get(api_url, timeout=5)
                if res.status_code == 200 and res.text.startswith('http'):
                    short_url = res.text.strip()
                    
                    # 添加防預覽參數但保持可點擊性
                    timestamp = int(time.time())
                    random_id = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=8))
                    
                    # 使用常見的追蹤參數，看起來正常但能破壞預覽
                    return f"{short_url}?utm_source=linebot&utm_medium=social&utm_campaign={random_id}&fbclid=IwAR{random_id}&t={timestamp}"
            except:
                continue
                
    except Exception as e:
        print(f"⚠️ 短網址失敗: {e}")
    
    # 備用方案：原網址加參數
    timestamp = int(time.time())
    random_id = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=10))
    separator = '&' if '?' in long_url else '?'
    return f"{long_url}{separator}utm_source=linebot&utm_campaign={random_id}&fbclid=IwAR{random_id}&t={timestamp}"

def format_anti_preview_message(title, source_name, url):
    """格式化訊息，使用零寬字符和特殊排版避免預覽"""
    
    # 方法1: 使用零寬字符打斷但保持可點擊 (推薦)
    disguised_url = url
    # 在協議後插入零寬字符
    disguised_url = disguised_url.replace('https://', 'https://\u200B')
    disguised_url = disguised_url.replace('http://', 'http://\u200B')
    
    # 方法2: 在新聞標題和網址之間加入更多內容，降低預覽觸發機率
    formatted_message = f"""📰 {title}
📌 來源：{source_name}
📅 {now.strftime('%Y-%m-%d %H:%M')}

🔗 完整報導：{disguised_url}"""
    
    return formatted_message

def format_message_with_separator(title, source_name, url):
    """使用分隔符號的格式化方法"""
    return f"""📰 {title}
📌 來源：{source_name}
{'─' * 30}
🔗 {url}
{'─' * 30}"""

def format_message_with_extra_content(title, source_name, url):
    """在網址前後加入額外內容降低預覽機率"""
    category = classify_news(title)
    
    return f"""📰 {title}
📌 來源：{source_name}
📂 分類：{category}
⏰ 發布：{now.strftime('%m/%d %H:%M')}

📖 詳細內容請點擊：
{url}

📱 建議使用瀏覽器開啟以獲得最佳閱讀體驗"""

def create_redirect_url(original_url):
    """創建重導向網址（如果你有自己的網域）"""
    # 如果你有自己的網域，可以創建重導向服務
    # 例如：https://yourdomain.com/redirect?url=encoded_original_url
    
    # 暫時使用現有的重導向服務
    redirect_services = [
        f"https://href.li/?{quote(original_url)}",
        f"https://link.tl/?{quote(original_url)}",
    ]
    
    for redirect_url in redirect_services:
        try:
            # 簡單測試服務是否可用
            test_res = requests.head(redirect_url, timeout=3)
            if test_res.status_code in [200, 301, 302]:
                timestamp = int(time.time())
                return f"{redirect_url}&t={timestamp}"
        except:
            continue
    
    # 如果重導向服務不可用，返回原網址
    return create_anti_preview_url(original_url)

def format_message_minimal_preview_risk(title, source_name, url):
    """最小預覽風險的格式化方法"""
    
    # 使用多種技巧組合
    processed_url = create_anti_preview_url(url)
    
    # 加入零寬字符
    processed_url = processed_url.replace('://', '://\u200B')
    
    # 使用特殊排版
    return f"""📰 {title}

📌 {source_name} | {now.strftime('%m-%d %H:%M')}

🔗 閱讀完整報導 👇
{processed_url}"""

def classify_news(title):
    title = normalize_title(title)
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw.lower() in title for kw in keywords):
            return category
    return "其他"

def is_taiwan_news(source_name, link):
    taiwan_sources = [
        '工商時報', '中國時報', '經濟日報', '三立新聞網', '自由時報', '聯合新聞網',
        '鏡週刊', '台灣雅虎', '鉅亨網', '中時新聞網','Ettoday新聞雲',
        '天下雜誌', '奇摩新聞', '《現代保險》雜誌','遠見雜誌'
    ]
    if any(taiwan_source in source_name for taiwan_source in taiwan_sources) and "香港經濟日報" not in source_name:
        return True
    if '.tw' in link:
        return True
    return False

def is_similar(title, known_titles_vecs):
    norm_title = normalize_title(title)
    vec = model.encode([norm_title])
    if not known_titles_vecs:
        return False
    sims = cosine_similarity(vec, known_titles_vecs)[0]
    return np.max(sims) >= SIMILARITY_THRESHOLD

def fetch_news():
    rss_urls = [
        "https://news.google.com/rss/search?q=新光金控+OR+新光人壽+OR+台新金控+OR+台新人壽+OR+壽險+OR+金控+OR+人壽+OR+新壽+OR+台新壽+OR+吳東進+OR+吳東亮&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
        "https://news.google.com/rss/search?q=新光金控+OR+新光人壽+OR+新壽+OR+吳東進&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
        "https://news.google.com/rss/search?q=台新金控+OR+台新人壽+OR+台新壽+OR+吳東亮&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
        "https://news.google.com/rss/search?q=壽險+OR+健康險+OR+意外險+OR+人壽&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
        "https://news.google.com/rss/search?q=金控+OR+金融控股&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    ]

    classified_news = {cat: [] for cat in CATEGORY_KEYWORDS}
    known_titles_vecs = []

    for rss_url in rss_urls:
        res = requests.get(rss_url)
        print(f"✅ 來源: {rss_url} 回應狀態：{res.status_code}")
        if res.status_code != 200:
            continue

        root = ET.fromstring(res.content)
        items = root.findall(".//item")
        print(f"✅ 從 {rss_url} 抓到 {len(items)} 筆新聞")

        for item in items:
            title_elem = item.find('title')
            link_elem = item.find('link')
            pubDate_elem = item.find('pubDate')
            if title_elem is None or link_elem is None or pubDate_elem is None:
                continue

            title = title_elem.text.strip()
            link = link_elem.text.strip()
            pubDate_str = pubDate_elem.text.strip()
            if not title or title.startswith("Google ニュース"):
                continue

            source_elem = item.find('source')
            source_name = source_elem.text.strip() if source_elem is not None else "未標示"
            pub_datetime = email.utils.parsedate_to_datetime(pubDate_str).astimezone(TW_TZ)

            if now - pub_datetime > timedelta(hours=24):
                continue
            if any(bad_kw in title for bad_kw in EXCLUDED_KEYWORDS):
                continue
            if not is_taiwan_news(source_name, link):
                continue
            if is_similar(title, known_titles_vecs):
                continue

            # 🔑 使用防預覽但保持可點擊的方法
            processed_url = create_anti_preview_url(link)
            
            # 可以選擇不同的格式化方法：
            # 方法1: 基本防預覽 (推薦)
            formatted = format_anti_preview_message(title, source_name, processed_url)
            
            # 方法2: 如果方法1無效，啟用這個
            # formatted = format_message_with_extra_content(title, source_name, processed_url)
            
            # 方法3: 最小風險格式
            # formatted = format_message_minimal_preview_risk(title, source_name, processed_url)
            
            category = classify_news(title)
            classified_news[category].append(formatted)

            # ✅ 新增向量（用正規化後標題）
            norm_title = normalize_title(title)
            known_titles_vecs.append(model.encode(norm_title))

    return classified_news

def send_message_by_category(news_by_category):
    max_length = 4000
    no_news_categories = []

    for category, messages in news_by_category.items():
        if messages:
            title = f"【{today} 業企部 今日【{category}】重點新聞整理】 共{len(messages)}則新聞"
            content = "\n\n".join(messages)
            full_message = f"{title}\n{'='*50}\n{content}"
            
            for i in range(0, len(full_message), max_length):
                segment = full_message[i:i + max_length]
                if i > 0:
                    segment = f"【續】\n{segment}"
                broadcast_message(segment)
        else:
            no_news_categories.append(category)

    if no_news_categories:
        title = f"【{today} 業企部 今日無相關新聞分類整理】"
        content = "\n".join(f"📂【{cat}】無相關新聞" for cat in no_news_categories)
        broadcast_message(f"{title}\n\n{content}")

def broadcast_message(message):
    url = 'https://api.line.me/v2/bot/message/broadcast'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {ACCESS_TOKEN}'
    }

    data = {
        "messages": [{
            "type": "text",
            "text": message
        }]
    }

    print(f"📤 發送訊息總長：{len(message)} 字元")
    res = requests.post(url, headers=headers, json=data)
    print(f"📤 LINE 回傳狀態碼：{res.status_code}")
    print("📤 LINE 回傳內容：", res.text)

if __name__ == "__main__":
    news = fetch_news()
    if news:
        send_message_by_category(news)
    else:
        print("⚠️ 沒有符合條件的新聞，不發送。")



