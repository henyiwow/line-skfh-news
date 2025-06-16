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

# Initialize semantic model
model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')

# Similarity threshold
SIMILARITY_THRESHOLD = 0.95

ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')
print("Access Token first 10 chars:", ACCESS_TOKEN[:10] if ACCESS_TOKEN else "Not set")

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

# Category emoji mapping
CATEGORY_EMOJIS = {
    "新光金控": "🌟",
    "台新金控": "🏢", 
    "金控": "🏦",
    "保險": "🛡️",
    "其他": "📰"
}

# Smart mode threshold
UNIFIED_MODE_THRESHOLD = 8  # 調整為8則，確保有足夠按鈕空間

def normalize_title(title):
    """Normalize title for comparison"""
    title = re.sub(r'[｜|‧\-－–—~～].*$', '', title)
    title = re.sub(r'<[^>]+>', '', title)
    title = re.sub(r'[^\w\u4e00-\u9fff\s]', '', title)
    title = re.sub(r'\s+', ' ', title)
    return title.strip().lower()

def shorten_url(long_url, service='tinyurl'):
    """Support multiple URL shortening services"""
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
        print(f"URL shortening failed for {service}: {e}")
    
    return long_url

def classify_news(title):
    """Classify news by category"""
    title = normalize_title(title)
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw.lower() in title for kw in keywords):
            return category
    return "其他"

def is_taiwan_news(source_name, link):
    """Check if news is from Taiwan"""
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
    """Check if title is similar to known titles"""
    norm_title = normalize_title(title)
    vec = model.encode([norm_title])
    if not known_titles_vecs:
        return False
    sims = cosine_similarity(vec, known_titles_vecs)[0]
    return np.max(sims) >= SIMILARITY_THRESHOLD

def truncate_title(title, max_length=50):
    """Truncate long titles"""
    if len(title) > max_length:
        return title[:max_length-3] + "..."
    return title

def format_time_ago(pub_datetime):
    """Format time difference"""
    time_diff = now - pub_datetime
    hours = int(time_diff.total_seconds() / 3600)
    
    if hours == 0:
        minutes = int(time_diff.total_seconds() / 60)
        return f"{minutes}分鐘前"
    elif hours < 24:
        return f"{hours}小時前"
    else:
        return pub_datetime.strftime("%m/%d")

def smart_message_strategy(news_by_category):
    """Smart strategy to determine message mode"""
    total_news = sum(len(items) for items in news_by_category.values() if items)
    
    if total_news <= UNIFIED_MODE_THRESHOLD:
        return "unified"
    else:
        return "category_menu"

def fetch_news():
    """Fetch news from RSS sources"""
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
        try:
            res = requests.get(rss_url, timeout=10)
            print(f"Source: {rss_url} Status: {res.status_code}")
            if res.status_code != 200:
                continue

            root = ET.fromstring(res.content)
            items = root.findall(".//item")
            print(f"Found {len(items)} items from this source")

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

                # Try multiple URL shortening services
                short_link = shorten_url(link, 'tinyurl')
                if short_link == link:
                    short_link = shorten_url(link, 'is.gd')
                if short_link == link:
                    short_link = shorten_url(link, 'v.gd')
                
                category = classify_news(title)
                
                # Create news item
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

                # Add vector for similarity check
                norm_title = normalize_title(title)
                known_titles_vecs.append(model.encode(norm_title))
        
        except Exception as e:
            print(f"Error processing RSS source: {e}")
            continue

    # Sort by publication time (newest first)
    for category in classified_news:
        classified_news[category].sort(key=lambda x: x['pub_datetime'], reverse=True)

    return classified_news

