import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
import email.utils
from urllib.parse import quote
import requests
import numpy as np
import re
import time
import hashlib

# 嘗試載入 AI 模型，如果失敗則跳過
try:
    from sentence_transformers import SentenceTransformer
    from sklearn.metrics.pairwise import cosine_similarity
    model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
    print("✅ AI 模型載入成功")
    USE_AI_SIMILARITY = True
except Exception as e:
    print(f"⚠️ AI 模型載入失敗，使用基礎去重: {e}")
    model = None
    USE_AI_SIMILARITY = False

# 基本設定
ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')
DEBUG_MODE = os.getenv('DEBUG_MODE', 'false').lower() == 'true'

if ACCESS_TOKEN:
    print(f"✅ Access Token 已設定，前10碼：{ACCESS_TOKEN[:10]}")
else:
    print("❌ ACCESS_TOKEN 環境變數未設定")

# 分類關鍵字 - 放寬條件
CATEGORY_KEYWORDS = {
    "新光金控": ["新光金", "新光人壽", "新壽", "吳東進", "新光", "SKL"],
    "台新金控": ["台新金", "台新人壽", "台新壽", "吳東亮", "台新", "Taishin"],
    "金控": ["金控", "金融控股", "中信金", "玉山金", "永豐金", "國泰金", "富邦金", "台灣金", "第一金", "元大金", "銀行", "金融"],
    "保險": ["保險", "壽險", "健康險", "意外險", "人壽", "產險", "車險", "保單", "理賠"],
    "其他": []
}

# 減少排除關鍵字
EXCLUDED_KEYWORDS = ['保險套', '避孕套']

TW_TZ = timezone(timedelta(hours=8))
now = datetime.now(TW_TZ)
today = now.date()

def normalize_title(title):
    """簡化的標題正規化"""
    if not title:
        return ""
    title = re.sub(r'<[^>]+>', '', title)
    title = re.sub(r'\s+', ' ', title)
    return title.strip()

def create_short_url(long_url):
    """創建短網址"""
    try:
        encoded_url = quote(long_url, safe='')
        api_url = f"http://tinyurl.com/api-create.php?url={encoded_url}"
        res = requests.get(api_url, timeout=8)
        if res.status_code == 200 and res.text.startswith('http'):
            return res.text.strip()
    except Exception as e:
        if DEBUG_MODE:
            print(f"⚠️ 短網址失敗: {e}")
    
    return long_url

def simple_similarity_check(title1, title2):
    """簡單的文字相似度檢查"""
    words1 = set(normalize_title(title1).lower().split())
    words2 = set(normalize_title(title2).lower().split())
    if not words1 or not words2:
        return False
    
    intersection = words1.intersection(words2)
    union = words1.union(words2)
    similarity = len(intersection) / len(union) if union else 0
    return similarity > 0.8

def classify_news(title):
    """新聞分類"""
    title_lower = title.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if category == "其他":
            continue
        for keyword in keywords:
            if keyword.lower() in title_lower:
                if DEBUG_MODE:
                    print(f"📂 分類為 [{category}]: {keyword} 在 {title[:50]}")
                return category
    return "其他"

def is_taiwan_news(source_name, link):
    """判斷是否為台灣新聞 - 大幅放寬"""
    # 如果是 Google News 的連結，基本上都接受
    if 'news.google.com' in link:
        return True
    
    taiwan_sources = [
        '工商', '中國時報', '經濟', '三立', '自由', '聯合',
        '鏡週刊', '雅虎', '鉅亨', '中時', 'Ettoday', 'ETtoday',
        '天下', '遠見', '商業周刊', '今周刊', 'MoneyDJ',
        '風傳媒', '新頭殼', '中央社', 'NOWnews', 'Yahoo',
        '財訊', 'Smart', '現代保險', '保險'
    ]
    
    for taiwan_source in taiwan_sources:
        if taiwan_source in source_name:
            return True
    
    if '.tw' in link or 'taiwan' in link.lower():
        return True
    
    # 預設接受，除非明確是國外媒體
    exclude_sources = ['香港', '中國', '美國', '日本', '韓國', 'CNN', 'BBC']
    for exclude in exclude_sources:
        if exclude in source_name:
            return False
    
    return True

