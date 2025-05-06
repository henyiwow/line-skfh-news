import requests
from bs4 import BeautifulSoup
import os

# 讀取 Access Token
ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')
print("✅ Access Token 前 10 碼：", ACCESS_TOKEN[:10] if ACCESS_TOKEN else "未設定")

def fetch_news():
    url = "https://news.google.com/search?q=新光金控&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(url, headers=headers)
    print(f"✅ 抓取新聞 HTTP 狀態碼：{res.status_code}")

    soup = BeautifulSoup(res.text, "html.parser")
    articles = soup.select("article h3 a")
    print(f"✅ 抓到 {len(articles)} 則新聞")

    news_list = []

    for article in articles[:5]:  # 最多取 5 則
        title = article.text
        href = article['href']
        link = 'https://news.google.com' + href[1:] if href.startswith('.') else href
        news_list.append(f"{title}\n{link}")

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
