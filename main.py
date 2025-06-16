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

# ✅ 智能判斷模式門檻
UNIFIED_MODE_THRESHOLD = 15  # ≤15則用統一訊息，≥16則用分類選單

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

# 🧠 智能判斷策略
def smart_message_strategy(news_by_category):
    """
    智能判斷使用哪種訊息模式
    返回: 'unified' 或 'category_menu'
    """
    total_news = sum(len(items) for items in news_by_category.values() if items)
    
    if total_news <= UNIFIED_MODE_THRESHOLD:
        return "unified"        # 統一訊息模式
    else:
        return "category_menu"  # 分類選單模式

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

# 📱 模式一：統一訊息模式 (≤15則新聞)
def create_unified_message(news_by_category):
    """建立統一訊息格式"""
    # 🔧 統計總新聞數
    total_news = sum(len(news_items) for news_items in news_by_category.values() if news_items)
    
    if total_news == 0:
        return {
            "type": "text",
            "text": f"📅 {today.strftime('%Y/%m/%d')} 業企部今日新聞\n\n❌ 今日暫無相關新聞"
        }
    
    # 🔧 建立統一訊息內容
    text_lines = [
        f"📅 {today.strftime('%Y/%m/%d')} 業企部今日新聞總覽",
        f"📊 共 {total_news} 則新聞",
        "=" * 35,
        ""
    ]
    
    # 🔧 收集所有新聞並編號
    all_news = []
    news_counter = 1
    
    for category, news_items in news_by_category.items():
        if not news_items:
            continue
            
        category_emoji = CATEGORY_EMOJIS.get(category, "📰")
        text_lines.append(f"{category_emoji} 【{category}】{len(news_items)} 則")
        text_lines.append("")
        
        # 顯示新聞詳情（如果總數<=10則全顯示，否則每分類最多顯示3則）
        if total_news <= 10:
            display_count = len(news_items)
        else:
            display_count = min(3, len(news_items))
            
        for item in news_items[:display_count]:
            truncated_title = truncate_title(item['title'], 40)
            text_lines.append(f"{news_counter:2d}. {truncated_title}")
            text_lines.append(f"     📌 {item['source']} • {item['time_ago']}")
            text_lines.append("")
            
            # 添加到全部新聞列表
            all_news.append(item)
            news_counter += 1
        
        # 如果該分類有更多新聞未顯示
        if len(news_items) > display_count:
            for item in news_items[display_count:]:
                all_news.append(item)
            text_lines.append(f"     ⬇️ 還有 {len(news_items) - display_count} 則新聞")
            text_lines.append("")
    
    text_content = "\n".join(text_lines)
    
    # 🔧 建立 Quick Reply 按鈕（最多 13 個）
    quick_reply_items = []
    
    # 顯示的新聞按鈕（最多 10 個）
    displayed_count = min(10, news_counter - 1)
    for i in range(displayed_count):
        quick_reply_items.append({
            "type": "action",
            "action": {
                "type": "uri",
                "label": f"📰 {i+1}",
                "uri": all_news[i]['link']
            }
        })
    
    # 如果有更多新聞，添加「查看全部」按鈕
    if len(all_news) > displayed_count:
        quick_reply_items.append({
            "type": "action",
            "action": {
                "type": "postback",
                "label": f"📋 全部{total_news}則",
                "data": "view_all_news",
                "displayText": "查看全部新聞"
            }
        })
    
    return {
        "type": "text",
        "text": text_content,
        "quickReply": {
            "items": quick_reply_items
        }
    }

