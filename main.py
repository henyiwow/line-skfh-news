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

# ✅ 分類 emoji 映射
CATEGORY_EMOJIS = {
    "新光金控": "🌟",
    "台新金控": "🏢", 
    "金控": "🏦",
    "保險": "🛡️",
    "其他": "📰"
}

# ✅ 標題正規化
def normalize_title(title):
    title = re.sub(r'[｜|‧\-－–—~～].*$', '', title)  # 移除媒體後綴
    title = re.sub(r'<[^>]+>', '', title)            # 移除 HTML 標籤
    title = re.sub(r'[^\w\u4e00-\u9fff\s]', '', title)  # 移除非文字符號
    title = re.sub(r'\s+', ' ', title)               # 多餘空白
    return title.strip().lower()

# 🔧 改進的短網址服務 - 支援多種服務
def shorten_url(long_url, service='tinyurl'):
    """
    支援多種短網址服務
    service: 'tinyurl', 'is.gd', 'v.gd'
    """
    try:
        if service == 'tinyurl':
            encoded_url = quote(long_url, safe='')
            api_url = f"http://tinyurl.com/api-create.php?url={encoded_url}"
            res = requests.get(api_url, timeout=5)
            if res.status_code == 200 and res.text.startswith('http'):
                return res.text.strip()
        
        elif service == 'is.gd':
            api_url = "https://is.gd/create.php"
            data = {'format': 'simple', 'url': long_url}
            res = requests.post(api_url, data=data, timeout=5)
            if res.status_code == 200 and res.text.startswith('http'):
                return res.text.strip()
        
        elif service == 'v.gd':
            api_url = "https://v.gd/create.php"
            data = {'format': 'simple', 'url': long_url}
            res = requests.post(api_url, data=data, timeout=5)
            if res.status_code == 200 and res.text.startswith('http'):
                return res.text.strip()
                
    except Exception as e:
        print(f"⚠️ {service} 短網址失敗：", e)
    
    return long_url

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

def truncate_title(title, max_length=50):
    """截斷過長的標題"""
    if len(title) > max_length:
        return title[:max_length-3] + "..."
    return title

def format_time_ago(pub_datetime):
    """計算發布時間距離現在多久"""
    time_diff = now - pub_datetime
    hours = int(time_diff.total_seconds() / 3600)
    
    if hours == 0:
        minutes = int(time_diff.total_seconds() / 60)
        return f"{minutes}分鐘前"
    elif hours < 24:
        return f"{hours}小時前"
    else:
        return pub_datetime.strftime("%m/%d")

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

            # 🔧 嘗試多種短網址服務
            short_link = shorten_url(link, 'tinyurl')
            if short_link == link:  # 如果第一個失敗，嘗試其他服務
                short_link = shorten_url(link, 'is.gd')
            if short_link == link:
                short_link = shorten_url(link, 'v.gd')
            
            category = classify_news(title)
            
            # 🔧 建立新聞項目
            news_item = {
                'title': title,
                'source': source_name,
                'link': link,
                'short_link': short_link,
                'category': category,
                'pub_datetime': pub_datetime,
                'time_ago': format_time_ago(pub_datetime)
            }
            
            classified_news[category].append(news_item)

            # ✅ 新增向量（用正規化後標題）
            norm_title = normalize_title(title)
            known_titles_vecs.append(model.encode(norm_title))

    # 🔧 按發布時間排序（最新的在前）
    for category in classified_news:
        classified_news[category].sort(key=lambda x: x['pub_datetime'], reverse=True)

    return classified_news

# 🔧 Quick Reply 訊息建立函數
def create_quick_reply_message(news_items, category):
    """建立 Quick Reply 格式的新聞訊息"""
    if not news_items:
        return None
    
    # 🔧 取得分類 emoji
    category_emoji = CATEGORY_EMOJIS.get(category, "📰")
    
    # 🔧 建立文字內容（顯示前10則新聞摘要）
    text_lines = [
        f"📅 {today.strftime('%Y/%m/%d')} 業企部今日新聞",
        f"{category_emoji} 【{category}】共 {len(news_items)} 則新聞",
        ""
    ]
    
    # 🔧 新聞摘要列表（最多顯示10則）
    display_count = min(10, len(news_items))
    for i, item in enumerate(news_items[:display_count], 1):
        truncated_title = truncate_title(item['title'], 45)
        text_lines.append(f"{i:2d}. {truncated_title}")
        text_lines.append(f"     📌 {item['source']} • {item['time_ago']}")
        text_lines.append("")
    
    if len(news_items) > 10:
        text_lines.append(f"⬇️ 還有 {len(news_items) - 10} 則新聞，點擊下方按鈕查看")
    
    text_content = "\n".join(text_lines)
    
    # 🔧 建立 Quick Reply 按鈕（最多13個）
    quick_reply_items = []
    
    # 新聞按鈕（最多12個新聞 + 1個「更多」按鈕）
    button_count = min(12, len(news_items))
    for i, item in enumerate(news_items[:button_count]):
        quick_reply_items.append({
            "type": "action",
            "action": {
                "type": "uri",
                "label": f"📰 新聞{i+1}",
                "uri": item['link']
            }
        })
    
    # 🔧 如果新聞超過12則，添加「更多新聞」按鈕
    if len(news_items) > 12:
        # 可以鏈接到更完整的新聞頁面或發送更多新聞
        quick_reply_items.append({
            "type": "action",
            "action": {
                "type": "postback",
                "label": "📋 查看全部",
                "data": f"more_news_{category}",
                "displayText": f"查看【{category}】全部新聞"
            }
        })
    
    return {
        "type": "text",
        "text": text_content,
        "quickReply": {
            "items": quick_reply_items
        }
    }

