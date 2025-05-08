import requests
import xml.etree.ElementTree as ET
import logging
import re

# 設定 LINE Notify 的 Access Token
LINE_ACCESS_TOKEN = '你的LINE_NOTIFY_ACCESS_TOKEN'
LINE_NOTIFY_API_URL = 'https://notify-api.line.me/api/notify'

# 設定 logging
logging.basicConfig(level=logging.INFO)

# 設定 Google News RSS 的 URL
rss_urls = [
    "https://news.google.com/rss/search?q=新光金控+OR+新光人壽+OR+台新金控+OR+台新人壽+OR+壽險+OR+金控+OR+人壽&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    "https://news.google.com/rss/search?q=新光金控+OR+新光人壽&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    "https://news.google.com/rss/search?q=台新金控+OR+台新人壽&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    "https://news.google.com/rss/search?q=壽險+OR+保險+OR+人壽&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    "https://news.google.com/rss/search?q=金控+OR+金融控股&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
]

# 類別與關鍵字對應
CATEGORY_KEYWORDS = {
    '新光金控': ['新光金控'],
    '台新金控': ['台新金控'],
    '保險': ['壽險', '保險', '人壽'],
    '金控': ['金控', '金融控股']
}

# 發送 LINE 訊息
def send_line_notify(message):
    headers = {
        'Authorization': 'Bearer ' + LINE_ACCESS_TOKEN
    }
    payload = {'message': message.encode('utf-8')}  # 確保 message 是 utf-8 編碼
    try:
        response = requests.post(LINE_NOTIFY_API_URL, headers=headers, data=payload)
        if response.status_code == 200:
            logging.info("成功發送 LINE 訊息")
        else:
            logging.error(f"發送 LINE 訊息失敗，狀態碼：{response.status_code}")
    except Exception as e:
        logging.error(f"發送 LINE 訊息發生錯誤: {e}")

# 擷取 Google News RSS 資料
def fetch_rss_data():
    all_news = []
    for url in rss_urls:
        logging.info(f"從 {url} 擷取新聞...")
        try:
            response = requests.get(url)
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                items = root.findall(".//item")
                for item in items:
                    title = item.find("title").text
                    link = item.find("link").text
                    description = item.find("description").text
                    pub_date = item.find("pubDate").text
                    all_news.append({'title': title, 'link': link, 'description': description, 'pubDate': pub_date})
                logging.info(f"成功擷取 {len(items)} 筆新聞")
            else:
                logging.error(f"無法擷取資料，HTTP 狀態碼: {response.status_code}")
        except Exception as e:
            logging.error(f"擷取資料時發生錯誤: {e}")
    return all_news

# 計算並分類新聞
def categorize_news(all_news):
    categorized_news = {key: [] for key in CATEGORY_KEYWORDS}
    categorized_news['其他'] = []

    for news in all_news:
        categorized = False
        for category, keywords in CATEGORY_KEYWORDS.items():
            if any(re.search(keyword, news['title'], re.IGNORECASE) for keyword in keywords):
                categorized_news[category].append(news)
                categorized = True
                break
        if not categorized:
            categorized_news['其他'].append(news)
    
    return categorized_news

# 構建要發送的訊息
def build_message(categorized_news):
    message = "每日金融與壽險新聞更新：\n\n"
    for category, news_list in categorized_news.items():
        message += f"--- {category} ---\n"
        for news in news_list:
            message += f"【{news['title']}】\n{news['link']}\n\n"
    return message

# 主程式
def main():
    all_news = fetch_rss_data()
    if not all_news:
        logging.info("沒有抓到新聞")
        return

    categorized_news = categorize_news(all_news)
    logging.info(f"已分類的新聞數量：{ {key: len(val) for key, val in categorized_news.items()} }")
    
    message = build_message(categorized_news)
    send_line_notify(message)

if __name__ == "__main__":
    main()



