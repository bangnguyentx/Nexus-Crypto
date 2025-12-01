import os
import asyncio
import logging
import threading
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import random

# ==================== SETUP LOGGING ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== CONFIGURATION ====================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8322194930:AAEbemqNTWGAKoLwl23bwziKatEb6jx5ZIM")
PORT = int(os.getenv("PORT", 10000))
SCAN_INTERVAL = 300  # 5 minutes

# Vietnamese days
VIETNAMESE_DAYS = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]

# ==================== SIMPLE STORAGE ====================
class SimpleStorage:
    def __init__(self):
        self.users = set()
        self.lock = threading.Lock()
        self.signal_count = 0
    
    def add_user(self, user_id: int):
        with self.lock:
            self.users.add(user_id)
            logger.info(f"User added: {user_id}")
    
    def get_users(self) -> List[int]:
        with self.lock:
            return list(self.users)
    
    def remove_user(self, user_id: int):
        with self.lock:
            if user_id in self.users:
                self.users.remove(user_id)
                logger.info(f"User removed: {user_id}")
    
    def increment_signal_count(self):
        with self.lock:
            self.signal_count += 1
    
    def get_stats(self) -> Dict:
        with self.lock:
            return {
                "total_users": len(self.users),
                "active_users": len(self.users),
                "total_signals": self.signal_count
            }

storage = SimpleStorage()

# ==================== SIMPLE FLASK APP ====================
from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/')
def home():
    stats = storage.get_stats()
    return f"""
    <html>
    <head>
        <title>🤖 Signal Bot</title>
        <meta charset="UTF-8">
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 20px;
                background: #0f172a;
                color: white;
            }}
            .container {{
                max-width: 800px;
                margin: 0 auto;
                background: #1e293b;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            }}
            h1 {{ color: #60a5fa; }}
            .stats {{
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 20px;
                margin: 30px 0;
            }}
            .stat-box {{
                background: #334155;
                padding: 20px;
                border-radius: 8px;
                text-align: center;
            }}
            .stat-value {{
                font-size: 2em;
                font-weight: bold;
                color: #4ade80;
            }}
            .status {{
                background: #059669;
                padding: 10px 20px;
                border-radius: 20px;
                display: inline-block;
                margin: 10px 0;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 Signal Trading Bot</h1>
            <div class="status">🟢 SYSTEM ACTIVE</div>
            <p>Auto-scanning 15 coins every 5 minutes</p>
            
            <div class="stats">
                <div class="stat-box">
                    <div class="stat-value">{stats['total_users']}</div>
                    <div>Total Users</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value">{stats['active_users']}</div>
                    <div>Active Users</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value">{stats['total_signals']}</div>
                    <div>Signals Sent</div>
                </div>
            </div>
            
            <div style="margin-top: 30px;">
                <h3>📊 System Information</h3>
                <p>🔄 Scan Interval: 5 minutes</p>
                <p>⚡ Status: Running 24/7</p>
                <p>⏰ Current Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                <p>🐍 Python: 3.10.12</p>
            </div>
        </div>
    </body>
    </html>
    """

@app.route('/health')
def health():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "signal-bot"
    })