def create_button_template_message(title, source_name, url, category):
    """創建 Button Template 訊息"""
    # 限制標題長度（LINE Button Template 限制）
    display_title = title[:80] + "..." if len(title) > 80 else title
    
    # 創建顯示文字
    message_text = f"📰 {display_title}\n\n📌 來源：{source_name}\n📂 分類：{category}\n⏰ {now.strftime('%m/%d %H:%M')}"
    
    # 確保文字不超過 LINE 限制
    if len(message_text) > 160:
        # 縮短標題
        max_title_length = 160 - len(f"\n\n📌 來源：{source_name}\n📂 分類：{category}\n⏰ {now.strftime('%m/%d %H:%M')}")
        display_title = title[:max_title_length-10] + "..."
        message_text = f"📰 {display_title}\n\n📌 來源：{source_name}\n📂 分類：{category}\n⏰ {now.strftime('%m/%d %H:%M')}"
    
    return {
        "type": "template",
        "altText": f"📰 {title[:50]}...",
        "template": {
            "type": "buttons",
            "text": message_text,
            "actions": [
                {
                    "type": "uri",
                    "label": "閱讀完整報導",
                    "uri": url
                }
            ]
        }
    }

def fetch_news():
    """主要新聞抓取函數 - 修正版本"""
    print("🚀 開始抓取新聞...")
    
    # 使用更簡單直接的 RSS URLs
    rss_urls = [
        "https://news.google.com/rss/search?q=新光金控&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
        "https://news.google.com/rss/search?q=台新金控&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
        "https://news.google.com/rss/search?q=金控&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
        "https://news.google.com/rss/search?q=壽險&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
        "https://news.google.com/rss/search?q=保險&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    ]

    classified_news = {cat: [] for cat in CATEGORY_KEYWORDS}
    processed_titles = []  # 簡單去重
    stats = {'total': 0, 'processed': 0, 'filtered': 0, 'duplicates': 0}

    for i, rss_url in enumerate(rss_urls, 1):
        try:
            print(f"📡 處理 RSS 來源 {i}/{len(rss_urls)}")
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            res = requests.get(rss_url, timeout=20, headers=headers)
            
            if res.status_code != 200:
                print(f"⚠️ RSS 回應異常: {res.status_code}")
                continue

            print(f"✅ RSS 回應成功，內容長度: {len(res.content)}")
            
            try:
                root = ET.fromstring(res.content)
            except ET.ParseError as e:
                print(f"❌ XML 解析失敗: {e}")
                continue
            
            items = root.findall(".//item")
            stats['total'] += len(items)
            
            print(f"✅ 從來源 {i} 找到 {len(items)} 筆新聞項目")

            for j, item in enumerate(items):
                try:
                    title_elem = item.find('title')
                    link_elem = item.find('link')
                    pubDate_elem = item.find('pubDate')
                    
                    if not all([title_elem, link_elem]):
                        continue

                    title = title_elem.text.strip() if title_elem.text else ""
                    link = link_elem.text.strip() if link_elem.text else ""
                    
                    if not title or not link:
                        continue
                    
                    if title.startswith("Google ニュース") or "Google News" in title:
                        continue

                    source_elem = item.find('source')
                    source_name = source_elem.text.strip() if source_elem is not None and source_elem.text else "未標示來源"
                    
                    if DEBUG_MODE:
                        print(f"  處理第 {j+1} 筆: {title[:40]}... | 來源: {source_name}")
                    
                    # 時間檢查 - 放寬到48小時
                    if pubDate_elem is not None and pubDate_elem.text:
                        try:
                            pub_datetime = email.utils.parsedate_to_datetime(pubDate_elem.text).astimezone(TW_TZ)
                            if now - pub_datetime > timedelta(hours=48):
                                stats['filtered'] += 1
                                continue
                        except:
                            pass  # 如果時間解析失敗，就不做時間過濾
                    
                    # 排除關鍵字檢查
                    if any(bad_kw in title for bad_kw in EXCLUDED_KEYWORDS):
                        stats['filtered'] += 1
                        continue
                    
                    # 台灣新聞檢查
                    if not is_taiwan_news(source_name, link):
                        stats['filtered'] += 1
                        continue
                    
                    # 簡單去重檢查
                    is_duplicate = False
                    for processed_title in processed_titles:
                        if simple_similarity_check(title, processed_title):
                            is_duplicate = True
                            break
                    
                    if is_duplicate:
                        stats['duplicates'] += 1
                        continue
                    
                    # 處理網址
                    clean_url = create_short_url(link)
                    category = classify_news(title)
                    
                    # 創建 Button Template 訊息
                    button_message = create_button_template_message(title, source_name, clean_url, category)
                    classified_news[category].append(button_message)
                    
                    # 記錄已處理的標題
                    processed_titles.append(title)
                    stats['processed'] += 1
                    
                    if DEBUG_MODE:
                        print(f"    ✅ 成功處理: [{category}] {title[:30]}...")

                except Exception as e:
                    print(f"❌ 處理單筆新聞失敗: {e}")
                    continue

        except Exception as e:
            print(f"❌ 處理 RSS 來源 {i} 失敗: {e}")
            continue

    # 輸出統計
    print(f"""
📊 新聞處理統計:
   總抓取: {stats['total']} 筆
   成功處理: {stats['processed']} 筆
   重複過濾: {stats['duplicates']} 筆
   其他過濾: {stats['filtered']} 筆
   
   分類統計:""")
    
    for category, messages in classified_news.items():
        print(f"   📂 {category}: {len(messages)} 筆")
    
    return classified_news

def send_button_template_messages(news_by_category):
    """發送 Button Template 訊息"""
    if not ACCESS_TOKEN:
        print("❌ ACCESS_TOKEN 未設定，無法發送訊息")
        return
    
    sent_count = 0
    
    for category, messages in news_by_category.items():
        if messages:
            # 發送分類標題
            category_title = f"【{today} 業企部 今日【{category}】重點新聞】共 {len(messages)} 則"
            broadcast_text_message(category_title)
            
            # 逐一發送 Button Template 訊息
            for message in messages:
                if broadcast_template_message(message):
                    sent_count += 1
                time.sleep(0.5)  # 避免發送過快
        else:
            # 發送無新聞通知
            no_news_msg = f"📂【{category}】今日無相關新聞"
            broadcast_text_message(no_news_msg)
    
    print(f"✅ 成功發送 {sent_count} 則新聞")

def broadcast_template_message(template_message):
    """發送 Template 訊息"""
    url = 'https://api.line.me/v2/bot/message/broadcast'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {ACCESS_TOKEN}'
    }

    data = {"messages": [template_message]}

    try:
        res = requests.post(url, headers=headers, json=data, timeout=15)
        
        if res.status_code == 200:
            if DEBUG_MODE:
                print("✅ Template 訊息發送成功")
            return True
        else:
            print(f"❌ Template 訊息發送失敗: {res.status_code} - {res.text}")
            return False
            
    except Exception as e:
        print(f"❌ 發送 Template 訊息異常: {e}")
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
        if res.status_code == 200:
            if DEBUG_MODE:
                print("✅ 文字訊息發送成功")
            return True
        else:
            print(f"❌ 文字訊息發送失敗: {res.status_code}")
            return False
    except Exception as e:
        print(f"❌ 發送文字訊息異常: {e}")
        return False

if __name__ == "__main__":
    start_time = time.time()
    print(f"🚀 新聞爬取系統啟動 (Button Template 模式) - {now}")
    
    # 測試模式
    if os.getenv('DEBUG_MODE', 'false').lower() == 'true':
        DEBUG_MODE = True
        print("🔍 除錯模式已啟用")
    
    try:
        news = fetch_news()
        
        # 檢查是否有新聞
        total_news = sum(len(msgs) for msgs in news.values())
        
        if total_news > 0:
            print(f"📨 準備發送 {total_news} 則新聞")
            send_button_template_messages(news)
        else:
            print("⚠️ 沒有符合條件的新聞")
            if ACCESS_TOKEN:
                broadcast_text_message(f"【{today} 業企部新聞】\n今日暫無符合條件的重點新聞")
        
        elapsed = time.time() - start_time
        print(f"✅ 系統執行完成，耗時 {elapsed:.1f} 秒")
        
    except Exception as e:
        print(f"❌ 系統執行失敗: {e}")
        if ACCESS_TOKEN:
            broadcast_text_message(f"【系統通知】\n新聞爬取系統執行異常")
        import traceback
        traceback.print_exc()


