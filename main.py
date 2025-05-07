import requests
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
import email.utils
from urllib.parse import quote

ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')
print("✅ Access Token 前 10 碼：", ACCESS_TOKEN[:10] if ACCESS_TOKEN else "未設定")

PREFERRED_SOURCES = [
    '工商時報', '中國時報', '經濟日報', 'Ettoday新聞雲', '工商時報網',
    '中時新聞網', '台灣雅虎奇摩', '經濟日報網', '鉅亨網', '聯合新聞網',
    '鏡周刊網', '自由財經', '中華日報', '台灣新生報', '旺報', '三立新聞網',
    '天下雜誌', '奇摩新聞', '《現代保險》雜誌', 'MoneyDJ', '遠見雜誌',
    '自由時報', 'Ettoday財經雲', '鏡週刊Mirror Media', '匯流新聞網',
    'Newtalk新聞', '奇摩股市', 'news.cnyes.com', '中央社', '民視新聞網',
    '風傳媒', 'CMoney', '大紀元'
]

CATEGORY_KEYWORDS = {
    "新光金控": ["新光金", "新光人壽", "新壽"],
    "台新金控": ["台新金", "台新人壽", "台新壽"],
    "保險": ["保險", "壽險", "健康險", "意外險", "人壽"],
    "金控": ["金控", "金融控股", "中信金", "玉山金", "永豐金", "國泰金", "富邦金"],
    "其他": []
}

EXCLUDED_KEYWORDS = ['保險套', '避孕套', '保險套使用']

TW_TZ = timezone(timedelta(hours=8))
today = datetime.now(TW_TZ).date()


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
    title = title.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw.lower() in title for kw in keywords):
            return category
    return "其他"


def fetch_news():
    rss_urls = [
        "https://news.google.com/rss/search?q=新光金控+OR+新光人壽+OR+台新金控+OR+台新人壽+OR+壽險+OR+金控+OR+人壽&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
        "https://news.google.com/rss/search?q=新光金控+OR+新光人壽&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
        "https://news.google.com/rss/search?q=台新金控+OR+台新人壽&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
        "https://news.google.com/rss/search?q=壽險+OR+保險+OR+人壽&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
        "https://news.google.com/rss/search?q=金控+OR+金融控股&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
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
                if not all([title_elem, link_elem, pubDate_elem]):
                    continue

                title = title_elem.text.strip()
                link = link_elem.text.strip()
                pubDate_str = pubDate_elem.text.strip()

                if not title or title.startswith("Google ニュース") or link in seen_links:
                    continue

                seen_links.add(link)

                source_elem = item.find('source')
                source_name = source_elem.text.strip() if source_elem is not None else "未標示"

                pub_datetime = email.utils.parsedate_to_datetime(pubDate_str).astimezone(TW_TZ)
                if pub_datetime.date() != today:
                    continue

                if any(bad_kw in title for bad_kw in EXCLUDED_KEYWORDS):
                    continue

                if not any(src in source_name or src in title for src in PREFERRED_SOURCES):
                    continue

                short_link = shorten_url(link)
                category = classify_news(title)
                formatted = f"📰 {title}\n📌 來源：{source_name}\n🔗 {short_link}"
                classified_news[category].append(formatted)

    return classified_news


def send_news_by_category(classified_news):
    url = 'https://api.line.me/v2/bot/message/broadcast'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {ACCESS_TOKEN}'
    }

    for cat, items in classified_news.items():
        if not items:
            continue

        message = f"【業企部 今日{cat}新聞整理】\n\n"
        message += f"📅 今日日期：{today.strftime('%Y-%m-%d')}\n\n"
        for idx, item in enumerate(items, 1):
            message += f"{idx}. {item}\n\n"
        message += "📎 本新聞整理自 Google News RSS，連結已轉為短網址。"

        print(f"📤 發送訊息總長：{len(message)} 字元")
        res = requests.post(url, headers=headers, json={"messages": [{"type": "text", "text": message}]})
        print(f"📤 類別 {cat} 發送狀態碼：{res.status_code}")
        print("📤 LINE 回傳內容：", res.text)


if __name__ == "__main__":
    news_by_category = fetch_news()
    send_news_by_category(news_by_category)