def create_improved_unified_message(news_by_category):
    """創建改良版統一訊息 - 只顯示標題，所有新聞都有按鈕"""
    total_news = sum(len(news_items) for news_items in news_by_category.values() if news_items)
    
    if total_news == 0:
        return {
            "type": "text",
            "text": f"📅 {today.strftime('%Y/%m/%d')} 業企部今日新聞\n\n❌ 今日暫無相關新聞"
        }
    
    # 創建簡潔的訊息內容（只顯示標題）
    text_lines = [
        f"📅 {today.strftime('%Y/%m/%d')} 業企部今日新聞",
        f"📊 共 {total_news} 則新聞",
        "=" * 30,
        ""
    ]
    
    # 收集所有新聞並編號
    all_news = []
    news_counter = 1
    
    for category, news_items in news_by_category.items():
        if not news_items:
            continue
            
        category_emoji = CATEGORY_EMOJIS.get(category, "📰")
        text_lines.append(f"{category_emoji} 【{category}】{len(news_items)} 則")
        text_lines.append("")
        
        # 只顯示標題，不顯示網址
        for item in news_items:
            truncated_title = truncate_title(item['title'], 50)
            text_lines.append(f"{news_counter:2d}. {truncated_title}")
            text_lines.append(f"     📌 {item['source']} • {item['time_ago']}")
            text_lines.append("")
            
            all_news.append(item)
            news_counter += 1
    
    # 使用說明
    text_lines.extend([
        "📱 使用方式：",
        "• 點擊下方按鈕直接閱讀新聞",
        "• 所有新聞都可快速瀏覽",
        ""
    ])
    
    text_content = "\n".join(text_lines)
    
    # 創建所有新聞的按鈕（最多13個，如果超過則分批）
    quick_reply_items = []
    
    if len(all_news) <= 12:
        # 如果新聞少於等於12則，全部都有按鈕
        for i, item in enumerate(all_news):
            quick_reply_items.append({
                "type": "action",
                "action": {
                    "type": "uri",
                    "label": f"📰 {i+1}",
                    "uri": item['link']
                }
            })
    else:
        # 如果超過12則，前11個有按鈕，第12個是「更多新聞」
        for i in range(11):
            quick_reply_items.append({
                "type": "action",
                "action": {
                    "type": "uri",
                    "label": f"📰 {i+1}",
                    "uri": all_news[i]['link']
                }
            })
        
        quick_reply_items.append({
            "type": "action",
            "action": {
                "type": "postback",
                "label": f"📋 第12-{total_news}則",
                "data": "view_remaining_news",
                "displayText": f"查看第12-{total_news}則新聞"
            }
        })
    
    return {
        "type": "text",
        "text": text_content,
        "quickReply": {
            "items": quick_reply_items
        }
    }

def create_remaining_news_message(all_news, start_index=11):
    """創建剩餘新聞訊息"""
    remaining_news = all_news[start_index:]
    
    if not remaining_news:
        return {
            "type": "text",
            "text": "❌ 沒有更多新聞了"
        }
    
    text_lines = [
        f"📋 第{start_index+1}-{len(all_news)}則新聞",
        f"📊 共 {len(remaining_news)} 則剩餘新聞",
        "=" * 25,
        ""
    ]
    
    # 顯示剩餘新聞標題
    for i, item in enumerate(remaining_news, start_index+1):
        truncated_title = truncate_title(item['title'], 50)
        text_lines.append(f"{i:2d}. {truncated_title}")
        text_lines.append(f"     📌 {item['source']} • {item['time_ago']}")
        text_lines.append("")
    
    text_lines.extend([
        "📱 使用方式：",
        "• 點擊下方按鈕直接閱讀新聞"
    ])
    
    text_content = "\n".join(text_lines)
    
    # 為剩餘新聞創建按鈕
    quick_reply_items = []
    
    # 最多12個剩餘新聞按鈕
    button_count = min(12, len(remaining_news))
    for i in range(button_count):
        actual_index = start_index + i
        quick_reply_items.append({
            "type": "action",
            "action": {
                "type": "uri",
                "label": f"📰 {actual_index+1}",
                "uri": remaining_news[i]['link']
            }
        })
    
    # 如果還有更多新聞
    if len(remaining_news) > 12:
        next_start = start_index + 12
        quick_reply_items.append({
            "type": "action",
            "action": {
                "type": "postback",
                "label": f"📋 第{next_start+1}則起",
                "data": f"view_more_news_{next_start}",
                "displayText": f"查看第{next_start+1}則開始的新聞"
            }
        })
    
    return {
        "type": "text",
        "text": text_content,
        "quickReply": {
            "items": quick_reply_items
        }
    }

def create_category_menu_message(news_by_category):
    """Create category menu message"""
    total_news = sum(len(news_items) for news_items in news_by_category.values() if news_items)
    
    if total_news == 0:
        return {
            "type": "text",
            "text": f"📅 {today.strftime('%Y/%m/%d')} 業企部今日新聞\n\n❌ 今日暫無相關新聞"
        }
    
    text_lines = [
        f"📅 {today.strftime('%Y/%m/%d')} 業企部今日新聞總覽",
        f"📊 共 {total_news} 則新聞 - 請選擇分類瀏覽",
        "=" * 40,
        ""
    ]
    
    text_lines.append("📊 分類統計")
    text_lines.append("")
    
    categories_with_news = []
    for category, news_items in news_by_category.items():
        if not news_items:
            continue
            
        category_emoji = CATEGORY_EMOJIS.get(category, "📰")
        
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
    
    quick_reply_items = []
    
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
    
    if len(quick_reply_items) < 11:
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
    """Create detailed news message for specific category"""
    if not news_items:
        return {
            "type": "text",
            "text": f"❌ 【{category}】分類暫無新聞"
        }
    
    category_emoji = CATEGORY_EMOJIS.get(category, "📰")
    
    text_lines = [
        f"{category_emoji} 【{category}】新聞列表",
        f"📊 共 {len(news_items)} 則新聞",
        "=" * 25,
        ""
    ]
    
    # 顯示所有新聞標題
    for i, item in enumerate(news_items, 1):
        truncated_title = truncate_title(item['title'], 50)
        text_lines.append(f"{i:2d}. {truncated_title}")
        text_lines.append(f"     📌 {item['source']} • {item['time_ago']}")
        text_lines.append("")
    
    text_lines.extend([
        "📱 使用方式：",
        "• 點擊下方按鈕直接閱讀新聞"
    ])
    
    text_content = "\n".join(text_lines)
    
    # 創建按鈕
    quick_reply_items = []
    
    # 最多11個新聞按鈕 + 1個返回按鈕
    button_count = min(11, len(news_items))
    for i in range(button_count):
        quick_reply_items.append({
            "type": "action",
            "action": {
                "type": "uri",
                "label": f"📰 {i+1}",
                "uri": news_items[i]['link']
            }
        })
    
    # 如果有更多新聞
    if len(news_items) > 11:
        quick_reply_items.append({
            "type": "action",
            "action": {
                "type": "postback",
                "label": f"📋 第12-{len(news_items)}則",
                "data": f"category_more_{category}",
                "displayText": f"查看【{category}】第12-{len(news_items)}則新聞"
            }
        })
    else:
        # 返回選單按鈕
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

