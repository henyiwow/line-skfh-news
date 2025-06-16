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

# ✅ 初始化語意模型 (可選)
try:
    model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
    logger.info("✅ AI 模型載入成功")
    USE_AI_MODEL = True
except Exception as e:
    logger.warning(f"⚠️ AI 模型載入失敗，將使用文字比對: {e}")
    model = None
    USE_AI_MODEL = False

# ✅ 大幅放寬去重參數
SIMILARITY_THRESHOLD = 0.95       # 語意相似度門檻 (提高到非常嚴格)
TEXT_SIMILARITY_THRESHOLD = 0.90   # 文字相似度門檻 (提高到非常嚴格)
URL_SIMILARITY_THRESHOLD = 0.95    # URL 相似度門檻 (提高到非常嚴格)
ENABLE_DEDUP = True                # 可以關閉去重功能進行測試

ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')
if ACCESS_TOKEN:
    logger.info(f"✅ Access Token 已設定，前10碼：{ACCESS_TOKEN[:10]}")
else:
    logger.error("❌ ACCESS_TOKEN 環境變數未設定")

# ✅ 放寬關鍵字比對，增加更多關鍵字
CATEGORY_KEYWORDS = {
    "新光金控": [
        "新光金", "新光人壽", "新壽", "吳東進", "新光金控", "新光保險",
        "新光銀行", "新光投信", "新光證券", "Shin Kong"
    ],
    "台新金控": [
        "台新金", "台新人壽", "台新壽", "吳東亮", "台新金控", "台新保險", 
        "台新銀行", "台新證券", "台新投信", "Taishin"
    ],
    "金控": [
        "金控", "金融控股", "中信金", "玉山金", "永豐金", "國泰金", "富邦金", 
        "台灣金", "第一金", "元大金", "開發金", "兆豐金", "華南金", "彰銀金",
        "金融業", "銀行業", "證券業"
    ],
    "保險": [
        "保險", "壽險", "健康險", "意外險", "人壽", "產險", "車險", "保單",
        "理賠", "投保", "保費", "保險業", "再保", "微型保險", "數位保險"
    ],
    "其他": []
}

# ✅ 大幅減少排除關鍵字，只排除明顯無關的
EXCLUDED_KEYWORDS = [
    '保險套', '避孕套', '保險套使用'
    # 移除其他排除條件，讓更多新聞通過
]

TW_TZ = timezone(timedelta(hours=8))
now = datetime.now(TW_TZ)
today = now.date()

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
        
        # 建立索引
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_title_hash ON processed_news(title_hash)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_processed_at ON processed_news(processed_at)')
        
        # 只清理超過3天的記錄 (縮短清理週期)
        days_ago = (now - timedelta(days=3)).isoformat()
        cursor.execute('DELETE FROM processed_news WHERE processed_at < ?', (days_ago,))
        deleted_count = cursor.rowcount
        
        conn.commit()
        logger.info(f"✅ 資料庫初始化完成，清理了 {deleted_count} 筆舊記錄")
        return conn
    except Exception as e:
        logger.error(f"❌ 資料庫初始化失敗: {e}")
        return None

def normalize_title(title):
    """簡化的標題正規化 - 保留更多原始資訊"""
    if not title:
        return ""
    
    # 只做最基本的清理
    title = re.sub(r'<[^>]+>', '', title)        # 移除 HTML 標籤
    title = re.sub(r'\s+', ' ', title)           # 合併多餘空白
    title = title.strip()
    
    # 不轉換大小寫，保留原始格式
    return title

def calculate_simple_similarity(text1, text2):
    """簡化的文字相似度計算"""
    if not text1 or not text2:
        return 0
    
    # 簡單的關鍵字重疊比較
    words1 = set(text1.split())
    words2 = set(text2.split())
    
    if not words1 or not words2:
        return 0
    
    intersection = words1.intersection(words2)
    union = words1.union(words2)
    return len(intersection) / len(union) if union else 0

def generate_hash(text):
    """生成文字雜湊"""
    if not text:
        return ""
    return hashlib.md5(text.encode('utf-8')).hexdigest()[:12]

def is_duplicate_news(title, link, conn):
    """大幅放寬的重複檢測"""
    if not ENABLE_DEDUP or not conn:
        return False
    
    try:
        normalized = normalize_title(title)
        title_hash = generate_hash(normalized)
        
        cursor = conn.cursor()
        
        # 只檢查完全相同的標題雜湊
        cursor.execute('SELECT title FROM processed_news WHERE title_hash = ?', (title_hash,))
        if cursor.fetchone():
            logger.info(f"🔄 發現完全相同標題: {title[:50]}...")
            return True
        
        # 只檢查完全相同的連結
        cursor.execute('SELECT title FROM processed_news WHERE link = ?', (link,))
        if cursor.fetchone():
            logger.info(f"🔄 發現相同連結: {title[:50]}...")
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