# 🔧 建立完整新聞列表訊息（當用戶點擊「查看全部」時）
def create_full_news_list(news_items, category):
    """建立完整的新聞列表（純文字格式）"""
    category_emoji = CATEGORY_EMOJIS.get(category, "📰")
    
    text_lines = [
        f"📋 【{category}】完整新聞列表",
        f"{category_emoji} 共 {len(news_items)} 則新聞",
        f"📅 {today.strftime('%Y/%m/%d')}",
        "=" * 30,
        ""
    ]
    
    # 🔧 顯示所有新聞（每4000字元分割一次）
    current_length = len("\n".join(text_lines))
    max_length = 4000
    
    for i, item in enumerate(news_items, 1):
        news_text = f"{i:2d}. {item['title']}\n"
        news_text += f"     📌 {item['source']} • {item['time_ago']}\n"
        news_text += f"     🔗 {item['short_link']}\n\n"
        
        # 檢查是否會超過訊息長度限制
        if current_length + len(news_text) > max_length:
            # 如果會超過，先發送當前內容
            yield "\n".join(text_lines)
            # 重置為新的訊息
            text_lines = [f"📋 【{category}】新聞列表 (續)", ""]
            current_length = len("\n".join(text_lines))
        
        text_lines.append(news_text.strip())
        text_lines.append("")
        current_length += len(news_text)
    
    # 發送最後一段內容
    if len(text_lines) > 2:  # 確保不是空的
        yield "\n".join(text_lines)

def send_message_by_category(news_by_category):
    """發送分類新聞訊息（Quick Reply 格式）"""
    no_news_categories = []

    for category, news_items in news_by_category.items():
        if news_items:
            # 🔧 建立 Quick Reply 訊息
            message = create_quick_reply_message(news_items, category)
            if message:
                broadcast_message_advanced(message)
                print(f"✅ 已發送【{category}】新聞，共 {len(news_items)} 則")
        else:
            no_news_categories.append(category)

    # 🔧 發送無新聞分類的通知
    if no_news_categories:
        title = f"📅 {today.strftime('%Y/%m/%d')} 業企部新聞報告"
        content_lines = ["以下分類今日無相關新聞：", ""]
        for cat in no_news_categories:
            emoji = CATEGORY_EMOJIS.get(cat, "📰")
            content_lines.append(f"{emoji} 【{cat}】無相關新聞")
        
        no_news_message = {
            "type": "text", 
            "text": "\n".join([title] + [""] + content_lines)
        }
        broadcast_message_advanced(no_news_message)

def broadcast_message_advanced(message):
    """發送進階訊息格式"""
    url = 'https://api.line.me/v2/bot/message/broadcast'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {ACCESS_TOKEN}'
    }

    data = {"messages": [message]}

    print(f"📤 發送訊息類型：{message.get('type', 'unknown')}")
    res = requests.post(url, headers=headers, json=data)
    print(f"📤 LINE 回傳狀態碼：{res.status_code}")
    if res.status_code != 200:
        print("📤 LINE 回傳內容：", res.text)
    else:
        print("✅ 訊息發送成功")

# 🔧 處理 Postback 事件（當用戶點擊「查看全部」時）
def handle_postback(event_data):
    """處理 Postback 事件"""
    if event_data.startswith("more_news_"):
        category = event_data.replace("more_news_", "")
        
        # 重新獲取該分類的新聞
        news = fetch_news()
        if category in news and news[category]:
            # 發送完整新聞列表
            for message_text in create_full_news_list(news[category], category):
                simple_message = {"type": "text", "text": message_text}
                broadcast_message_advanced(simple_message)
        else:
            error_message = {
                "type": "text", 
                "text": f"❌ 找不到【{category}】的新聞資料"
            }
            broadcast_message_advanced(error_message)

if __name__ == "__main__":
    print("🚀 開始執行 LINE 新聞機器人（Quick Reply 版本）")
    print(f"📅 執行時間：{now.strftime('%Y-%m-%d %H:%M:%S')}")
    
    news = fetch_news()
    if any(news_items for news_items in news.values()):
        send_message_by_category(news)
        
        # 🔧 統計信息
        total_news = sum(len(news_items) for news_items in news.values())
        print(f"✅ 新聞推播完成！總共處理 {total_news} 則新聞")
        for category, news_items in news.items():
            if news_items:
                print(f"   📊 【{category}】: {len(news_items)} 則")
    else:
        print("⚠️ 沒有符合條件的新聞，不發送。")



