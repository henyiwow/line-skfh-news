import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
import email.utils
from urllib.parse import quote
import requests
from bs4 import BeautifulSoup

ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')
print("✅ Access Token 前 10 碼：", ACCESS_TOKEN[:10] if ACCESS_TOKEN else "未設定")

PREFERRED_SOURCES = ['工商時報', '中國時報', '經濟日報', 'Ettoday新聞雲', '工商時報網',
                     '中時新聞網', '台灣雅虎奇摩', '經濟日報網', '鉅亨網', '聯合新聞網',
                     '鏡周刊網', '自由財經', '中華日報', '台灣新生報', '旺報', '三立新聞網',
                     '天下雜誌', '奇摩新聞', '《現代保險》雜誌', 'MoneyDJ', '遠見雜誌',
                     '自由時報', 'Ettoday財經雲', '鏡週刊Mirror Media', '匯流新聞網',
                     'Newtalk新聞', '奇摩股市', 'news.cnyes.com', '中央社', '民視新聞網',
                     '風傳媒', 'CMoney', '大紀元']

CATEGORY_KEYWORDS = {
    "新光金控": ["新光金", "新光人壽", "新壽", "吳東進"],
    "台新金控": ["台新金", "台新人壽", "台新壽", "吳東亮"],
    "金控": ["金控", "金融控股", "中信金", "玉山金", "永豐金", "國泰金", "富邦金", "台灣金"],
    "保險": ["保險", "壽險", "健康險", "意外險", "人壽"],
    "其他": []
}

EXCLUDED_KEYWORDS = ['保險套', '避孕套', '保險套使用', '太陽人壽', '大西部人壽', '美國海岸保險']
EXCLUDED_SOURCES = ['香港經濟日報']
TW_TZ = timezone(timedelta(hours=8))
now = datetime.now(TW_TZ)

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

def fetch_article_content(link):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(link, headers=headers, timeout=5)
        if res.status_code != 200:
            return ""
        soup = BeautifulSoup(res.text, 'html.parser')
        paragraphs = soup.find_all('p')
        return " ".join(p.get_text(strip=True) for p in paragraphs if p.get_text())
    except Exception as e:
        print(f"⚠️ 抓取內文失敗：{e}（{link}）")
        return ""

def classify_news(title, content):
    full_text = (title + " " + content).lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw.lower() in full_text for kw in keywords):
            return category
    return "其他"

def is_taiwan_news(source_name, link):
    if source_name in EXCLUDED_SOURCES:
        return False
    taiwan_sources = ['工商時報', '中國時報', '經濟日報', '三立新聞網', '自由時報',
                      '聯合新聞網', '鏡週刊', '台灣雅虎', '鉅亨網', '中時新聞網', 'Ettoday新聞雲',
                      '天下雜誌', '奇摩新聞', '《現代保險》雜誌', '遠見雜誌']
    if any(tw_src in source_name for tw_src in taiwan_sources):
        return True
    if '.tw' in link:
        return True
    return False

def fetch_news():
    rss_urls = [
        "https://news.google.com/rss/search?q=新光金控+OR+新光人壽+OR+台新金控+OR+台新人壽+OR+壽險+OR+金控+OR+人壽+OR+新壽+OR+台新壽+OR+吳東進+OR+吳東亮&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    ]

    classified_news = {cat: [] for cat in CATEGORY_KEYWORDS}
    processed_links = set()

    for rss_url in rss_urls:
        res = requests.get(rss_url)
        print(f"✅ 抓取 RSS：{rss_url} 狀態碼：{res.status_code}")
        if res.status_code != 200:
            continue

        root = ET.fromstring(res.content)
        items = root.findall(".//item")
        print(f"✅ 共 {len(items)} 筆新聞")

        for item in items:
            title_elem = item.find('title')
            link_elem = item.find('link')
            pubDate_elem = item.find('pubDate')
            source_elem = item.find('source')

            if not (title_elem and link_elem and pubDate_elem):
                continue

            title = title_elem.text.strip()
            link = link_elem.text.strip()
            pubDate = email.utils.parsedate_to_datetime(pubDate_elem.text.strip()).astimezone(TW_TZ)
            source_name = source_elem.text.strip() if source_elem is not None else "未標示"

            if (now - pubDate).total_seconds() > 86400:
                continue
            if any(bad_kw in title for bad_kw in EXCLUDED_KEYWORDS):
                continue
            if not is_taiwan_news(source_name, link):
                continue
            if link in processed_links:
                continue

            processed_links.add(link)
            content = fetch_article_content(link)
            category = classify_news(title, content)
            short_link = shorten_url(link)
            message = f"📰 {title}\n📌 來源：{source_name}\n🔗 {short_link}"
            classified_news[category].append(message)

    return classified_news

def send_message_by_category(news_by_category):
    max_length = 4000
    no_news_categories = []

    for category, messages in news_by_category.items():
        if messages:
            title = f"【{now.date()} 業企部 今日【{category}】重點新聞整理】 共{len(messages)}則新聞"
            full = f"{title}\n\n" + "\n".join(messages)
            for i in range(0, len(full), max_length):
                broadcast_message(full[i:i + max_length])
        else:
            no_news_categories.append(category)

    if no_news_categories:
        title = f"【{now.date()} 業企部 今日無相關新聞分類整理】"
        content = "\n".join(f"📂【{cat}】無相關新聞" for cat in no_news_categories)
        broadcast_message(f"{title}\n\n{content}")

def broadcast_message(message):
    url = 'https://api.line.me/v2/bot/message/broadcast'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {ACCESS_TOKEN}'
    }
    data = {"messages": [{"type": "text", "text": message}]}
    print(f"📤 發送訊息：{len(message)} 字元")
    res = requests.post(url, headers=headers, json=data)
    print(f"📤 LINE 狀態碼：{res.status_code} 回應：{res.text}")

if __name__ == "__main__":
    news = fetch_news()
    if news:
        send_message_by_category(news)
    else:
        print("⚠️ 沒有符合條件的新聞，不發送。")