def create_clean_url(long_url):
    """建立避免 LINE 預覽的網址"""
    try:
        # 使用 TinyURL
        encoded_url = quote(long_url, safe='')
        api_url = f"http://tinyurl.com/api-create.php?url={encoded_url}"
        res = requests.get(api_url, timeout=8)
        
        if res.status_code == 200 and res.text.startswith('http'):
            short_url = res.text.strip()
            return f"{short_url}?t={int(time.time())}"
        
    except Exception as e:
        logger.warning(f"⚠️ 短網址失敗: {e}")
    
    # 備用方案
    separator = '&' if '?' in long_url else '?'
    return f"{long_url}{separator}t={int(time.time())}"

def classify_news(title):
    """放寬的新聞分類"""
    title_lower = title.lower()
    
    # 依序檢查分類
    for category, keywords in CATEGORY_KEYWORDS.items():
        if category == "其他":
            continue
        for keyword in keywords:
            if keyword.lower() in title_lower:
                logger.info(f"📂 分類為 [{category}]: {keyword} in {title[:50]}")
                return category
    
    logger.info(f"📂 分類為 [其他]: {title[:50]}")
    return "其他"

def is_taiwan_news(source_name, link, title):
    """大幅放寬台灣新聞判斷"""
    # 大幅擴展台灣新聞來源
    taiwan_sources = [
        '工商時報', '中國時報', '經濟日報', '三立新聞網', '自由時報', '聯合新聞網',
        '鏡週刊', '台灣雅虎', '鉅亨網', '中時新聞網', 'Ettoday新聞雲', 'ETtoday',
        '天下雜誌', '奇摩新聞', '現代保險', '遠見雜誌', '商業周刊', '今周刊',
        'MoneyDJ', '鉅亨', 'Anue', '理財網', '經濟通', '卡優新聞網', 'Yahoo',
        '蘋果新聞網', '中央社', 'NOWnews', '風傳媒', '新頭殼', 'Newtalk',
        '財訊', 'Smart', '鉅亨網', '工商', '經濟'
    ]
    
    # 檢查來源 (移除香港排除條件，先放寬測試)
    if any(taiwan_source in source_name for taiwan_source in taiwan_sources):
        logger.info(f"✅ 台灣新聞來源: {source_name}")
        return True
    
    # 檢查網域
    taiwan_domains = ['.tw', 'yahoo.com', 'google.com', 'ettoday', 'chinatimes', 'udn.com']
    if any(domain in link for domain in taiwan_domains):
        logger.info(f"✅ 台灣網域: {link}")
        return True
    
    # 大幅放寬，幾乎所有新聞都通過
    logger.info(f"✅ 預設通過: {source_name}")
    return True

