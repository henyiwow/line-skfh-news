import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
import email.utils
from urllib.parse import quote
import requests

ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')
print("✅ Access Token 前 10 碼：", ACCESS_TOKEN[:10] if ACCESS_TOKEN else "未設定")

PREFERRED_SOURCES = [
    '工商時報', '中國時報', '經濟日報', 'Ettoday新聞雲', '工商時報網',
    '中時新聞網', '台灣雅虎奇摩', '經濟日報網', '鉅亨網', '聯合新聞網',
    '鏡周刊網', '自由財經', '中華日報', '台灣新生報', '旺報', '三立新聞網',
    '天下雜誌', '奇摩新聞', '《現代保險》雜誌', 'MoneyDJ', '遠見雜誌',
    '自由時報', 'Ettoday財經雲', '鏡週刊Mirror Media', '匯流新聞網',
    'Newtalk新聞', '奇摩股市', 'news.cnyes.com', '中央社', '民視新聞網',
    '風傳媒', 'CMoney', '大紀元'
]

CATEGORY_KEYWORDS = {
    "新光金控": ["新光金", "新光人壽", "新壽", "吳東進"],
    "台新金控": ["台新金", "台新人壽", "台新壽", "吳東亮"],
    "金控": ["金控", "金融控股", "中信金", "玉山金", "永豐金", "國泰金", "富邦金", "台灣金"],
    "保險": ["保險", "壽險", "健康險", "意外險", "人壽"],
    "其他": []
}

EXCLUDED_KEYWORDS = ['保險套', '避孕套', '保險套使用', '太陽人壽', '大西部人壽', '美國海岸保險']
TW_TZ = timezone(timedelta(hours=8))
today = datetime.now(TW_TZ).date()

def shorten_url(long_url):
    try:
        encoded_url = quote(long_url, safe='')
        api_url = f"http://tinyurl.com/api-create.php?url={encoded_url}"
        res = requests.get(api_url, timeout=5)
        if res.status_code == 200:
            return res.text.strip()
    except Exception as e:
        print("⚠️ 短網址失敗：", e)
    return long_url

def classify_news(title):
    title = title.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw.lower() in title for kw in keywords):
            return category
    return "其他"

def is_taiwan_news(source_name, link):
    taiwan_sources = ['工商時報', '中國時報', '經濟日報', '三立新聞網', '自由時報', '聯合新聞網', '鏡週刊', '台灣雅虎', '鉅亨網', '中時新聞網','Ettoday新聞雲',
                      '天下雜誌', '奇摩新聞', '《現代保險》雜誌','遠見雜誌']
    if any(taiwan_source in source_name for taiwan_source in taiwan_sources):
        return True
    if '.tw' in link:
        return True
    return False

def fetch_news():
    rss_urls = [
        "https://news.google.com/rss/search?q=新光金控+OR+新光人壽+OR+台新金控+OR+台新人壽+OR+壽險+OR+金控+OR+人壽+OR+新壽+OR+台新壽+OR+吳東進+OR+吳東亮&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
        "https://news.google.com/rss/search?q=新光金控+OR+新光人壽+OR+新壽+OR+吳東進&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
        "https://news.google.com/rss/search?q=台新金控+OR+台新人壽+OR+台新壽+OR+吳東亮&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
        "https://news.google.com/rss/search?q=壽險+OR+保險+OR+人壽&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
        "https://news.google.com/rss/search?q=金控+OR+金融控股&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    ]

    classified_news = {cat: [] for cat in CATEGORY_KEYWORDS}
    processed_links = set()

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
            if pub_datetime.date() != today:
                continue

            if any(bad_kw in title for bad_kw in EXCLUDED_KEYWORDS):
                continue
            if not is_taiwan_news(source_name, link):
                continue
            if link in processed_links:
                continue
            processed_links.add(link)

            short_link = shorten_url(link)

            desc_elem = item.find('description')
            description = desc_elem.text.strip() if desc_elem is not None else ""
            summary = description[:50] + "..." if description else ""

            category = classify_news(title)
            formatted = f"📰 {title}\n📌 來源：{source_name}\n📝 {summary}\n🔗 {short_link}"
            classified_news[category].append(formatted)

    return classified_news

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

def send_message_by_category(news_by_category):
    max_length = 4000
    no_news_categories = []

    for category, messages in news_by_category.items():
        if messages:
            title = f"【{today} 業企部 今日【{category}】重點新聞整理】 共{len(messages)}則新聞"
            content = "\n".join(messages)
            full_message = f"{title}\n\n{content}"
            for i in range(0, len(full_message), max_length):
                broadcast_message(full_message[i:i + max_length])
        else:
            no_news_categories.append(category)

    if no_news_categories:
        title = f"【{today} 業企部 今日無相關新聞分類整理】"
        content = "\n".join(f"📂【{cat}】無相關新聞" for cat in no_news_categories)
        broadcast_message(f"{title}\n\n{content}")

    # ➕ 加發重點摘要訊息（分類排序 + 描述摘要）
    summary_order = ["新光金控", "台新金控", "保險", "金控"]
    summary_message = f"📌 {today} 重點新聞摘要（依類別排序）\n"
    remaining_chars = 4000 - len(summary_message)

    for cat in summary_order:
        messages = news_by_category.get(cat, [])
        if not messages:
            continue

        added_header = False
        for msg in messages:
            msg_length = len(msg) + 1
            if remaining_chars >= msg_length:
                if not added_header:
                    header = f"\n📂【{cat}】\n"
                    if remaining_chars < len(header):
                        break
                    summary_message += header
                    remaining_chars -= len(header)
                    added_header = True

                summary_message += msg + "\n"
                remaining_chars -= msg_length
            else:
                break

    broadcast_message(summary_message.strip())

if __name__ == "__main__":
    news = fetch_news()
    if news:
        send_message_by_category(news)
    else:
        print("⚠️ 沒有符合條件的新聞，不發送。")



