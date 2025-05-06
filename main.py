import requests
from bs4 import BeautifulSoup
import os

ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')

def fetch_news():
    url = "https://news.google.com/search?q=新光金控&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(url, headers=headers)
    soup = BeautifulSoup(res.text, "html.parser")

    articles = soup.select("article h3 a")
    news_list = []

    for article in articles[:5]:
        title = article.text
        href = article['href']
        link = 'https://news.google.com' + href[1:] if href.startswith('.') else href
        news_list.append(f"{title}\n{link}")

    return "\n\n".join(news_list)

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
    res = requests.post(url, headers=headers, json=data)
    print(f"Status: {res.status_code}")
    print(res.text)

if __name__ == "__main__":
    news = fetch_news()
    if news:
        broadcast_message("【新光金控 最新新聞】\n\n" + news)
