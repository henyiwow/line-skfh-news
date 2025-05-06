import requests
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
import email.utils
from urllib.parse import quote

ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')
print("✅ Access Token 前 10 碼：", ACCESS_TOKEN[:10] if ACCESS_TOKEN else "未設定")

# 關鍵字可自訂
PREFERRED_SOURCES = [
    '工商時報', '中國時報', '經濟日報', 'Ettoday新聞雲', '工商時報網', 
    '中時新聞網', '中國時報', '台灣雅虎奇摩', '經濟日報網', '鉅亨網', 
    '聯合新聞網', '鏡周刊網',  '自由財經', '中華日報', '台灣新生報', 
    '旺報', '中國時報', '三立新聞網',  '天下雜誌', '奇摩新聞',
    '《現代保險》雜誌', 'MoneyDJ', '遠見雜誌', '自由時報', 'Ettoday財經雲',
    '鏡週刊Mirror Media', '匯流新聞網', 'Newtalk新聞', '奇摩股市', 'news.cnyes.com',
    '中央社', '民視新聞網', '風傳媒', 'CMoney', '大紀元'
]

# 分類關鍵字
CATEGORY_KEYWORDS = {
    "新光金控": ["新光金", "新光人壽", "新壽"],
    "保險": ["保險", "壽險", "健康險", "意外險"],
    "金控": ["金控", "金融控股"],
    "其他": []
}

# 排除關鍵字
EXCLUDED_TERMS = ["保險套"]

# 台灣時區
TW_TZ = timezone(timedelta(hours=8))
today = datetime.now(TW_TZ).date()

# 短網址工具
def shorten_url(long_url):
    try:
        encoded_url = quote(long_url, safe='')
        api_url = f"http://tinyurl.com/api-create.php?url={encoded_url}"
        res = requests.get(api_url, timeout=5)
        if res.status_code == 200:
            return res.text
    except Exception as e:
        print("⚠️ 短網址失敗：", e)
    return long_url

# 分類工具，排除無關詞彙
def classify_news(title):
    if any(ex in title for ex in EXCLUDED_TERMS):
        return "其他"
    for category, keywor

