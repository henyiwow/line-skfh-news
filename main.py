import requests
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
import email.utils

ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')
print("✅ Access Token 前 10 碼：", ACCESS_TOKEN[:10] if ACCESS_TOKEN else "未設定")

# 關鍵字，可自訂其他來源關鍵字
PREFERRED_SOURCES = ['工商時報', '中國時報']

# 台灣時間
TW_TZ = timezone(timedelta(hours=8))
today = datetime.now(TW_TZ).date()

def fetch_news():
    url = "https://news.google.com/rss/search?q=新光金控&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    res = requests.get(url)
    print(f"✅ RSS 回應狀態：{res.status_code}")

    news_list = []

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

            # 轉為台灣時間
            pub_datetime = email.utils.parsedate_to_datetime(pubDate_str).astimezone(TW_TZ)
            pub_date = pub_datetime.date()

            # Debug
            print(f"🔍 檢查：{title[:20]}... 來源：{source_name} 發佈日：{pub_date}")

            if pub_date != today:
                continue

            # 方法三：來源或標題含關鍵字
            if not any(keyword in source_name or keyword in title for keyword in PREFERRED_SOURCES):
                continue

            news_list.append(f"📰 {title}\n📌 來源：{source_name}\n🔗 {link}")

    news_text = "\n\n".join(news_list)
    print("✅ 今日新聞內容：\n", news_text)
    return news_text

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
