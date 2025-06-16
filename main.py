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

def create_super_broken_url(long_url):
    """創建超強打斷的網址，避免任何預覽可能"""
    try:
        # 使用多個短網址服務
        services = [
            f"http://tinyurl.com/api-create.php?url={quote(long_url, safe='')}",
            f"https://is.gd/create.php?format=simple&url={quote(long_url, safe='')}",
            f"http://v.gd/create.php?format=simple&url={quote(long_url, safe='')}"
        ]
        
        for api_url in services:
            try:
                res = requests.get(api_url, timeout=5)
                if res.status_code == 200 and res.text.startswith('http'):
                    short_url = res.text.strip()
                    # 添加超強破壞參數
                    timestamp = int(time.time())
                    random_id = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=12))
                    return f"{short_url}?ref=nb&t={timestamp}&id={random_id}&nopreview=1&cache={timestamp}&v=safe"
            except:
                continue
                
    except Exception as e:
        print(f"⚠️ 短網址服務失敗: {e}")
    
    # 備用方案：原網址加強力參數
    timestamp = int(time.time())
    random_id = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=15))
    separator = '&' if '?' in long_url else '?'
    return f"{long_url}{separator}utm_source=bot&t={timestamp}&id={random_id}&nopreview=true&safe=1"

def format_ultra_broken_url(url):
    """將網址打斷到極致，確保不會觸發預覽"""
    # 移除協議
    clean_url = url.replace('https://', '').replace('http://', '')
    
    # 方法1: 每個特殊字符都用空格包圍
    broken_url = clean_url.replace('.', ' . ')
    broken_url = broken_url.replace('/', ' / ')
    broken_url = broken_url.replace('?', ' ? ')
    broken_url = broken_url.replace('&', ' & ')
    broken_url = broken_url.replace('=', ' = ')
    broken_url = broken_url.replace('-', ' - ')
    
    # 方法2: 在域名中間也加入空格
    parts = broken_url.split(' / ', 1)
    if len(parts) > 0:
        domain_part = parts[0]
        # 在域名中每隔4-6個字符加空格
        domain_chars = list(domain_part.replace(' ', ''))
        spaced_domain = ''
        for i, char in enumerate(domain_chars):
            spaced_domain += char
            if i > 0 and (i + 1) % 5 == 0 and char not in [' ', '.']:
                spaced_domain += ' '
        
        if len(parts) > 1:
            broken_url = spaced_domain + ' / ' + parts[1]
        else:
            broken_url = spaced_domain
    
    return broken_url

def format_message_with_broken_url(title, source_name, url):
    """格式化訊息，使用多重打斷技術"""
    broken_url = format_ultra_broken_url(url)
    
    # 分成多行顯示，進一步降低預覽風險
    url_lines = []
    words = broken_url.split()
    current_line = ""
    
    for word in words:
        if len(current_line + word) < 35:  # 每行最多35字符
            current_line += word + " "
        else:
            if current_line.strip():
                url_lines.append(current_line.strip())
            current_line = word + " "
    
    if current_line.strip():
        url_lines.append(current_line.strip())
    
    # 格式化多行網址顯示
    formatted_url_lines = '\n'.join([f"  {line}" for line in url_lines])
    
    return f"""📰 {title}
📌 來源：{source_name}
🔗 網址 (複製時移除所有空格)：
{formatted_url_lines}"""

def create_alternative_broken_url(url):
    """替代的打斷方法 - 使用中文符號"""
    clean_url = url.replace('https://', '').replace('http://', '')
    
    # 使用中文標點符號打斷
    broken_url = clean_url.replace('.', '．')  # 使用全形句號
    broken_url = broken_url.replace('/', '／')  # 使用全形斜線
    broken_url = broken_url.replace('?', '？')  # 使用全形問號
    broken_url = broken_url.replace('&', '＆')  # 使用全形&
    broken_url = broken_url.replace('=', '＝')  # 使用全形等號
    
    return broken_url

def create_reverse_display_url(url):
    """反向顯示網址的部分內容"""
    clean_url = url.replace('https://', '').replace('http://', '')
    parts = clean_url.split('/')
    
    if len(parts) > 1:
        domain = parts[0]
        path = '/'.join(parts[1:])
        
        # 反向顯示域名
        reversed_domain = domain[::-1]
        
        return f"🌐 {reversed_domain} (反向) → {path[:30]}..."
    
    return f"🌐 {clean_url[::-1]} (反向顯示)"

def format_creative_message(title, source_name, url):
    """創意格式化 - 多種破壞方法組合"""
    
    # 方法選擇 (可以隨機或按順序)
    method = random.choice(['broken', 'chinese', 'reverse'])
    
    if method == 'broken':
        # 超強打斷法
        formatted_url = format_ultra_broken_url(url)
        url_display = f"🔗 {formatted_url}\n💡 複製時請移除所有空格"
        
    elif method == 'chinese':
        # 中文符號法
        formatted_url = create_alternative_broken_url(url)
        url_display = f"🔗 {formatted_url}\n💡 請將全形符號改為半形"
        
    else:  # reverse
        # 反向顯示法
        formatted_url = create_reverse_display_url(url)
        url_display = f"{formatted_url}\n💡 私訊「完整網址」獲取正常連結"
    
    return f"""📰 {title}
📌 來源：{source_name}
{url_display}"""

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

            # 🔑 使用超強打斷網址方法
            broken_url = create_super_broken_url(link)
            formatted = format_message_with_broken_url(title, source_name, broken_url)
            
            category = classify_news(title)
            classified_news[category].append(formatted)

            # ✅ 新增向量（用正規化後標題）
            norm_title = normalize_title(title)
            known_titles_vecs.append(model.encode(norm_title))

    return classified_news

def send_message_by_category(news_by_category):
    max_length = 3500  # 因為多行格式需要更多空間
    no_news_categories = []

    for category, messages in news_by_category.items():
        if messages:
            title = f"【{today} 業企部 今日【{category}】重點新聞整理】 共{len(messages)}則新聞"
            footer = "\n\n⚠️ 使用網址時請移除所有空格符號"
            
            content = "\n" + "─"*50 + "\n".join([f"\n{msg}\n" + "─"*50 for msg in messages])
            full_message = f"{title}{content}{footer}"
            
            # 分段發送長訊息
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



