import requests
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
import email.utils
from urllib.parse import quote

# 設定 ACCESS_TOKEN
ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')
print("✅ Access Token 前 10 碼：", ACCESS_TOKEN[:10] if ACCESS_TOKEN else "未設定")

# 預設來源
PREFERRED_SOURCES = ['工商時報', '中國時報', '經濟日報', 'Ettoday新聞雲', '工商時報網',
                     '中時新聞網', '台灣雅虎奇摩', '經濟日報網', '鉅亨網', '聯合新聞網',
                     '鏡周刊網', '自由財經', '中華日報', '台灣新生報', '旺報', '三立新聞網',
                     '天下雜誌', '奇摩新聞', '《現代保險》雜誌', 'MoneyDJ', '遠見雜誌',
                     '自由時報', 'Ettoday財經雲', '鏡週刊Mirror Media', '匯流新聞網',
                     'Newtalk新聞', '奇摩股市', 'news.cnyes.com', '中央社', '民視新聞網',
                     '風傳媒', 'CMoney', '大紀元']

# 分類關鍵字
CATEGORY_KEYWORDS = {
    "新光金控": ["新光金", "新光人壽", "新壽", "吳東進"],
    "台新金控": ["台新金", "台新人壽", "台新壽", "吳東亮"],
    "保險": ["保險", "壽險", "健康險", "意外險", "人壽"],
    "金控": ["金控", "金融控股", "中信金", "玉山金", "永豐金", "國泰金", "富邦金"],
    "其他": []
}

# 排除關鍵字
EXCLUDED_KEYWORDS = ['保險套', '避孕套', '保險套使用']

# 台灣時區設定
TW_TZ = timezone(timedelta(hours=8))
today = datetime.now(TW_TZ).date()

# 生成短網址
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

# 根據標題分類新聞
def classify_news(title):
    title = title.lower()  # 將標題轉為小寫
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw.lower() in title for kw in keywords):  # 關鍵字也轉為小寫
            return category
    return "其他"

# 擷取新聞
def fetch_news():
    rss_urls = [
        "https://news.google.com/rss/search?q=新光金控+OR+新光人壽+OR+台新金控+OR+台新人壽+OR+壽險+OR+金控+OR+人壽&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
        "https://news.google.com/rss/search?q=新光金控+OR+新光人壽&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
        "https://news.google.com/rss/search?q=台新金控+OR+台新人壽&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
        "https://news.google.com/rss/search?q=壽險+OR+保險+OR+人壽&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
        "https://news.google.com/rss/search?q=金控+OR+金融控股&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    ]

    classified_news = {cat: [] for cat in CATEGORY_KEYWORDS}
    seen_links = set()

    for rss_url in rss_urls:
        res = requests.get(rss_url)
        print(f"✅ 來源: {rss_url} 回應狀態：{res.status_code}")

        if res.status_code == 200:
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

                if link in seen_links:
                    continue
                seen_links.add(link)

                source_elem = item.find('source')
                source_name = source_elem.text.strip() if source_elem is not None else "未標示"

                pub_datetime = email.utils.parsedate_to_datetime(pubDate_str).astimezone(TW_TZ)
                pub_date = pub_datetime.date()
                if pub_date != today:
                    continue

                if any(bad_kw in title for bad_kw in EXCLUDED_KEYWORDS):
                    continue

                if not any(src in source_name or src in title for src in PREFERRED_SOURCES):
                    continue

                short_link = shorten_url(link)
                category = classify_news(title)
                formatted = f"📰 {title}\n📌 來源：{source_name}\n🔗 {short_link}"
                classified_news[category].append(formatted)

    news_text = f"📅 今日日期：{today.strftime('%Y-%m-%d')}\n\n"
    for cat in ["新光金控", "台新金控", "保險", "金控", "其他"]:
        if classified_news[cat]:
            news_text += f"📂【{cat}】({len(classified_news[cat])}則)\n"
            for idx, item in enumerate(classified_news[cat], 1):
                news_text += f"{idx}. {item}\n\n"

    news_text += "📎 本新聞整理自 Google News RSS，連結已轉為短網址。"
    print("✅ 今日新聞內容：\n", news_text)
    return classified_news

# 根據類別分開發送訊息
def send_message_by_category(news_by_category):
    max_length = 4000

    for category, messages in news_by_category.items():
        if messages:  # 如果該類別有消息
            category_title = f"📂【{category}】 今日新聞整理\n"  # 顯示類別標題
            category_message = category_title + "\n"
            category_message += "\n".join(messages)

            # 如果訊息長度超過 4000 字元，則分割成多條訊息
            for i in range(0, len(category_message), max_length):
                chunk = category_message[i:i + max_length]
                broadcast_message(chunk)

# 發送單條訊息到 LINE
def broadcast_message(message):
    url = 'https://api.line.me/v2/bot/message/broadcast'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {ACCESS_TOKEN}'
    }

    final_message = "【業企部 今日重點新聞整理】\n\n" + message
    data = {
        "messages": [{
            "type": "text",
            "text": final_message
        }]
    }

    print(f"📤 發送訊息總長：{len(final_message)} 字元")
    res = requests.post(url, headers=headers, json=data)
    print(f"📤 LINE 回傳狀態碼：{res.status_code}")
    print("📤 LINE 回傳內容：", res.text)

# 主程序
if __name__ == "__main__":
    news = fetch_news()
    if news:
        send_message_by_category(news)
    else:
        print("⚠️ 沒有符合條件的新聞，不發送。")




