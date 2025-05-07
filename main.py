import requests
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
import email.utils
from urllib.parse import quote, urlparse
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')
print("✅ Access Token 前 10 碼：", ACCESS_TOKEN[:10] if ACCESS_TOKEN else "未設定")

PREFERRED_SOURCES = ['工商時報', '中國時報', '經濟日報', 'Ettoday新聞雲', '工商時報網',
                     '中時新聞網', '台灣雅虎奇摩', '經濟日報網', '鉅亨網', '聯合新聞網',
                     '鏡周刊網', '自由財經', '中華日報', '台灣新生報', '旺報', '三立新聞網',
                     '天下雜誌', '奇摩新聞', '《現代保險》雜誌', 'MoneyDJ', '遠見雜誌',
                     '自由時報', 'Ettoday財經雲', '鏡週刊Mirror Media', '匯流新聞網',
                     'Newtalk新聞', '奇摩股市', 'news.cnyes.com', '中央社', '民視新聞網',
                     '風傳媒', 'CMoney', '大紀元']

CATEGORY_DESCRIPTIONS = {
    "新光金控": "新光金 新光人壽 新光金控",
    "台新金控": "台新金 台新人壽 台新金控",
    "保險": "保險 壽險 健康險 意外險 保險業",
    "金控": "金融控股 金融集團 金控 銀行",
    "其他": ""
}

EXCLUDED_KEYWORDS = ['保險套', '避孕套', '保險套使用']

TW_TZ = timezone(timedelta(hours=8))
today = datetime.now(TW_TZ).date()

vectorizer = TfidfVectorizer()
category_texts = list(CATEGORY_DESCRIPTIONS.values())
category_vectors = vectorizer.fit_transform(category_texts)

def classify_news(title):
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in title for kw in keywords):
            print(f"News title: {title} matched category: {category}")  # 這行可以幫助追蹤
            return category
    return "其他"

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


def extract_domain(url):
    try:
        parsed = urlparse(url)
        return parsed.netloc.replace('www.', '')
    except:
        return ""


def is_preferred_source(source_name, link, title):
    domain = extract_domain(link)
    return any(src in source_name or src in title or src in domain for src in PREFERRED_SOURCES)


def normalize_url(url):
    parsed = urlparse(url)
    return f"{parsed.netloc}{parsed.path}"


def fetch_news():
    keywords_list = [
        "新光金控 OR 新光人壽",
        "台新金控 OR 台新人壽",
        "壽險 OR 健康險 OR 金控"
    ]

    rss_urls = [
        f"https://news.google.com/rss/search?q={quote(k)}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        for k in keywords_list
    ]

    classified_news = {cat: [] for cat in CATEGORY_DESCRIPTIONS}
    seen_links = set()

    for rss_url in rss_urls:
        try:
            res = requests.get(rss_url)
            print(f"✅ 來源: {rss_url} 回應狀態：{res.status_code}")
            if res.status_code != 200:
                continue
            root = ET.fromstring(res.content)
            items = root.findall(".//item")
            print(f"✅ 抓到 {len(items)} 筆新聞")
        except Exception as e:
            print(f"⚠️ 解析 RSS 錯誤：{e}")
            continue

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

            norm_link = normalize_url(link)
            if norm_link in seen_links:
                continue
            seen_links.add(norm_link)

            source_elem = item.find('source')
            source_name = source_elem.text.strip() if source_elem is not None else "未標示"

            pub_datetime = email.utils.parsedate_to_datetime(pubDate_str).astimezone(TW_TZ)
            pub_date = pub_datetime.date()
            if pub_date != today:
                continue

            if any(bad_kw in title for bad_kw in EXCLUDED_KEYWORDS):
                continue

            if not is_preferred_source(source_name, link, title):
                continue

            short_link = shorten_url(link)
            category = classify_news(title)
            formatted = f"📰 {title}\n📌 來源：{source_name}\n🔗 {short_link}"
            classified_news[category].append(formatted)

    news_text = f"📅 今日日期：{today.strftime('%Y-%m-%d')}\n\n"
    for cat in CATEGORY_DESCRIPTIONS:
        if classified_news[cat]:
            news_text += f"📂【{cat}】({len(classified_news[cat])}則)\n"
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


if __name__ == "__main__":
    news = fetch_news()
    if news:
        broadcast_message(news)
    else:
        print("⚠️ 沒有符合條件的新聞，不發送。")
