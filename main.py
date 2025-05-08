import requests
import xml.etree.ElementTree as ET
import logging
import datetime
from urllib.parse import quote
import json
import os

# 設定 log 等級
logging.basicConfig(level=logging.INFO)

# LINE Notify 權杖 (替換成你的 Token)
LINE_ACCESS_TOKEN = '你的 LINE Notify 權杖'
LINE_NOTIFY_API_URL = 'https://notify-api.line.me/api/notify'

# 設定需要抓取的 RSS 來源
RSS_SOURCES = [
    "https://news.google.com/rss/search?q=新光金控+OR+新光人壽+OR+台新金控+OR+台新人壽+OR+壽險+OR+金控+OR+人壽&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    "https://news.google.com/rss/search?q=新光金控+OR+新光人壽&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    "https://news.google.com/rss/search?q=台新金控+OR+台新人壽&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    "https://news.google.com/rss/search?q=壽險+OR+保險+OR+人壽&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    "https://news.google.com/rss/search?q=金控+OR+金融控股&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
]

# 定義分類的關鍵字
CATEGORY_KEYWORDS = {
    '新光金控': ['新光金控', '新光人壽'],
    '台新金控': ['台新金控', '台新人壽'],
    '保險': ['壽險', '保險', '人壽'],
    '金控': ['金控', '金融控股'],
}

# 用來儲存分類結果
classified_news = {
    '新光金控': 0,
    '台新金控': 0,
    '保險': 0,
    '金控': 0,
    '其他': 0
}

# 發送 LINE 訊息
def send_line_notify(message):
    headers = {
        'Authorization': 'Bearer ' + LINE_ACCESS_TOKEN
    }
    payload = {'message': message}
    try:
        response = requests.post(LINE_NOTIFY_API_URL, headers=headers, data=payload)
        if response.status_code == 200:
            logging.info("成功發送 LINE 訊息")
        else:
            logging.error(f"發送 LINE 訊息失敗，狀態碼：{response.status_code}")
    except Exception as e:
        logging.error(f"發送 LINE 訊息發生錯誤: {e}")

# 擷取 RSS 並分類
def fetch_and_classify_news():
    all_news = []
    for url in RSS_SOURCES:
        try:
            logging.info(f"從 {url} 擷取資料中...")
            response = requests.get(url)
            if response.status_code == 200:
                logging.info(f"成功從 {url} 擷取新聞")
                root = ET.fromstring(response.content)
                # 解析每一條新聞
                for item in root.findall('.//item'):
                    title = item.find('title').text
                    description = item.find('description').text
                    link = item.find('link').text
                    published_date = item.find('pubDate').text
                    # 組合標題與描述進行分類
                    news_text = (title or "") + " " + (description or "")
                    category = classify_news(news_text)
                    all_news.append({'title': title, 'link': link, 'category': category, 'published_date': published_date})
                    classified_news[category] += 1
            else:
                logging.error(f"從 {url} 擷取資料失敗，狀態碼：{response.status_code}")
        except Exception as e:
            logging.error(f"擷取 {url} 資料時發生錯誤: {e}")
    
    return all_news

# 根據新聞內容進行分類
def classify_news(text):
    text = text.lower()  # 確保全小寫進行比對
    logging.info(f"分類檢查：{text}")  # 顯示新聞文本，幫助調試

    # 根據關鍵字分類
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw.lower() in text for kw in keywords):
            logging.info(f"分類為：{category}")  # 顯示匹配的分類
            return category
    
    logging.info(f"未能分類，標記為：其他")  # 顯示未匹配的情況
    return "其他"

# 主程式
def main():
    # 擷取並分類新聞
    news = fetch_and_classify_news()
    
    # 顯示分類結果
    logging.info(f"已分類的新聞數量：{classified_news}")
    
    # 發送分類結果到 LINE
    summary_message = "\n".join([f"{category}: {count}篇" for category, count in classified_news.items()])
    send_line_notify(f"今日新聞分類結果：\n{summary_message}")
    
    # 發送具體新聞到 LINE
    for article in news:
        message = f"標題: {article['title']}\n連結: {article['link']}\n分類: {article['category']}\n發布日期: {article['published_date']}\n"
        send_line_notify(message)

if __name__ == '__main__':
    main()