# 📋 模式二：分類選單模式 (≥16則新聞)
def create_category_menu_message(news_by_category):
    """建立分類選單訊息"""
    # 🔧 統計總新聞數
    total_news = sum(len(news_items) for news_items in news_by_category.values() if news_items)
    
    if total_news == 0:
        return {
            "type": "text",
            "text": f"📅 {today.strftime('%Y/%m/%d')} 業企部今日新聞\n\n❌ 今日暫無相關新聞"
        }
    
    # 🔧 建立總覽訊息
    text_lines = [
        f"📅 {today.strftime('%Y/%m/%d')} 業企部今日新聞總覽",
        f"📊 共 {total_news} 則新聞 - 請選擇分類瀏覽",
        "=" * 40,
        ""
    ]
    
    # 🔧 分類統計
    text_lines.append("📊 分類統計")
    text_lines.append("")
    
    categories_with_news = []
    for category, news_items in news_by_category.items():
        if not news_items:
            continue
            
        category_emoji = CATEGORY_EMOJIS.get(category, "📰")
        
        # 取前2則新聞標題作為預覽
        preview_titles = []
        for item in news_items[:2]:
            preview_titles.append(truncate_title(item['title'], 25))
        
        preview_text = "、".join(preview_titles)
        if len(news_items) > 2:
            preview_text += "..."
            
        text_lines.append(f"{category_emoji} 【{category}】{len(news_items)}則 - {preview_text}")
        text_lines.append("")
        
        categories_with_news.append((category, len(news_items)))
    
    text_lines.append("請選擇您想查看的分類：")
    text_content = "\n".join(text_lines)
    
    # 🔧 建立分類選單按鈕
    quick_reply_items = []
    
    # 各分類按鈕
    for category, count in categories_with_news:
        emoji = CATEGORY_EMOJIS.get(category, "📰")
        quick_reply_items.append({
            "type": "action",
            "action": {
                "type": "postback",
                "label": f"{emoji} {category}({count})",
                "data": f"category_{category}",
                "displayText": f"查看【{category}】新聞"
            }
        })
    
    # 特殊功能按鈕
    if len(quick_reply_items) < 11:  # 確保不超過13個按鈕限制
        quick_reply_items.extend([
            {
                "type": "action",
                "action": {
                    "type": "postback",
                    "label": "⭐ 今日重點",
                    "data": "today_highlights",
                    "displayText": "查看今日重點新聞"
                }
            },
            {
                "type": "action",
                "action": {
                    "type": "postback",
                    "label": "📊 全部摘要",
                    "data": "all_summary",
                    "displayText": "查看全部新聞摘要"
                }
            }
        ])
    
    return {
        "type": "text",
        "text": text_content,
        "quickReply": {
            "items": quick_reply_items
        }
    }

def create_category_detail_message(news_items, category):
    """建立特定分類的詳細新聞訊息"""
    if not news_items:
        return {
            "type": "text",
            "text": f"❌ 【{category}】分類暫無新聞"
        }
    
    category_emoji = CATEGORY_EMOJIS.get(category, "📰")
    
    text_lines = [
        f"{category_emoji} 【{category}】詳細新聞",
        f"📊 共 {len(news_items)} 則新聞",
        "=" * 30,
        ""
    ]
    
    # 顯示新聞列表（最多顯示8則詳情）
    display_count = min(8, len(news_items))
    for i, item in enumerate(news_items[:display_count], 1):
        text_lines.append(f"{i:2d}. {item['title']}")
        text_lines.append(f"     📌 {item['source']} • {item['time_ago']}")
        text_lines.append("")
    
    if len(news_items) > display_count:
        text_lines.append(f"⬇️ 還有 {len(news_items) - display_count} 則新聞，使用下方按鈕查看")
    
    text_content = "\n".join(text_lines)
    
    # 建立該分類的按鈕
    quick_reply_items = []
    
    # 新聞按鈕（最多10個）
    button_count = min(10, len(news_items))
    for i in range(button_count):
        quick_reply_items.append({
            "type": "action",
            "action": {
                "type": "uri",
                "label": f"📰 {i+1}",
                "uri": news_items[i]['link']
            }
        })
    
    # 功能按鈕
    if len(news_items) > 10:
        quick_reply_items.append({
            "type": "action",
            "action": {
                "type": "postback",
                "label": f"📋 更多新聞",
                "data": f"more_{category}",
                "displayText": f"查看【{category}】更多新聞"
            }
        })
    
    quick_reply_items.append({
        "type": "action",
        "action": {
            "type": "postback",
            "label": "🔙 返回選單",
            "data": "back_to_menu",
            "displayText": "返回分類選單"
        }
    })
    
    return {
        "type": "text",
        "text": text_content,
        "quickReply": {
            "items": quick_reply_items
        }
    }

