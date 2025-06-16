import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
import email.utils
from urllib.parse import quote
import requests
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
import re
import hashlib
import json
import sqlite3
from pathlib import Path
import time
import logging

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('news_bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# ✅ 初始化語意模型
try:
    model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
    logger.info("✅ AI 模型載入成功")
except Exception as e:
    logger.error(f"❌ AI 模型載入失敗: {e}")
    model = None

# ✅ 去重參數設定
SIMILARITY_THRESHOLD = 0.82  # 語意相似度門檻
TEXT_SIMILARITY_THRESHOLD = 0.75  # 文字相似度門檻
URL_SIMILARITY_THRESHOLD = 0.8  # URL 相似度門檻

ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')
if ACCESS_TOKEN:
    logger.info(f"✅ Access Token 已設定，前10碼：{ACCESS_TOKEN[:10]}")
else:
    logger.error("❌ ACCESS_TOKEN 環境變數未設定")

CATEGORY_KEYWORDS = {
    "新光金控": ["新光金", "新光人壽", "新壽", "吳東進", "新光金控"],
    "台新金控": ["台新金", "台新人壽", "台新壽", "吳東亮", "台新金控"],
    "金控": ["金控", "金融控股", "中信金", "玉山金", "永豐金", "國泰金", "富邦金", "台灣金", "第一金", "元大金"],
    "保險": ["保險", "壽險", "健康險", "意外險", "人壽", "產險", "車險", "保單"],
    "其他": []
}

EXCLUDED_KEYWORDS = [
    '保險套', '避孕套', '保險套使用', '太陽人壽', '大西部人壽', '美國海岸保險',
    '香港', '大陸', '中國大陸', '美國', '日本', '韓國', '越南', '泰國', '新加坡'
]

TW_TZ = timezone(timedelta(hours=8))
now = datetime.now(TW_TZ)
today = now.date()

# ✅ 初始化資料庫
def init_database():
    """初始化 SQLite 資料庫"""
    try:
        db_path = Path('news_cache.db')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS processed_news (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                normalized_title TEXT NOT NULL,
                link TEXT NOT NULL,
                source TEXT,
                category TEXT,
                pub_date TEXT,
                processed_at TEXT NOT NULL,
                title_hash TEXT NOT NULL,
                url_hash TEXT
            )
        ''')
        
        # 建立索引提高查詢效能
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_title_hash ON processed_news(title_hash)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_url_hash ON processed_news(url_hash)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_processed_at ON processed_news(processed_at)')
        
        # 清理超過7天的記錄
        week_ago = (now - timedelta(days=7)).isoformat()
        cursor.execute('DELETE FROM processed_news WHERE processed_at < ?', (week_ago,))
        deleted_count = cursor.rowcount
        
        conn.commit()
        logger.info(f"✅ 資料庫初始化完成，清理了 {deleted_count} 筆舊記錄")
        return conn
    except Exception as e:
        logger.error(f"❌ 資料庫初始化失敗: {e}")
        return None

# ✅ 改進的標題正規化
def normalize_title(title):
    """更嚴格的標題正規化"""
    if not title:
        return ""
    
    # 移除常見的新聞前綴後綴
    title = re.sub(r'^(快訊|獨家|最新|即時|更新|圖表新聞|專題|深度|分析|重磅|突發|緊急)', '', title)
    title = re.sub(r'[｜|‧\-－–—~～].*$', '', title)  # 移除媒體後綴
    title = re.sub(r'<[^>]+>', '', title)            # 移除 HTML 標籤
    title = re.sub(r'[（()）\[\]【】「」『』""''《》]', '', title)  # 移除各種括號
    title = re.sub(r'[^\w\u4e00-\u9fff\s]', ' ', title)  # 移除非文字符號，保留空白
    title = re.sub(r'\s+', ' ', title)               # 合併多餘空白
    title = re.sub(r'(股份有限公司|有限公司|股份|公司|集團)', '', title)  # 移除公司後綴
    title = re.sub(r'(新台幣|元|億|萬|千)', '', title)  # 移除金額單位
    return title.strip().lower()

def calculate_text_similarity(text1, text2):
    """計算文字相似度 (Jaccard similarity)"""
    if not text1 or not text2:
        return 0
    
    # 分詞並去除短詞
    words1 = set([w for w in text1.split() if len(w) >= 2])
    words2 = set([w for w in text2.split() if len(w) >= 2])
    
    if not words1 or not words2:
        return 0
    
    intersection = words1.intersection(words2)
    union = words1.union(words2)
    return len(intersection) / len(union) if union else 0

def calculate_url_similarity(url1, url2):
    """計算 URL 相似度"""
    if not url1 or not url2:
        return 0
    
    # 移除協議和參數
    def clean_url(url):
        url = re.sub(r'^https?://', '', url)
        url = re.sub(r'\?.*$', '', url)
        url = re.sub(r'#.*$', '', url)
        return url.lower()
    
    clean1 = clean_url(url1)
    clean2 = clean_url(url2)
    
    # 計算編輯距離相似度
    from difflib import SequenceMatcher
    return SequenceMatcher(None, clean1, clean2).ratio()

def generate_hash(text):
    """生成文字雜湊"""
    if not text:
        return ""
    return hashlib.md5(text.encode('utf-8')).hexdigest()[:16]

def is_duplicate_news(title, link, conn):
    """改進的重複新聞檢測"""
    if not conn:
        return False
    
    try:
        normalized = normalize_title(title)
        title_hash = generate_hash(normalized)
        url_hash = generate_hash(link)
        
        cursor = conn.cursor()
        
        # 1. 檢查完全相同的標題雜湊
        cursor.execute('SELECT title FROM processed_news WHERE title_hash = ?', (title_hash,))
        if cursor.fetchone():
            logger.info(f"🔄 發現重複標題雜湊: {title[:50]}...")
            return True
        
        # 2. 檢查相同的 URL 雜湊
        cursor.execute('SELECT title FROM processed_news WHERE url_hash = ?', (url_hash,))
        if cursor.fetchone():
            logger.info(f"🔄 發現重複URL: {title[:50]}...")
            return True
        
        # 3. 檢查文字相似度和 URL 相似度
        cursor.execute('''
            SELECT normalized_title, link FROM processed_news 
            WHERE processed_at > ? 
            ORDER BY processed_at DESC 
            LIMIT 200
        ''', ((now - timedelta(hours=48)).isoformat(),))
        
        for stored_title, stored_link in cursor.fetchall():
            # 文字相似度檢查
            text_sim = calculate_text_similarity(normalized, stored_title)
            if text_sim >= TEXT_SIMILARITY_THRESHOLD:
                logger.info(f"🔄 發現高文字相似度 ({text_sim:.2f}): {title[:50]}...")
                return True
            
            # URL 相似度檢查
            url_sim = calculate_url_similarity(link, stored_link)
            if url_sim >= URL_SIMILARITY_THRESHOLD:
                logger.info(f"🔄 發現相似URL ({url_sim:.2f}): {title[:50]}...")
                return True
        
        return False
        
    except Exception as e:
        logger.error(f"❌ 重複檢測失敗: {e}")
        return False

def save_processed_news(title, link, source, category, pub_date, conn):
    """儲存已處理的新聞"""
    if not conn:
        return
    
    try:
        normalized = normalize_title(title)
        title_hash = generate_hash(normalized)
        url_hash = generate_hash(link)
        
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO processed_news 
            (id, title, normalized_title, link, source, category, pub_date, processed_at, title_hash, url_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            f"{title_hash}_{int(now.timestamp())}",
            title, normalized, link, source, category, 
            pub_date, now.isoformat(), title_hash, url_hash
        ))
        conn.commit()
    except Exception as e:
        logger.error(f"❌ 儲存新聞失敗: {e}")

# ✅ 修改網址處理，避免 LINE 預覽
def create_clean_url(long_url):
    """建立避免 LINE 預覽的網址"""
    try:
        # 方法1: 使用 TinyURL
        encoded_url = quote(long_url, safe='')
        api_url = f"http://tinyurl.com/api-create.php?url={encoded_url}"
        res = requests.get(api_url, timeout=8)
        
        if res.status_code == 200 and res.text.startswith('http'):
            short_url = res.text.strip()
            # 加上破壞預覽的參數
            return f"{short_url}?v={int(time.time())}"
        
    except Exception as e:
        logger.warning(f"⚠️ 短網址失敗: {e}")
    
    # 備用方案：直接在原網址加參數
    separator = '&' if '?' in long_url else '?'
    return f"{long_url}{separator}cache_bust={int(time.time())}&noprev=1"

def classify_news(title):
    """新聞分類"""
    normalized_title = normalize_title(title)
    
    # 依序檢查分類，優先檢查特定公司
    for category, keywords in CATEGORY_KEYWORDS.items():
        if category == "其他":  # 跳過「其他」分類
            continue
        for keyword in keywords:
            if keyword.lower() in normalized_title:
                return category
    
    return "其他"

def is_taiwan_news(source_name, link, title):
    """判斷是否為台灣新聞"""
    taiwan_sources = [
        '工商時報', '中國時報', '經濟日報', '三立新聞網', '自由時報', '聯合新聞網',
        '鏡週刊', '台灣雅虎', '鉅亨網', '中時新聞網', 'Ettoday新聞雲', 'ETtoday',
        '天下雜誌', '奇摩新聞', '《現代保險》雜誌', '遠見雜誌', '商業周刊', '今周刊',
        'MoneyDJ', '鉅亨', 'Anue', '理財網', '經濟通', '卡優新聞網'
    ]
    
    # 檢查來源
    if any(taiwan_source in source_name for taiwan_source in taiwan_sources):
        if "香港經濟日報" not in source_name:  # 排除香港媒體
            return True
    
    # 檢查網域
    if '.tw' in link or 'yahoo.com' in link:
        return True
    
    # 檢查標題內容（台灣特有詞彙）
    taiwan_terms = ['新台幣', '立法院', '行政院', '金管會', '央行', '台股', '台灣', '北市', '高雄']
    if any(term in title for term in taiwan_terms):
        return True
    
    return False

def is_semantically_similar(title, processed_embeddings):
    """語意相似度檢測"""
    if not model or not processed_embeddings:
        return False
    
    try:
        norm_title = normalize_title(title)
        if not norm_title:
            return False
        
        current_embedding = model.encode([norm_title])
        similarities = cosine_similarity(current_embedding, processed_embeddings)[0]
        max_similarity = np.max(similarities)
        
        if max_similarity >= SIMILARITY_THRESHOLD:
            logger.info(f"🔄 發現語意相似新聞 ({max_similarity:.3f}): {title[:50]}...")
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"❌ 語意相似度檢測失敗: {e}")
        return False

def fetch_news():
    """主要新聞抓取函數"""
    logger.info("🚀 開始抓取新聞...")
    
    conn = init_database()
    if not conn:
        logger.error("❌ 資料庫連接失敗，無法繼續")
        return {}
    
    rss_urls = [
        "https://news.google.com/rss/search?q=(新光金控+OR+新光人壽+OR+台新金控+OR+台新人壽+OR+壽險+OR+金控+OR+人壽)+when:1d&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
        "https://news.google.com/rss/search?q=新光金控+OR+新光人壽+OR+新壽+OR+吳東進+when:1d&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
        "https://news.google.com/rss/search?q=台新金控+OR+台新人壽+OR+台新壽+OR+吳東亮+when:1d&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
        "https://news.google.com/rss/search?q=(壽險+OR+健康險+OR+意外險+OR+人壽)+when:1d&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
        "https://news.google.com/rss/search?q=(金控+OR+金融控股)+when:1d&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    ]

    classified_news = {cat: [] for cat in CATEGORY_KEYWORDS}
    processed_embeddings = []
    stats = {
        'total_fetched': 0,
        'processed': 0,
        'duplicates': 0,
        'filtered_out': 0
    }

    # 載入最近的新聞標題進行比較
    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT normalized_title FROM processed_news 
            WHERE processed_at > ? 
            ORDER BY processed_at DESC 
            LIMIT 300
        ''', ((now - timedelta(hours=48)).isoformat(),))
        
        recent_titles = [row[0] for row in cursor.fetchall()]
        
        if recent_titles and model:
            logger.info(f"✅ 載入 {len(recent_titles)} 個最近標題用於語意比較")
            processed_embeddings = model.encode(recent_titles)
            
    except Exception as e:
        logger.error(f"❌ 載入歷史標題失敗: {e}")

    # 處理每個 RSS 來源
    for i, rss_url in enumerate(rss_urls, 1):
        try:
            logger.info(f"📡 處理 RSS 來源 {i}/{len(rss_urls)}")
            
            res = requests.get(rss_url, timeout=15, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            
            if res.status_code != 200:
                logger.warning(f"⚠️ RSS 回應異常: {res.status_code}")
                continue

            root = ET.fromstring(res.content)
            items = root.findall(".//item")
            stats['total_fetched'] += len(items)
            
            logger.info(f"✅ 抓到 {len(items)} 筆新聞")

            for item in items:
                try:
                    # 解析新聞項目
                    title_elem = item.find('title')
                    link_elem = item.find('link')
                    pubDate_elem = item.find('pubDate')
                    
                    if not all([title_elem, link_elem, pubDate_elem]):
                        continue

                    title = title_elem.text.strip()
                    link = link_elem.text.strip()
                    pubDate_str = pubDate_elem.text.strip()
                    
                    if not title or title.startswith("Google ニュース"):
                        continue

                    source_elem = item.find('source')
                    source_name = source_elem.text.strip() if source_elem is not None else "未標示"
                    
                    # 解析發布時間
                    try:
                        pub_datetime = email.utils.parsedate_to_datetime(pubDate_str).astimezone(TW_TZ)
                    except:
                        continue

                    # 基本過濾條件
                    if now - pub_datetime > timedelta(hours=24):
                        stats['filtered_out'] += 1
                        continue
                        
                    if any(bad_kw in title for bad_kw in EXCLUDED_KEYWORDS):
                        stats['filtered_out'] += 1
                        continue
                        
                    if not is_taiwan_news(source_name, link, title):
                        stats['filtered_out'] += 1
                        continue

                    # 重複檢測
                    if is_duplicate_news(title, link, conn):
                        stats['duplicates'] += 1
                        continue
                    
                    if is_semantically_similar(title, processed_embeddings):
                        stats['duplicates'] += 1
                        continue

                    # 新聞處理
                    clean_url = create_clean_url(link)
                    category = classify_news(title)
                    
                    # 格式化新聞（避免 LINE 預覽）
                    formatted = f"📰 {title}\n📌 {source_name}\n🔗 詳情: {clean_url}"
                    classified_news[category].append(formatted)
                    
                    # 儲存到資料庫
                    save_processed_news(title, link, source_name, category, 
                                      pub_datetime.isoformat(), conn)
                    
                    # 更新語意比較基準
                    if model and len(processed_embeddings) > 0:
                        try:
                            new_embedding = model.encode([normalize_title(title)])
                            processed_embeddings = np.vstack([processed_embeddings, new_embedding])
                        except:
                            pass
                    
                    stats['processed'] += 1
                    
                except Exception as e:
                    logger.error(f"❌ 處理單筆新聞失敗: {e}")
                    continue

        except Exception as e:
            logger.error(f"❌ 處理 RSS 來源失敗: {e}")
            continue

    conn.close()
    
    # 輸出統計資訊
    logger.info(f"""
📊 新聞處理統計:
   總抓取: {stats['total_fetched']} 筆
   成功處理: {stats['processed']} 筆
   重複過濾: {stats['duplicates']} 筆
   其他過濾: {stats['filtered_out']} 筆
""")
    
    return classified_news

def send_message_by_category(news_by_category):
    """分類發送 LINE 訊息"""
    if not ACCESS_TOKEN:
        logger.error("❌ ACCESS_TOKEN 未設定，無法發送訊息")
        return
    
    max_length = 3800  # LINE 訊息長度限制
    successful_sends = 0
    
    for category, messages in news_by_category.items():
        if not messages:
            continue
            
        try:
            # 建立分類標題
            title = f"【{today} {category} 新聞】共 {len(messages)} 則"
            divider = "=" * 35
            content = f"\n{divider}\n".join(messages)
            full_message = f"{title}\n{divider}\n{content}"
            
            # 處理超長訊息
            if len(full_message) <= max_length:
                if broadcast_message(full_message):
                    successful_sends += 1
            else:
                # 分段發送
                segments = []
                current_segment = f"{title}\n{divider}\n"
                
                for msg in messages:
                    if len(current_segment + msg + f"\n{divider}\n") <= max_length:
                        current_segment += msg + f"\n{divider}\n"
                    else:
                        segments.append(current_segment.rstrip(f"\n{divider}\n"))
                        current_segment = f"{title} (續)\n{divider}\n{msg}\n{divider}\n"
                
                if current_segment.strip():
                    segments.append(current_segment.rstrip(f"\n{divider}\n"))
                
                for i, segment in enumerate(segments):
                    if broadcast_message(segment):
                        successful_sends += 1
                    time.sleep(1)  # 避免發送過快
                        
        except Exception as e:
            logger.error(f"❌ 發送 {category} 分類失敗: {e}")

    # 發送無新聞通知
    empty_categories = [cat for cat, msgs in news_by_category.items() if not msgs]
    if empty_categories:
        title = f"【{today} 無新聞分類】"
        content = "\n".join(f"📂 {cat}: 無相關新聞" for cat in empty_categories)
        broadcast_message(f"{title}\n{content}")
        
    logger.info(f"✅ 成功發送 {successful_sends} 個分類的訊息")

def broadcast_message(message):
    """發送 LINE 廣播訊息"""
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

    try:
        logger.info(f"📤 發送訊息 ({len(message)} 字元)")
        res = requests.post(url, headers=headers, json=data, timeout=15)
        
        if res.status_code == 200:
            logger.info("✅ 訊息發送成功")
            return True
        else:
            logger.error(f"❌ 發送失敗 - 狀態碼: {res.status_code}, 回應: {res.text}")
            return False
            
    except Exception as e:
        logger.error(f"❌ 發送訊息異常: {e}")
        return False

if __name__ == "__main__":
    start_time = time.time()
    logger.info(f"🚀 新聞爬取系統啟動 - {now}")
    
    try:
        news = fetch_news()
        
        # 檢查是否有新聞需要發送
        total_news = sum(len(msgs) for msgs in news.values())
        
        if total_news > 0:
            logger.info(f"📨 準備發送 {total_news} 則新聞")
            send_message_by_category(news)
        else:
            logger.info("ℹ️ 沒有符合條件的新聞")
            # 發送無新聞通知
            broadcast_message(f"【{today} 業企部新聞】\n今日暫無符合條件的重點新聞")
        
        elapsed = time.time() - start_time
        logger.info(f"✅ 系統執行完成，耗時 {elapsed:.1f} 秒")
        
    except Exception as e:
        logger.error(f"❌ 系統執行失敗: {e}")
        # 發送錯誤通知
        if ACCESS_TOKEN:
            broadcast_message(f"【系統通知】\n新聞爬取系統執行異常: {str(e)[:100]}")