def send_message_by_improved_strategy(news_by_category):
    """Send message using improved strategy"""
    strategy = smart_message_strategy(news_by_category)
    total_news = sum(len(items) for items in news_by_category.values() if items)
    
    print(f"Smart decision: {total_news} total news, using {strategy} mode")
    print(f"Using improved mode - all news accessible via buttons")
    
    if strategy == "unified":
        message = create_improved_unified_message(news_by_category)
        broadcast_message_advanced(message)
        print(f"Sent improved unified message with {total_news} news")
    elif strategy == "category_menu":
        message = create_category_menu_message(news_by_category)
        broadcast_message_advanced(message)
        print(f"Sent category menu mode with {total_news} news")
    
    if total_news == 0:
        no_news_message = {
            "type": "text",
            "text": f"📅 {today.strftime('%Y/%m/%d')} 業企部新聞報告\n\n❌ 今日暫無相關新聞，請稍後再試。"
        }
        broadcast_message_advanced(no_news_message)

def broadcast_message_advanced(message):
    """Send advanced message format"""
    url = 'https://api.line.me/v2/bot/message/broadcast'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {ACCESS_TOKEN}'
    }

    data = {"messages": [message]}

    print(f"Sending message type: {message.get('type', 'unknown')}")
    try:
        res = requests.post(url, headers=headers, json=data, timeout=10)
        print(f"LINE API response status: {res.status_code}")
        
        if res.status_code != 200:
            print("LINE API error:", res.text)
        else:
            print("Message sent successfully")
    except Exception as e:
        print(f"Error sending message: {e}")