def is_semantically_similar(title, processed_embeddings):
    """語意相似度檢測 (可選)"""
    if not USE_AI_MODEL or not model or not processed_embeddings or not ENABLE_DEDUP:
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
    """主要新聞抓取函數 - 放寬所有條件"""
    logger.info("🚀 開始抓取新聞...")
    
    conn = init_database()
    
    # 簡化 RSS URLs，移除時間限制
    rss_urls = [
        "https://news.google.com/rss/search?q=新光金控+OR+新光人壽+OR+台新金控+OR+台新人壽+OR+壽險+OR+金控+OR+人壽&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
        "https://news.google.com/rss/search?q=新光金控+OR+新光人壽+OR+新壽+OR+吳東進&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
        "https://news.google.com/rss/search?q=台新金控+OR+台新人壽+OR+台新壽+OR+吳東亮&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
        "https://news.google.com/rss/search?q=壽險+OR+健康險+OR+意外險+OR+人壽+OR+保險&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
        "https://news.google.com/rss/search?q=金控+OR+金融控股+OR+銀行&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    ]

    classified_news = {cat: [] for cat in CATEGORY_KEYWORDS}
    processed_embeddings = []
    stats = {
        'total_fetched': 0,
        'processed': 0,
        'duplicates': 0,
        'filtered_out': 0,
        'by_category': {cat: 0 for cat in CATEGORY_KEYWORDS}
    }

    # 載入最近的新聞 (縮短時間範圍)
    if USE_AI_MODEL and conn:
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT normalized_title FROM processed_news 
                WHERE processed_at > ? 
                LIMIT 100
            ''', ((now - timedelta(hours=24)).isoformat(),))
            
            recent_titles = [row[0] for row in cursor.fetchall()]
            
            if recent_titles and model:
                logger.info(f"✅ 載入 {len(recent_titles)} 個最近標題用於比較")
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
                        # 如果時間解析失敗，使用當前時間
                        pub_datetime = now
                        logger.warning(f"⚠️ 時間解析失敗，使用當前時間: {title[:30]}")

                    logger.info(f"📝 處理新聞: {title[:50]}... | 來源: {source_name}")

                    # 放寬基本過濾條件
                    
                    # 1. 時間過濾 - 延長到48小時
                    if now - pub_datetime > timedelta(hours=48):
                        stats['filtered_out'] += 1
                        logger.info(f"⏰ 時間過濾: {title[:30]}...")
                        continue
                    
                    # 2. 排除關鍵字檢查 - 只排除極少數
                    if any(bad_kw in title for bad_kw in EXCLUDED_KEYWORDS):
                        stats['filtered_out'] += 1
                        logger.info(f"🚫 關鍵字過濾: {title[:30]}...")
                        continue
                    
                    # 3. 台灣新聞檢查 - 大幅放寬
                    if not is_taiwan_news(source_name, link, title):
                        stats['filtered_out'] += 1
                        logger.info(f"🌏 地區過濾: {title[:30]}...")
                        continue

                    # 4. 重複檢測 - 可選
                    if is_duplicate_news(title, link, conn):
                        stats['duplicates'] += 1
                        continue
                    
                    if is_semantically_similar(title, processed_embeddings):
                        stats['duplicates'] += 1
                        continue

                    # 新聞通過所有檢查
                    clean_url = create_clean_url(link)
                    category = classify_news(title)
                    
                    # 格式化新聞
                    formatted = f"📰 {title}\n📌 {source_name}\n🔗 詳情: {clean_url}"
                    classified_news[category].append(formatted)
                    stats['by_category'][category] += 1
                    
                    # 儲存到資料庫
                    if conn:
                        save_processed_news(title, link, source_name, category, 
                                          pub_datetime.isoformat(), conn)
                    
                    # 更新語意比較基準
                    if USE_AI_MODEL and model and len(processed_embeddings) > 0:
                        try:
                            new_embedding = model.encode([normalize_title(title)])
                            processed_embeddings = np.vstack([processed_embeddings, new_embedding])
                        except:
                            pass
                    
                    stats['processed'] += 1
                    logger.info(f"✅ 成功處理: [{category}] {title[:30]}...")
                    
                except Exception as e:
                    logger.error(f"❌ 處理單筆新聞失敗: {e}")
                    continue

        except Exception as e:
            logger.error(f"❌ 處理 RSS 來源失敗: {e}")
            continue

    if conn:
        conn.close()
    
    # 輸出詳細統計
    logger.info(f"""
📊 新聞處理統計:
   總抓取: {stats['total_fetched']} 筆
   成功處理: {stats['processed']} 筆
   重複過濾: {stats['duplicates']} 筆
   其他過濾: {stats['filtered_out']} 筆
   
   分類統計:
   📂 新光金控: {stats['by_category']['新光金控']} 筆
   📂 台新金控: {stats['by_category']['台新金控']} 筆
   📂 金控: {stats['by_category']['金控']} 筆
   📂 保險: {stats['by_category']['保險']} 筆
   📂 其他: {stats['by_category']['其他']} 筆
""")
    
    return classified_news

def send_message_by_category(news_by_category):
    """分類發送 LINE 訊息"""
    if not ACCESS_TOKEN:
        logger.error("❌ ACCESS_TOKEN 未設定，無法發送訊息")
        return
    
    max_length = 3800
    successful_sends = 0
    total_news = sum(len(msgs) for msgs in news_by_category.values())
    
    logger.info(f"📨 準備發送 {total_news} 則新聞")
    
    for category, messages in news_by_category.items():
        if not messages:
            continue
            
        try:
            logger.info(f"📤 發送分類 [{category}]: {len(messages)} 則新聞")
            
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
        
    logger.info(f"✅ 成功發送 {successful_sends} 個訊息段落")

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
    logger.info(f"🚀 新聞爬取系統啟動 (放寬模式) - {now}")
    
    # 測試模式：可以關閉去重功能
    if os.getenv('DISABLE_DEDUP') == 'true':
        ENABLE_DEDUP = False
        logger.info("🔓 去重功能已關閉 (測試模式)")
    
    try:
        news = fetch_news()
        
        # 檢查是否有新聞
        total_news = sum(len(msgs) for msgs in news.values())
        
        if total_news > 0:
            logger.info(f"📨 準備發送 {total_news} 則新聞")
            send_message_by_category(news)
        else:
            logger.warning("⚠️ 沒有符合條件的新聞")
            # 發送調試訊息
            if ACCESS_TOKEN:
                debug_msg = f"【{today} 系統通知】\n新聞爬取完成，但沒有符合條件的新聞\n請檢查關鍵字和過濾條件"
                broadcast_message(debug_msg)
        
        elapsed = time.time() - start_time
        logger.info(f"✅ 系統執行完成，耗時 {elapsed:.1f} 秒")
        
    except Exception as e:
        logger.error(f"❌ 系統執行失敗: {e}")
        # 發送錯誤通知
        if ACCESS_TOKEN:
            error_msg = f"【系統錯誤】\n新聞爬取系統執行異常\n錯誤: {str(e)[:100]}"
            broadcast_message(error_msg)



