import requests
import os
import xml.etree.ElementTree as ET

ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')
print("✅ Access Token 前 10 碼：", ACCESS_TOKEN[:10] if ACCESS_TOKEN else "未設定")

# 可自訂來源清單
PREFERRED_SOURCES = ['工商時報', '中國時報']

def fetch_news():
    url = "https://news.google.com/rss/search?q=新光金控&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    res = requests.get(url)
    print(f"✅ RSS 回應狀態：{res.status_code}")

    news_list = []
    if res.status_code == 200:
        root = ET.fromstring(res.content)
        items = root.findall(".//item")

        print(f"✅ 抓到 {len(items)} 筆新聞")
        count = 0

        for item in items:
            title = item.find('title').text
            link = item.find('link').text
            source = item.find('source')
            source_name = source.text if source is not None else "未知來源"

            # 若有指定來源清單，優先挑選
            if PREFERRED_SOURCES:
                if not any(src in source_name for src in PREFERRED_SOURCES):
                    continue

            news_list.append(f"📰 {title}\n📌 來源：{source_name}\n🔗 {link}")
            count += 1
            if count >= 10:  # 最多顯示 10 則，可自調
                break

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
        broadcast_message("【新光金控 最新新聞】\n\n" + news)
    else:
        print("⚠️ 抓不到新聞，不發送。")
