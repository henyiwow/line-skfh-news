import requests
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
import email.utils
from urllib.parse import quote

ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')
print("✅ Access Token 前 10 碼：", ACCESS_TOKEN[:10] if ACCESS_TOKEN else "未設定")

# 關鍵字可自訂
PREFERRED_SOURCES = ['工商時報', '中國時報', '經濟日報', 'Ettoday新聞雲', '工商時報網', '中時新聞網', '中國時報', '台灣雅虎奇摩', '經濟日報網', '鉅亨網', '聯合新聞網', '鏡周刊網', 'MSN', '自由財經網', '中華日報', '台灣新生報', '旺報', '中國時報', '三立新聞網']

# 分類關鍵字
CATEGORY_KEYWORDS = {
    "新光金控": ["新光金控", "新光人壽", "新壽"],
    "保險": ["保險", "壽險", "保戶"],
    "金控": ["金控", "金融控股", "銀行", "證券"],
    "其他": []
}

# 台灣時區
TW_TZ = timezone(timedelta(hours=8))
today = datetime.now(TW_TZ).date()

# 短網址工具
def shorten_url(long_url):
    try:
        encoded_url = quote(long_url, safe='')
        api_url = f"http://tinyurl.com/api-create.php?url={encoded_url}"
        res = requests.get(api_url, timeout=5)
        if res.status_code == 200:
            return res.text
    except Exception as e:
        print("⚠️ 短網址失敗：", e)
    return long_url

# 分類工具
def classify_news(title):
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in title for kw in keywords):
            return category
    return "其他"

# 新聞抓取邏輯，支持多個 RSS 源
def fetch_news():
    rss_urls = [
        "https://news.google.com/rss/search?q=新光金控+OR+新光人壽+OR+保險+OR+金控+OR+人壽&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",  # Google News
        "https://www.ettoday.net/news/rss",  # ETtoday
        "https://www.chinatimes.com/rss",  # 中時新聞
        "https://www.ltn.com.tw/rss",  # 自由時報
        "https://www.setn.com/RSS.aspx",  # 三立新聞
        "https://www.cna.com.tw/rss",  # 中央社
        "https://www.udn.com/rssfeed/news/2",  # 經濟日報
    ]
    
    classified_news = {cat: [] for cat in CATEGORY_KEYWORDS}

    # 循環抓取每個 RSS
    for rss_url in rss_urls:
        res = requests.get(rss_url)
        print(f"✅ 來源: {rss_url} 回應狀態：{res.status_code}")

        if res.status_code == 200:
            root = ET.fromstring(res.content)
            items = root.findall(".//item")
            print(f"✅ 從 {rss_url} 抓到 {len(items)} 筆新聞")

            for item in items:
                title = item.find('title').text
                link = item.find('link').text
                pubDate_str = item.find('pubDate').text
                source_elem = item.find('source')
                source_name = source_elem.text if source_elem is not None else "未標示"

                # 轉為台灣時間
                pub_datetime = email.utils.parsedate_to_datetime(pubDate_str).astimezone(TW_TZ)
                pub_date = pub_datetime.date()

                print(f"🔍 檢查：{title[:20]}... 來源：{source_name} 發佈日：{pub_date}")

                if pub_date != today:
                    continue

                # 篩選來源或標題
                if not any(keyword in source_name or keyword in title for keyword in PREFERRED_SOURCES):
                    continue

                short_link = shorten_url(link)
                category = classify_news(title)

                formatted = f"📰 {title}\n📌 來源：{source_name}\n🔗 {short_link}"
                classified_news[category].append(formatted)

    # 整理輸出內容
    news_text = ""
    for cat in ["新光金控", "保險", "金控", "其他"]:
        if classified_news[cat]:
            news_text += f"📂【{cat}】\n" + "\n\n".join(classified_news[cat]) + "\n\n"

    print("✅ 今日新聞內容：\n", news_text)
    return news_text.strip()

# LINE 廣播
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

    print("✅ 即將發送的資料：")
    print(data)

    res = requests.post(url, headers=headers, json=data)
    print(f"📤 LINE 回傳狀態碼：{res.status_code}")
    print("📤 LINE 回傳內容：", res.text)

if __name__ == "__main__":
    news = fetch_news()
    if news:
        broadcast_message("【新光金控 今日新聞】\n\n" + news)
    else:
        print("⚠️ 沒有符合條件的新聞，不發送。")

