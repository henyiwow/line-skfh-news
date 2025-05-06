import requests
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
import email.utils
from urllib.parse import quote

ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')
print("✅ Access Token 前 10 碼：", ACCESS_TOKEN[:10] if ACCESS_TOKEN else "未設定")

PREFERRED_SOURCES = ['工商時報', '中國時報', '經濟日報', 'Ettoday新聞雲', '工商時報網', 
                     '中時新聞網', '中國時報', '台灣雅虎奇摩', '經濟日報網', '鉅亨網', 
                     '聯合新聞網', '鏡周刊網',  '自由財經', '中華日報', '台灣新生報', 
                     '旺報', '中國時報', '三立新聞網',  '天下雜誌', '奇摩新聞',
                     '《現代保險》雜誌', 'MoneyDJ', '遠見雜誌', '自由時報', 'Ettoday財經雲',
                     '鏡週刊Mirror Media', '匯流新聞網', 'Newtalk新聞' , '奇摩股市', 'news.cnyes.com',
                     '中央社', '民視新聞網', '風傳媒', 'CMoney', '大紀元']

CATEGORY_KEYWORDS = {
    "新光金控": ["新光金", "新光人壽", "新壽"],
    "台新金控": ["台新金", "台新人壽"],
    "保險": ["保險", "壽險", "健康險", "意外險"],
    "金控": ["金控", "金融控股"],
    "其他": []
}

EXCLUDED_KEYWORDS = ['保險套', '避孕套', '保險套使用', '司法保險', '必要保險']

TW_TZ = timezone(timedelta(hours=8))
today = datetime.now(TW_TZ).date()

# 儲存已處理的連結，避免重複
processed_links = set()

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
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in title for kw in keywords):
            return category
    return "其他"


def fetch_news():
    rss_urls = [
        "https://news.google.com/rss/search?q=新光金控+OR+新光人壽+OR+保險+OR+金控+OR+人壽&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    ]

    classified_news = {cat: [] for cat in CATEGORY_KEYWORDS}

    for rss_url in rss_urls:
        try:
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

                    pub_datetime = email.utils.parsedate_to_datetime(pubDate_str).astimezone(TW_TZ)
                    pub_date = pub_datetime.date()

                    print(f"🔍 檢查：{title[:20]}... 來源：{source_name} 發佈日：{pub_date}")

                    if pub_date != today:
                        continue

                    # 排除敏感關鍵字
                    if any(bad_kw in title for bad_kw in EXCLUDED_KEYWORDS):
                        print(f"⛔ 排除：{title[:20]}... 含有排除關鍵字")
                        continue

                    if not any(keyword in source_name or keyword in title for keyword in PREFERRED_SOURCES):
                        continue

                    # 檢查是否已經處理過此連結
                    if link in processed_links:
                        print(f"⛔ 排除：{title[:20]}... 重複連結")
                        continue

                    short_link = shorten_url(link)
                    processed_links.add(link)  # 標記此連結已處理

                    category = classify_news(title)

                    formatted = f"📰 {title}\n📌 來源：{source_name}\n🔗 {short_link}"
                    classified_news[category].append(formatted)

        except Exception as e:
            print(f"⚠️ 無法從 {rss_url} 抓取新聞：{e}")

    news_text = f"📅 今日日期：{today.strftime('%Y-%m-%d')}\n\n"
    for cat in ["新光金控", "台新金控","保險", "金控", "其他"]:
        if classified_news[cat]:
            news_text += f"📂【{cat}】\n"
            for idx, item in enumerate(classified_news[cat], 1):
                news_text += f"{idx}. {item}\n\n"

    news_text += "📎 本新聞整理自 Google News RSS，連結已轉為短網址。"
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
        broadcast_message("【業企部 今日重點新聞整理】\n\n" + news)
    else:
        print("⚠️ 沒有符合條件的新聞，不發送。")