def handle_postback(event_data, news_by_category):
    """Handle user Postback events"""
    print(f"Received Postback event: {event_data}")
    
    try:
        if event_data == "view_remaining_news":
            # 查看剩餘新聞
            all_news = []
            for category, news_items in news_by_category.items():
                if news_items:
                    all_news.extend(news_items)
            all_news.sort(key=lambda x: x['pub_datetime'], reverse=True)
            
            message = create_remaining_news_message(all_news, 11)
            broadcast_message_advanced(message)
            
        elif event_data.startswith("view_more_news_"):
            # 查看更多新聞（指定起始位置）
            start_index = int(event_data.replace("view_more_news_", ""))
            all_news = []
            for category, news_items in news_by_category.items():
                if news_items:
                    all_news.extend(news_items)
            all_news.sort(key=lambda x: x['pub_datetime'], reverse=True)
            
            message = create_remaining_news_message(all_news, start_index)
            broadcast_message_advanced(message)
            
        elif event_data.startswith("category_"):
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
                
        elif event_data.startswith("category_more_"):
            # 查看分類的更多新聞
            category = event_data.replace("category_more_", "")
            if category in news_by_category and news_by_category[category]:
                news_items = news_by_category[category]
                remaining_news = news_items[11:]
                
                if remaining_news:
                    category_emoji = CATEGORY_EMOJIS.get(category, "📰")
                    text_lines = [
                        f"{category_emoji} 【{category}】第12-{len(news_items)}則新聞",
                        f"📊 共 {len(remaining_news)} 則剩餘新聞",
                        "=" * 25,
                        ""
                    ]
                    
                    for i, item in enumerate(remaining_news, 12):
                        truncated_title = truncate_title(item['title'], 50)
                        text_lines.append(f"{i:2d}. {truncated_title}")
                        text_lines.append(f"     📌 {item['source']} • {item['time_ago']}")
                        text_lines.append("")
                    
                    text_lines.extend([
                        "📱 使用方式：",
                        "• 點擊下方按鈕直接閱讀新聞"
                    ])
                    
                    quick_reply_items = []
                    button_count = min(12, len(remaining_news))
                    for i in range(button_count):
                        quick_reply_items.append({
                            "type": "action",
                            "action": {
                                "type": "uri",
                                "label": f"📰 {i+12}",
                                "uri": remaining_news[i]['link']
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
            
        elif event_data == "today_highlights":
            # 今日重點新聞
            highlight_news = []
            for category in ["新光金控", "台新金控"]:
                if category in news_by_category:
                    highlight_news.extend(news_by_category[category][:3])
            
            if highlight_news:
                text_lines = [
                    f"⭐ {today.strftime('%Y/%m/%d')} 今日重點新聞",
                    f"📊 共 {len(highlight_news)} 則重點新聞",
                    "=" * 25,
                    ""
                ]
                
                for i, item in enumerate(highlight_news, 1):
                    truncated_title = truncate_title(item['title'], 50)
                    text_lines.append(f"{i:2d}. {truncated_title}")
                    text_lines.append(f"     📌 {item['source']} • {item['time_ago']}")
                    text_lines.append("")
                
                text_lines.extend([
                    "📱 使用方式：",
                    "• 點擊下方按鈕直接閱讀新聞"
                ])
                
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
            else:
                no_highlights_message = {
                    "type": "text",
                    "text": "❌ 今日暫無重點新聞"
                }
                broadcast_message_advanced(no_highlights_message)
                
        elif event_data == "all_summary":
            # 全部新聞摘要
            text_lines = [
                f"📊 {today.strftime('%Y/%m/%d')} 全部新聞摘要",
                "=" * 30,
                ""
            ]
            
            total_count = 0
            for category, news_items in news_by_category.items():
                if not news_items:
                    continue
                    
                category_emoji = CATEGORY_EMOJIS.get(category, "📰")
                text_lines.append(f"{category_emoji} 【{category}】{len(news_items)} 則")
                text_lines.append("")
                
                for i, item in enumerate(news_items[:3], 1):
                    total_count += 1
                    truncated_title = truncate_title(item['title'], 40)
                    text_lines.append(f"{total_count:2d}. {truncated_title}")
                    text_lines.append(f"     📌 {item['source']} • {item['time_ago']}")
                    text_lines.append("")
                
                if len(news_items) > 3:
                    text_lines.append(f"     ⬇️ 還有 {len(news_items) - 3} 則新聞")
                    text_lines.append("")
            
            text_lines.extend([
                "📱 使用方式：",
                "• 返回選單查看完整分類新聞"
            ])
            
            quick_reply_items = [{
                "type": "action",
                "action": {
                    "type": "postback",
                    "label": "🔙 返回選單",
                    "data": "back_to_menu",
                    "displayText": "返回分類選單"
                }
            }]
            
            message = {
                "type": "text",
                "text": "\n".join(text_lines),
                "quickReply": {"items": quick_reply_items}
            }
            broadcast_message_advanced(message)
    
    except Exception as e:
        print(f"Error handling Postback event: {e}")
        error_message = {
            "type": "text",
            "text": "❌ 處理請求時發生錯誤，請稍後再試。"
        }
        broadcast_message_advanced(error_message)

if __name__ == "__main__":
    print("🚀 Starting Improved No URL Card LINE News Bot")
    print(f"📅 Execution time: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🔄 Using improved mode - all news accessible via buttons")
    print(f"🧠 Smart threshold: <={UNIFIED_MODE_THRESHOLD} use unified, >={UNIFIED_MODE_THRESHOLD+1} use category menu")
    print("💡 Features: All news accessible + No URL cards + Clean design")
    
    try:
        # Fetch news
        news = fetch_news()
        
        # Check if there are any news
        if any(news_items for news_items in news.values()):
            # Send news using improved strategy
            send_message_by_improved_strategy(news)
            
            # Statistics
            total_news = sum(len(news_items) for news_items in news.values())
            strategy = smart_message_strategy(news)
            
            print(f"✅ Improved news broadcast completed!")
            print(f"📊 Strategy used: {strategy}")
            print(f"📈 Total processed: {total_news} news items")
            print(f"🔄 All news accessible: Every news has a button")
            print(f"🎨 Clean design: No URL cards, only titles")
            
            for category, news_items in news.items():
                if news_items:
                    print(f"   📁 【{category}】: {len(news_items)} items")
        else:
            print("⚠️ No qualifying news found, not sending.")
    
    except Exception as e:
        print(f"❌ Error during execution: {e}")
        import traceback
        traceback.print_exc()
        
    print("🏁 Improved program execution completed")
    print("💡 All users can access all news via buttons")
    print("💡 Clean message design without URL cards")
    print("💡 Perfect solution for complete news access!")
