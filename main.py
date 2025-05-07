from collections import defaultdict, Counter

def fetch_news():
    rss_urls = [ ... ]  # 如原本
    classified_news = {cat: [] for cat in CATEGORY_KEYWORDS}
    seen_links = set()
    title_counter = Counter()
    title_to_data = {}  # 儲存每則新聞的內容與分類

    for rss_url in rss_urls:
        res = requests.get(rss_url)
        if res.status_code != 200:
            continue

        root = ET.fromstring(res.content)
        items = root.findall(".//item")

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
            pub_datetime = email.utils.parsedate_to_datetime(pubDate_str).astimezone(TW_TZ)
            if pub_datetime.date() != today:
                continue

            source_elem = item.find('source')
            source_name = source_elem.text.strip() if source_elem is not None else "未標示"

            if any(bad_kw in title for bad_kw in EXCLUDED_KEYWORDS):
                continue

            if not any(src in source_name or src in title for src in PREFERRED_SOURCES):
                continue

            short_link = shorten_url(link)
            category = classify_news(title)
            formatted = f"📰 {title}\n📌 來源：{source_name}\n🔗 {short_link}"

            title_counter[title] += 1
            title_to_data[title] = (category, formatted)

    # 加入分類新聞，並依出現次數排序
    for title, count in title_counter.items():
        category, formatted = title_to_data[title]
        classified_news[category].append((count, formatted))

    # 依出現次數排序
    for category in classified_news:
        items = sorted(classified_news[category], key=lambda x: -x[0])
        classified_news[category] = [item for _, item in items[:10]]  # 最多取 10 則

    return classified_news