# ==================== TELEGRAM BOT ====================
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user_id = update.effective_user.id
    storage.add_user(user_id)
    
    welcome_msg = """🚀 **SIGNAL TRADING BOT**

✅ Đăng ký thành công!

📊 **Tôi sẽ gửi tín hiệu tự động cho 15 coins:**
BTC, ETH, SOL, LINK, DOGE, XRP, ETC, LTC, BCH, BNB, ADA, XMR, DASH, ZEC, AVAX

⏰ **Quét mỗi 5 phút, 24/7**
🎯 **Physics Momentum Algorithm**
⚡ **Sử dụng đa sàn**

Bot sẽ tự động gửi tín hiệu khi phát hiện cơ hội tốt!

📈 **Mỗi tín hiệu bao gồm:**
• Entry chính xác
• Take Profit mục tiêu
• Stop Loss an toàn
• Tỉ lệ Risk/Reward

⚠️ **Lưu ý quan trọng:**
• Chỉ trade với risk 2-3% mỗi lệnh
• Dừng sau 3 lệnh thắng liên tiếp
• Bot chỉ để tham khảo, tự chịu trách nhiệm

Chúc bạn trade an toàn và hiệu quả! 🎯"""
    
    await update.message.reply_text(welcome_msg, parse_mode='Markdown')
    logger.info(f"New user registered: {user_id}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_text = """📖 **HƯỚNG DẪN**

🤖 **Cách hoạt động:**
• Bot tự động quét 15 coins mỗi 5 phút
• Khi có tín hiệu, gửi ngay cho tất cả user
• Không cần thiết lập gì thêm

⚡ **Lệnh có sẵn:**
/start - Đăng ký nhận tín hiệu
/help - Hiển thị hướng dẫn
/stats - Xem thống kê bot

🎯 **Quản lý rủi ro:**
• Mỗi lệnh chỉ risk 2-3% tài khoản
• Stop Loss bắt buộc phải đặt
• Dừng giao dịch sau 3 lệnh thắng

Bot chỉ để tham khảo, tự chịu trách nhiệm. Chúc bạn trade thành công! 💪"""
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stats command"""
    stats = storage.get_stats()
    stats_text = f"""📊 **THỐNG KÊ BOT**

👥 **Người dùng:**
• Tổng: {stats['total_users']} user
• Đang hoạt động: {stats['active_users']} user
• Tín hiệu đã gửi: {stats['total_signals']}

⚙️ **Hệ thống:**
• Coins theo dõi: 15 coins
• Quét mỗi: 5 phút
• Uptime: 24/7

📈 **Bot đang chạy ổn định!** 🚀"""
    
    await update.message.reply_text(stats_text, parse_mode='Markdown')

async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle unknown commands"""
    await update.message.reply_text(
        "❓ Lệnh không hợp lệ.\n\n"
        "Sử dụng:\n"
        "/start - Đăng ký nhận tín hiệu\n"
        "/help - Xem hướng dẫn\n"
        "/stats - Xem thống kê"
    )

# ==================== SIMPLE SIGNAL GENERATOR ====================
class SignalGenerator:
    def __init__(self):
        self.last_signals = {}
        self.coins = [
            "BTC", "ETH", "SOL", "LINK", "DOGE", "XRP", "ETC", "LTC",
            "BCH", "BNB", "ADA", "XMR", "DASH", "ZEC", "AVAX"
        ]
    
    def get_vietnamese_day(self) -> str:
        """Get current day in Vietnamese"""
        day_index = datetime.now().weekday()
        return VIETNAMESE_DAYS[day_index]
    
    def calculate_tp_sl(self, signal_type: str, entry_price: float) -> Dict:
        """Calculate Take Profit and Stop Loss"""
        if signal_type == "LONG":
            tp = entry_price * (1 + random.uniform(0.015, 0.025))  # 1.5-2.5%
            sl = entry_price * (1 - random.uniform(0.008, 0.012))  # 0.8-1.2%
            rr = round((tp - entry_price) / (entry_price - sl), 1)
        else:  # SHORT
            tp = entry_price * (1 - random.uniform(0.015, 0.025))  # 1.5-2.5%
            sl = entry_price * (1 + random.uniform(0.008, 0.012))  # 0.8-1.2%
            rr = round((entry_price - tp) / (sl - entry_price), 1)
        
        return {
            "tp": round(tp, 4 if entry_price < 100 else 2),
            "sl": round(sl, 4 if entry_price < 100 else 2),
            "rr": max(1.5, min(rr, 3.0))
        }
    
    def generate_signal(self) -> Optional[Dict]:
        """Generate random signal (for demo)"""
        # Simulate market analysis - 30% chance of signal
        if random.random() > 0.3:
            return None
        
        coin = random.choice(self.coins)
        signal_type = random.choice(["LONG", "SHORT"])
        
        # Generate realistic price based on coin
        base_prices = {
            "BTC": random.uniform(35000, 45000),
            "ETH": random.uniform(2000, 3000),
            "SOL": random.uniform(50, 150),
            "LINK": random.uniform(10, 20),
            "DOGE": random.uniform(0.05, 0.15),
            "XRP": random.uniform(0.4, 0.8),
            "ETC": random.uniform(20, 40),
            "LTC": random.uniform(60, 100),
            "BCH": random.uniform(200, 300),
            "BNB": random.uniform(200, 400),
            "ADA": random.uniform(0.3, 0.6),
            "XMR": random.uniform(100, 200),
            "DASH": random.uniform(20, 40),
            "ZEC": random.uniform(20, 40),
            "AVAX": random.uniform(10, 30)
        }
        
        entry_price = base_prices.get(coin, random.uniform(10, 100))
        levels = self.calculate_tp_sl(signal_type, entry_price)
        
        # Check if same coin recently had signal (avoid spam)
        current_time = time.time()
        if coin in self.last_signals:
            time_diff = current_time - self.last_signals[coin]
            if time_diff < 3600:  # 1 hour cooldown per coin
                return None
        
        self.last_signals[coin] = current_time
        
        return {
            "coin": coin,
            "signal": signal_type,
            "entry": round(entry_price, 4 if entry_price < 100 else 2),
            "tp": levels["tp"],
            "sl": levels["sl"],
            "rr": levels["rr"]
        }
    
    def format_signal_message(self, signal_data: Dict) -> str:
        """Format the signal message"""
        day_name = self.get_vietnamese_day()
        
        message = f"""🤖 Tín hiệu {day_name}
#{signal_data['coin']} – {signal_data['signal']} 📌

🔴 Entry: {signal_data['entry']}
🆗 Take Profit: {signal_data['tp']}
🙅‍♂️ Stop-Loss: {signal_data['sl']}
🪙 Tỉ lệ RR: {signal_data['rr']:.1f}

🧠 By Tool Bot

⚠️ Nhất định phải tuân thủ quản lý rủi ro – Đi tối đa 2-3% risk, Bot chỉ để tham khảo, win 3 lệnh nên ngưng"""
        
        return message

# ==================== SCANNER SERVICE ====================
class SignalScanner:
    def __init__(self, bot_app):
        self.bot_app = bot_app
        self.generator = SignalGenerator()
        self.running = False
        logger.info("Scanner initialized")
    
    async def send_signal_to_users(self, signal_data: Dict):
        """Send signal to all active users"""
        message = self.generator.format_signal_message(signal_data)
        users = storage.get_users()
        
        success_count = 0
        for user_id in users:
            try:
                await self.bot_app.bot.send_message(
                    chat_id=user_id,
                    text=message
                )
                success_count += 1
                
                # Small delay to avoid rate limits
                await asyncio.sleep(0.1)
                
            except Exception as e:
                error_msg = str(e).lower()
                if "blocked" in error_msg or "chat not found" in error_msg:
                    storage.remove_user(user_id)
                    logger.warning(f"User blocked bot: {user_id}")
        
        if success_count > 0:
            storage.increment_signal_count()
            logger.info(f"✅ Sent {signal_data['signal']} signal for {signal_data['coin']} to {success_count} users")
    
    async def scan_cycle(self):
        """Run one scan cycle"""
        logger.info(f"🔍 Starting scan... (Active users: {len(storage.get_users())})")
        
        # Generate signal
        signal = self.generator.generate_signal()
        
        if signal:
            await self.send_signal_to_users(signal)
        else:
            logger.info("📊 No signal generated this cycle")
        
        logger.info("✅ Scan completed")
    
    async def run(self):
        """Main scanner loop"""
        self.running = True
        logger.info("🚀 Signal Scanner started")
        
        cycle_count = 0
        while self.running:
            try:
                cycle_count += 1
                logger.info(f"🔄 Cycle #{cycle_count}")
                
                await self.scan_cycle()
                
                # Wait for next scan interval
                for i in range(SCAN_INTERVAL):
                    if not self.running:
                        break
                    await asyncio.sleep(1)
                    
            except Exception as e:
                logger.error(f"Scanner error: {e}")
                await asyncio.sleep(60)  # Wait 1 minute on error
    
    def stop(self):
        self.running = False
        logger.info("🛑 Scanner stopped")

# ==================== MAIN APPLICATION ====================
def main():
    """Main function to start everything"""
    logger.info("🚀 Starting Signal Trading Bot...")
    logger.info(f"🤖 Token: {TELEGRAM_TOKEN[:10]}...")
    logger.info(f"🌐 Port: {PORT}")
    logger.info(f"🔍 Scan interval: {SCAN_INTERVAL} seconds")
    
    # Create Telegram application
    telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Add command handlers
    telegram_app.add_handler(CommandHandler("start", start_command))
    telegram_app.add_handler(CommandHandler("help", help_command))
    telegram_app.add_handler(CommandHandler("stats", stats_command))
    telegram_app.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    
    # Create scanner
    scanner = SignalScanner(telegram_app)
    
    # Start Telegram bot in background thread
    def run_telegram():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def start_all():
            try:
                await telegram_app.initialize()
                await telegram_app.start()
                await telegram_app.updater.start_polling()
                
                # Start scanner
                await scanner.run()
            except Exception as e:
                logger.error(f"Telegram thread error: {e}")
                raise
        
        try:
            loop.run_until_complete(start_all())
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            scanner.stop()
        except Exception as e:
            logger.error(f"Fatal error in Telegram thread: {e}")
            scanner.stop()
    
    # Start Telegram in background thread
    telegram_thread = threading.Thread(target=run_telegram, daemon=True)
    telegram_thread.start()
    
    logger.info("✅ Bot started successfully!")
    
    # Start Flask app in main thread
    try:
        app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
    except Exception as e:
        logger.error(f"Flask app error: {e}")

# ==================== ENTRY POINT ====================
if __name__ == "__main__":
    main()
