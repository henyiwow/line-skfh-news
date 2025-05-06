import requests
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
import email.utils
from urllib.parse import quote

ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')
print("✅ Access Token 前 10 碼：", ACCESS_TOKEN[:10] if ACCESS_TOKEN else "未設定")

# 關鍵字與排除清單
PREFERRED_SOURCES = [
    '工商時報', '中國時報', '經濟日報', 'Ettoday新聞雲', '工商時報網', 
    '中時新聞網', '台灣雅虎奇摩', '經濟日報網', '鉅亨網', 
    '聯合新聞網', '鏡周刊網',  '自由財經', '中華日報', '台灣新生報', 
    '旺報', '三立新聞網',  '天下雜誌', '奇摩新聞',
    '《現代保險》雜誌', 'MoneyDJ', '遠見雜誌', '自由時報', 'Ettoday財經雲',
    '鏡週刊Mirror Media', '匯流新聞網', 'Newtalk新聞', '奇摩股市', 'news.cnyes.com',
    '中央社', '民視新聞網', '風傳媒', 'CMoney', '大紀元'
]

CATEGORY_KEYWORDS = {
    "新光金控": ["新光金", "新光人壽", "新壽"],
    "保險": ["保險", "壽險", "健康險", "意外險"],
    "金控": ["金控", "金融控股"],
    "其他": []
}

EXCLUDED_TERMS = ["保險套", "保險套販售", "保險套價格", "司法保險費"]

# 台灣時間
TW_TZ = timezone(timedelta(hours=8))
today = datetime.now(TW_TZ).date()

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

def classify_news(title):
    if any(ex in title for ex in EXCLUDED_TERMS):
        return "其他"
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in title for kw in keywords):
            return category
    return "其他"

def fetch_news():
    rss_urls = [
        "https://news.google.com/rss/search?q=新光金控+OR+新光人壽+OR+保險+OR+金控+OR+人壽&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    ]

    classified_news = {cat: [] for cat in CATEGORY_KEYWORDS}
    date_str = today.strftime("%Y/%m/%d")

    for rss_url in rss_urls:
        res = requests.get(rss_url)
        print(f"✅ 來源: {rss_url} 回應狀態：{res.status_code}")

        if res.status_code == 200:
            root = ET.fromstring(res.content)
            items = root.findall(".//item")
            print(f"✅ 抓到 {len(items)} 筆新聞")

            for item in items:
                title = item.find('title').text
                link = item.find('link').text
                pubDate_str = item.find('pubDate').text
                source_elem = item.find('source')
                source_name = source_elem.text if source_elem is not None else "未標示"

                pub_datetime = email.utils.parsedate_to_datetime(pubDate_str).astimezone(TW_TZ)
                pub_date = pub_datetime.date()

                if pub_date != today:
                    continue

                if not any(keyword in source_name or keyword in title for keyword in PREFERRED_SOURCES):
                    continue

                category = classify_news(title)
                if category == "其他":
                    continue

                short_link = shorten_url(link)
                formatted = {
                    "title": title,
                    "source": source_name,
                    "link": short_link
                }
                classified_news[category].append(formatted)

    news_text = f"【業企部 今日重點新聞整理 - {date_str}】\n\n"
    for cat in ["新光金控", "保險", "金控"]:
        if classified_news[cat]:
            news_text += f"📂【{cat}】\n"
            for idx, news in enumerate(classified_news[cat], start=1):
                news_text += f"{idx}. 📰 {news['title']}\n📌 來源：{news['source']}\n🔗 {news['link']}\n\n"
    news_text += "📎 資料來源：Google News RSS"

    print("✅ 今日新聞內容：\n", news_text)
    return news_text.strip()

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
        broadcast_message(news)
    else:
        print("⚠️ 沒有符合條件的新聞，不發送。")
