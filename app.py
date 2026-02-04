import os
import feedparser
from datetime import datetime, timedelta
import tweepy
from groq import Groq
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# ── تنظیمات ────────────────────────────────────────────────────────────────
RSS_FEEDS = [
    "https://nitter.privacyredirect.com/khamenei_ir/rss",      # بیت رهبری
    "https://nitter.privacyredirect.com/elonmusk/rss",         # ایلان ماسک
    "https://nitter.privacyredirect.com/IrnaEnglish/rss",      # ایرنا انگلیسی
    "https://nitter.privacyredirect.com/IranIntl_En/rss",      # ایران اینترنشنال انگلیسی
    "https://nitter.privacyredirect.com/Tasnimnews_EN/rss",    # تسنیم انگلیسی
    "https://nitter.privacyredirect.com/EnglishFars/rss",      # فارس انگلیسی
    "https://nitter.privacyredirect.com/isna_farsi/rss",       # ایسنا
    "https://nitter.privacyredirect.com/MehrnewsCom/rss",      # مهر
]

X_API_KEY = os.getenv("X_API_KEY")
X_API_SECRET = os.getenv("X_API_SECRET")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN")
X_ACCESS_TOKEN_SECRET = os.getenv("X_ACCESS_TOKEN_SECRET")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# X client فقط برای پست کردن
x_client = tweepy.Client(
    consumer_key=X_API_KEY,
    consumer_secret=X_API_SECRET,
    access_token=X_ACCESS_TOKEN,
    access_token_secret=X_ACCESS_TOKEN_SECRET
)

groq_client = Groq(api_key=GROQ_API_KEY)

@app.route('/')
def health():
    return "Agent زنده است – هر ۲ ساعت چک می‌کنه", 200

def fetch_news():
    news_items = []
    three_hours_ago = datetime.utcnow() - timedelta(hours=3)
    
    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url, sanitize_html=False)
            print(f"[FETCH] {url} → {len(feed.entries)} entries")
            
            for entry in feed.entries[:8]:  # حداکثر ۸ تا از هر منبع
                pub_parsed = entry.get('published_parsed') or entry.get('updated_parsed')
                if pub_parsed:
                    pub_dt = datetime(*pub_parsed[:6])
                    if pub_dt > three_hours_ago:
                        title = entry.get('title', 'بدون عنوان')
                        link = entry.get('link', 'بدون لینک')
                        summary = entry.get('summary', '')[:300] or ''
                        news_items.append(f"[{entry.get('author', 'ناشناس')}] {title}\n{summary.strip()}\n{link}")
        except Exception as e:
            print(f"[ERROR] {url}: {str(e)}")
    
    if not news_items:
        return "در ۳ ساعت گذشته هیچ خبر جدیدی پیدا نشد (احتمالاً feedها بلاک شدن یا خالی هستن)."
    
    return "\n\n".join(news_items[:20])  # حداکثر ۲۰ خبر برای توکن

def generate_tweet(news_text):
    prompt = f"""
اخبار جمع‌آوری‌شده (منابع محدود – بیشتر داخلی + ایران اینترنشنال):
{news_text}

یک توییت کوتاه، جذاب و فارسی بنویس (حداکثر ۲۷۰ کاراکتر):
- خلاصه وضعیت فعلی کن
- اگر خبر مهم بود، هشدار یا پیش‌بینی کوتاه بده
- لحن حرفه‌ای، خنثی اما هوشمند
- ایموجی مرتبط بگذار (زیاده‌روی نکن)
- هشتگ مرتبط (مثل #ایران #خبر #تحلیل_ایران)
- اگر خبرها خیلی کم یا تکراری بود، اشاره کن که "اطلاعات محدود است"

فقط متن نهایی توییت رو برگردون – هیچ توضیحی ننویس.
"""
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=180,
            temperature=0.65
        )
        tweet = response.choices[0].message.content.strip()
        if len(tweet) > 280:
            tweet = tweet[:277] + "..."
        return tweet
    except Exception as e:
        print(f"[GROQ ERROR] {str(e)}")
        return "خطا در تولید توییت – منبع خبر کافی نبود یا مشکل API"

def post_tweet():
    print(f"\n[{datetime.now()}] شروع چرخه جدید...")
    news = fetch_news()
    tweet_text = generate_tweet(news)
    
    try:
        response = x_client.create_tweet(text=tweet_text)
        print(f"[SUCCESS] توییت پست شد:\n{tweet_text}\nID: {response.data['id']}")
    except Exception as e:
        print(f"[POST ERROR] {str(e)}")

# ── زمان‌بندی ────────────────────────────────────────────────────────────────
scheduler = BackgroundScheduler()
scheduler.add_job(post_tweet, 'interval', hours=2)
scheduler.start()

# برای Render – نگه داشتن اپ زنده
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)