def send_message_by_strategy(news_by_category):
    """根據智能策略發送訊息"""
    strategy = smart_message_strategy(news_by_category)
    total_news = sum(len(items) for items in news_by_category.values() if items)
    
    print(f"🧠 智能判斷：總共 {total_news} 則新聞，使用 {strategy} 模式")
    
    if strategy == "unified":
        # 📱 統一訊息模式
        message = create_unified_message(news_by_category)
        broadcast_message_advanced(message)
        print(f"✅ 已發送統一訊息模式，共 {total_news} 則新聞")
        
    elif strategy == "category_menu":
        # 📋 分類選單模式
        message = create_category_menu_message(news_by_category)
        broadcast_message_advanced(message)
        print(f"✅ 已發送分類選單模式，共 {total_news} 則新聞")
    
    # 🔧 如果沒有新聞，發送無新聞通知
    if total_news == 0:
        no_news_message = {
            "type": "text",
            "text": f"📅 {today.strftime('%Y/%m/%d')} 業企部新聞報告\n\n❌ 今日暫無相關新聞，請稍後再試。"
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
        print("❌ LINE 回傳錯誤：", res.text)
    else:
        print("✅ 訊息發送成功")

# 🔧 處理 Postback 事件（當用戶點擊按鈕時）
def handle_postback(event_data, news_by_category):
    """處理用戶的 Postback 事件"""
    print(f"📥 收到 Postback 事件：{event_data}")
    
    if event_data.startswith("category_"):
        # 用戶選擇特定分類
        category = event_data.replace("category_", "")
        if category in news_by_category and news_by_category[category]:
            message = create_category_detail_message(news_by_category[category], category)
            broadcast_message_advanced(message)
        else:
            error_message = {
                "type": "text", 
                "text": f"❌ 找不到【{category}】的新聞資料"
            }
            broadcast_message_advanced(error_message)
    
    elif event_data == "today_highlights":
        # 今日重點新聞（新光金控 + 台新金控）
        highlight_news = []
        for category in ["新光金控", "台新金控"]:
            if category in news_by_category:
                highlight_news.extend(news_by_category[category][:3])  # 每個分類取前3則
        
        if highlight_news:
            # 建立重點新聞訊息
            text_lines = [
                f"⭐ {today.strftime('%Y/%m/%d')} 今日重點新聞",
                f"📊 共 {len(highlight_news)} 則重點新聞",
                "=" * 30,
                ""
            ]
            
            for i, item in enumerate(highlight_news, 1):
                text_lines.append(f"{i:2d}. {item['title']}")
                text_lines.append(f"     📌 {item['source']} • {item['time_ago']}")
                text_lines.append("")
            
            quick_reply_items = []
            for i, item in enumerate(highlight_news):
                quick_reply_items.append({
                    "type": "action",
                    "action": {
                        "type": "uri",
                        "label": f"📰 {i+1}",
                        "uri": item['link']
                    }
                })
            
            quick_reply_items.append({
                "type": "action",
                "action": {
                    "type": "postback",
                    "label": "🔙 返回選單",
                    "data": "back_to_menu",
                    "displayText": "返回分類選單"
                }
            })
            
            message = {
                "type": "text",
                "text": "\n".join(text_lines),
                "quickReply": {"items": quick_reply_items}
            }
            broadcast_message_advanced(message)
    
    elif event_data == "back_to_menu":
        # 返回分類選單
        message = create_category_menu_message(news_by_category)
        broadcast_message_advanced(message)
    
    elif event_data == "view_all_news":
        # 查看全部新聞（統一模式的延伸）
        all_news = []
        for category, news_items in news_by_category.items():
            if news_items:
                all_news.extend(news_items)
        
        # 按時間排序
        all_news.sort(key=lambda x: x['pub_datetime'], reverse=True)
        
        # 分批發送（每批最多10則）
        for i in range(0, len(all_news), 10):
            batch = all_news[i:i+10]
            batch_num = i // 10 + 1
            total_batches = (len(all_news) - 1) // 10 + 1
            
            text_lines = [
                f"📋 全部新聞詳細列表 ({batch_num}/{total_batches})",
                f"📊 第 {i+1}-{min(i+10, len(all_news))} 則 / 共 {len(all_news)} 則",
                "=" * 30,
                ""
            ]
            
            for j, item in enumerate(batch, i+1):
                text_lines.append(f"{j:2d}. {item['title']}")
                text_lines.append(f"     📌 {item['source']} • {item['time_ago']}")
                text_lines.append(f"     🔗 {item['short_link']}")
                text_lines.append("")
            
            simple_message = {"type": "text", "text": "\n".join(text_lines)}
            broadcast_message_advanced(simple_message)
            
            # 避免發送太快
            if i + 10 < len(all_news):
                time.sleep(1)

if __name__ == "__main__":
    print("🚀 開始執行智能兩模式 LINE 新聞機器人")
    print(f"📅 執行時間：{now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🧠 智能判斷門檻：≤{UNIFIED_MODE_THRESHOLD}則用統一訊息，≥{UNIFIED_MODE_THRESHOLD+1}則用分類選單")
    
    # 抓取新聞
    news = fetch_news()
    
    # 檢查是否有新聞
    if any(news_items for news_items in news.values()):
        # 使用智能策略發送新聞
        send_message_by_strategy(news)
        
        # 🔧 統計信息
        total_news = sum(len(news_items) for news_items in news.values())
        strategy = smart_message_strategy(news)
        
        print(f"✅ 新聞推播完成！")
        print(f"📊 使用策略：{strategy}")
        print(f"📈 總共處理：{total_news} 則新聞")
        
        for category, news_items in news.items():
            if news_items:
                print(f"   📁 【{category}】: {len(news_items)} 則")
    else:
        print("⚠️ 沒有符合條件的新聞，不發送。")
        
    print("🏁 程式執行完成")

