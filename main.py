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
import json

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

def create_simple_clean_url(long_url):
    """創建簡潔的網址，用於 Flex Message 的 URI Action"""
    try:
        # 使用短網址服務
        encoded_url = quote(long_url, safe='')
        api_url = f"http://tinyurl.com/api-create.php?url={encoded_url}"
        res = requests.get(api_url, timeout=5)
        if res.status_code == 200 and res.text.startswith('http'):
            return res.text.strip()
    except Exception as e:
        print(f"⚠️ 短網址失敗: {e}")
    
    return long_url

def create_flex_message_news(title, source_name, url, category):
    """創建 Flex Message 格式的新聞卡片"""
    
    # 限制標題長度避免顯示問題
    display_title = title[:60] + "..." if len(title) > 60 else title
    
    flex_message = {
        "type": "flex",
        "altText": f"📰 {display_title}",
        "contents": {
            "type": "bubble",
            "size": "kilo",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "📰 新聞快報",
                        "weight": "bold",
                        "color": "#1DB446",
                        "size": "sm"
                    }
                ],
                "backgroundColor": "#F0F8F0",
                "paddingAll": "8px"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": display_title,
                        "weight": "bold",
                        "size": "md",
                        "wrap": True,
                        "color": "#333333"
                    },
                    {
                        "type": "separator",
                        "margin": "md"
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "margin": "md",
                        "contents": [
                            {
                                "type": "text",
                                "text": f"📌 {source_name}",
                                "size": "sm",
                                "color": "#666666"
                            },
                            {
                                "type": "text",
                                "text": f"📂 {category}",
                                "size": "sm",
                                "color": "#666666",
                                "margin": "xs"
                            },
                            {
                                "type": "text",
                                "text": f"⏰ {now.strftime('%m/%d %H:%M')}",
                                "size": "sm",
                                "color": "#666666",
                                "margin": "xs"
                            }
                        ]
                    }
                ],
                "paddingAll": "12px"
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "action": {
                            "type": "uri",
                            "uri": url
                        },
                        "text": "閱讀完整報導",
                        "color": "#1DB446"
                    }
                ],
                "paddingAll": "8px"
            }
        }
    }
    
    return flex_message

def create_text_message_with_button(title, source_name, url):
    """創建帶按鈕的文字訊息（備用方案）"""
    return {
        "type": "template",
        "altText": f"📰 {title[:50]}...",
        "template": {
            "type": "buttons",
            "text": f"📰 {title[:60]}...\n\n📌 來源：{source_name}\n⏰ {now.strftime('%m/%d %H:%M')}",
            "actions": [
                {
                    "type": "uri",
                    "label": "閱讀完整報導",
                    "uri": url
                }
            ]
        }
    }

def create_simple_text_with_hidden_url(title, source_name, url):
    """創建純文字訊息，網址隱藏在文字中"""
    # 使用特殊的 Unicode 字符來隱藏網址
    hidden_url = f"詳細報導"  # 這個文字實際上會是可點擊的
    
    message_text = f"""📰 {title}
📌 來源：{source_name}
📅 {now.strftime('%Y-%m-%d %H:%M')}

🔗 點擊「{hidden_url}」查看完整內容"""
    
    return {
        "type": "text",
        "text": message_text
    }

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

            # 🔑 處理網址
            clean_url = create_simple_clean_url(link)
            category = classify_news(title)
            
            # 🔑 備用方案：Button Template（更簡單）
            button_news = create_text_message_with_button(title, source_name, clean_url)
            
            # 🔑 主要方案：Flex Message（推薦）
            # flex_news = create_flex_message_news(title, source_name, clean_url, category)
            
            classified_news[category].append(button_news)

            # ✅ 新增向量（用正規化後標題）
            norm_title = normalize_title(title)
            known_titles_vecs.append(model.encode(norm_title))

    return classified_news

def send_flex_messages_by_category(news_by_category):
    """發送 Flex Message 格式的新聞"""
    sent_count = 0
    
    for category, flex_messages in news_by_category.items():
        if flex_messages:
            # 發送分類標題
            category_title = f"【{today} 業企部 今日【{category}】重點新聞整理】 共{len(flex_messages)}則新聞"
            broadcast_text_message(category_title)
            
            # 發送 Flex Messages（一次最多發送10個）
            for i in range(0, len(flex_messages), 10):
                batch = flex_messages[i:i+10]
                if broadcast_flex_messages(batch):
                    sent_count += len(batch)
                time.sleep(1)  # 避免發送過快
        else:
            # 發送無新聞通知
            no_news_msg = f"📂【{category}】今日無相關新聞"
            broadcast_text_message(no_news_msg)
    
    print(f"✅ 成功發送 {sent_count} 則 Flex Message 新聞")

def broadcast_flex_messages(flex_messages):
    """發送 Flex Messages"""
    url = 'https://api.line.me/v2/bot/message/broadcast'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {ACCESS_TOKEN}'
    }

    # 如果只有一則新聞，直接發送
    if len(flex_messages) == 1:
        data = {"messages": flex_messages}
    else:
        # 多則新聞使用 Carousel
        carousel_message = {
            "type": "flex",
            "altText": f"📰 {len(flex_messages)} 則新聞",
            "contents": {
                "type": "carousel",
                "contents": [msg["contents"] for msg in flex_messages]
            }
        }
        data = {"messages": [carousel_message]}

    try:
        print(f"📤 發送 {len(flex_messages)} 則 Flex Message")
        res = requests.post(url, headers=headers, json=data, timeout=15)
        
        if res.status_code == 200:
            print("✅ Flex Message 發送成功")
            return True
        else:
            print(f"❌ Flex Message 發送失敗: {res.status_code} - {res.text}")
            return False
            
    except Exception as e:
        print(f"❌ 發送 Flex Message 異常: {e}")
        return False

def broadcast_text_message(message):
    """發送純文字訊息"""
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

    try:
        res = requests.post(url, headers=headers, json=data, timeout=15)
        return res.status_code == 200
    except:
        return False

if __name__ == "__main__":
    print("🚀 使用 Flex Message 格式發送新聞")
    
    news = fetch_news()
    if any(news.values()):
        send_flex_messages_by_category(news)
    else:
        print("⚠️ 沒有符合條件的新聞，不發送。")
        broadcast_text_message(f"【{today} 業企部新聞】\n今日暫無符合條件的重點新聞")


