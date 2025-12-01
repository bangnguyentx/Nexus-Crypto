import os
import asyncio
import logging
import threading
import random
from datetime import datetime
from typing import Dict, List

import ccxt
import ccxt.async_support as ccxt_async
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from flask import Flask, jsonify

from storage import Storage
import analysis

# ==================== CONFIG ====================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8322194930:AAEbemqNTWGAKoLwl23bwziKatEb6jx5ZIM")
PORT = int(os.getenv("PORT", 10000))
SCAN_INTERVAL = 300  # 5 minutes

# Multiple exchanges to avoid IP blocking
EXCHANGES = [
    {"id": "binance", "class": ccxt_async.binance},
    {"id": "bybit", "class": ccxt_async.bybit},
    {"id": "bitget", "class": ccxt_async.bitget},
    {"id": "okx", "class": ccxt_async.okx},
]

# Symbols to scan (15 coins)
SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "LINK/USDT", "DOGE/USDT",
    "XRP/USDT", "ETC/USDT", "LTC/USDT", "BCH/USDT", "BNB/USDT",
    "ADA/USDT", "XMR/USDT", "DASH/USDT", "ZEC/USDT", "AVAX/USDT"
]

# Vietnamese day names
VIETNAMESE_DAYS = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]

# ==================== LOGGING ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== STORAGE ====================
storage = Storage()

# ==================== FLASK APP ====================
app = Flask(__name__)

@app.route('/')
def home():
    stats = storage.get_stats()
    return f"""
    <html>
        <head>
            <title>Signal Bot - Auto Scanner</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; background: #0f172a; color: white; }}
                .container {{ max-width: 800px; margin: 0 auto; }}
                .card {{ background: #1e293b; padding: 20px; border-radius: 10px; margin: 20px 0; }}
                .stat {{ display: inline-block; margin: 10px 20px; }}
                .value {{ font-size: 24px; color: #60a5fa; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🤖 Signal Trading Bot</h1>
                <div class="card">
                    <h3>📊 System Status</h3>
                    <div class="stat">Active Users: <span class="value">{stats['active_users']}</span></div>
                    <div class="stat">Total Signals: <span class="value">{stats['total_signals']}</span></div>
                    <p>🔄 Scanning 15 coins every 5 minutes</p>
                    <p>⚡ Using multiple exchanges to avoid rate limits</p>
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

@app.route('/stats')
def stats():
    return jsonify(storage.get_stats())

# ==================== HELPER FUNCTIONS ====================
def get_vietnamese_day() -> str:
    """Get current Vietnamese day name"""
    day_index = datetime.now().weekday()  # Monday=0, Sunday=6
    return VIETNAMESE_DAYS[day_index]

def calculate_tp_sl(signal_type: str, entry_price: float) -> Dict[str, float]:
    """Calculate Take Profit and Stop Loss levels"""
    if signal_type == "LONG":
        # TP: +2%, SL: -1% (RR 2:1)
        tp = entry_price * 1.02
        sl = entry_price * 0.99
        rr_ratio = 2.0
    else:  # SHORT
        # TP: -2%, SL: +1% (RR 2:1)
        tp = entry_price * 0.98
        sl = entry_price * 1.01
        rr_ratio = 2.0
    
    return {
        "tp": round(tp, 4),
        "sl": round(sl, 4),
        "rr_ratio": rr_ratio
    }

def format_signal_message(symbol: str, signal_data: Dict, levels: Dict) -> str:
    """Format the signal message"""
    day_name = get_vietnamese_day()
    coin_name = symbol.replace("/USDT", "")
    
    # Format entry price based on coin value
    entry_price = signal_data['entry']
    if entry_price < 1:
        entry_fmt = f"{entry_price:.6f}"
        tp_fmt = f"{levels['tp']:.6f}"
        sl_fmt = f"{levels['sl']:.6f}"
    elif entry_price < 100:
        entry_fmt = f"{entry_price:.4f}"
        tp_fmt = f"{levels['tp']:.4f}"
        sl_fmt = f"{levels['sl']:.4f}"
    else:
        entry_fmt = f"{entry_price:.2f}"
        tp_fmt = f"{levels['tp']:.2f}"
        sl_fmt = f"{levels['sl']:.2f}"
    
    message = f"""🤖 Tín hiệu {day_name}
#{coin_name} – {signal_data['signal']} 📌

🔴 Entry: {entry_fmt}
🆗 Take Profit: {tp_fmt}
🙅‍♂️ Stop-Loss: {sl_fmt}
🪙 Tỉ lệ RR: {levels['rr_ratio']:.1f}

🧠 By Tool Bot

⚠️ Nhất định phải tuân thủ quản lý rủi ro – Đi tối đa 2-3% risk, Bot chỉ để tham khảo, win 3 lệnh nên ngưng"""
    
    return message

async def fetch_ohlcv(exchange_class, symbol: str, timeframe: str = "5m", limit: int = 100):
    """Fetch OHLCV data from exchange with error handling"""
    exchange = exchange_class({
        'enableRateLimit': True,
        'options': {'defaultType': 'future'}
    })
    
    try:
        await exchange.load_markets()
        ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        await exchange.close()
        return ohlcv
    except Exception as e:
        logger.error(f"Error fetching {symbol} from {exchange_class.__name__}: {e}")
        await exchange.close()
        return None

# ==================== SCANNER ====================
class SignalScanner:
    def __init__(self, bot_application):
        self.bot_app = bot_application
        self.running = False
        self.last_scan_time = None
        
    async def scan_symbols(self):
        """Scan all symbols for signals"""
        logger.info(f"🔍 Starting scan... (Active users: {len(storage.get_users())})")
        
        # Distribute symbols among exchanges
        symbols_per_exchange = len(SYMBOLS) // len(EXCHANGES) + 1
        
        for i, exchange_config in enumerate(EXCHANGES):
            exchange_class = exchange_config["class"]
            start_idx = i * symbols_per_exchange
            end_idx = min(start_idx + symbols_per_exchange, len(SYMBOLS))
            exchange_symbols = SYMBOLS[start_idx:end_idx]
            
            if not exchange_symbols:
                continue
                
            for symbol in exchange_symbols:
                try:
                    # Fetch data
                    ohlcv = await fetch_ohlcv(exchange_class, symbol)
                    if not ohlcv:
                        continue
                    
                    # Convert to DataFrame and analyze
                    df = analysis.ohlcv_to_df(ohlcv)
                    indicators = analysis.calculate_indicators(df)
                    
                    if indicators.get("error"):
                        continue
                    
                    # Check for signal
                    signal = analysis.check_signal(indicators)
                    
                    if signal and signal.get("strength", 0) > 50:  # Only send strong signals
                        await self.send_signal_to_users(symbol, signal)
                        # Small delay to avoid rate limits
                        await asyncio.sleep(1)
                        
                except Exception as e:
                    logger.error(f"Error scanning {symbol}: {e}")
                    continue
                    
                # Small delay between symbols
                await asyncio.sleep(0.5)
        
        self.last_scan_time = datetime.now()
        logger.info(f"✅ Scan completed at {self.last_scan_time}")
    
    async def send_signal_to_users(self, symbol: str, signal_data: Dict):
        """Send signal to all active users"""
        # Calculate TP/SL levels
        levels = calculate_tp_sl(signal_data['signal'], signal_data['entry'])
        
        # Format message
        message = format_signal_message(symbol, signal_data, levels)
        
        # Send to all active users
        users = storage.get_users()
        success_count = 0
        
        for user_id in users:
            try:
                await self.bot_app.bot.send_message(
                    chat_id=user_id,
                    text=message
                )
                storage.increment_signal_count(user_id)
                success_count += 1
                
                # Small delay between messages
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.warning(f"Failed to send to user {user_id}: {e}")
                # If user blocked the bot, mark as inactive
                if "bot was blocked" in str(e) or "chat not found" in str(e):
                    storage.remove_user(user_id)
        
        if success_count > 0:
            logger.info(f"📨 Sent {signal_data['signal']} signal for {symbol} to {success_count} users")
    
    async def run(self):
        """Main scanner loop"""
        self.running = True
        logger.info("🚀 Signal Scanner started")
        
        while self.running:
            try:
                await self.scan_symbols()
            except Exception as e:
                logger.error(f"Scanner error: {e}")
            
            # Wait for next scan interval
            for i in range(SCAN_INTERVAL):
                if not self.running:
                    break
                await asyncio.sleep(1)
        
        logger.info("🛑 Signal Scanner stopped")
    
    def stop(self):
        self.running = False

# ==================== TELEGRAM HANDLERS ====================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user_id = update.effective_user.id
    storage.add_user(user_id)
    
    welcome_message = """🚀 **SIGNAL TRADING BOT**

Chào mừng bạn đến với bot gửi tín hiệu giao dịch tự động!

📊 **Tôi sẽ gửi tín hiệu cho 15 coins:**
BTC, ETH, SOL, LINK, DOGE, XRP, ETC, LTC, BCH, BNB, ADA, XMR, DASH, ZEC, AVAX

⏰ **Quét tự động mỗi 5 phút**
🎯 **Thuật toán Physics Momentum**
⚡ **Sử dụng đa sàn để tránh bị chặn**

Bot sẽ tự động gửi tín hiệu khi phát hiện cơ hội tốt. Không cần thiết lập gì thêm!

Chúc bạn trade an toàn và hiệu quả! 🎯"""
    
    await update.message.reply_text(welcome_message, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_message = """📖 **HƯỚNG DẪN SỬ DỤNG**

Bot hoạt động hoàn toàn tự động:
• Quét 15 coins mỗi 5 phút
• Gửi tín hiệu khi phát hiện cơ hội
• Format đầy đủ Entry, TP, SL, RR

🔹 **Các lệnh có sẵn:**
/start - Đăng ký nhận tín hiệu
/help - Hiển thị hướng dẫn
/stats - Thống kê bot

⚡ **Lưu ý quan trọng:**
• Chỉ trade với risk 2-3% mỗi lệnh
• Dừng sau 3 lệnh thắng liên tiếp
• Bot chỉ để tham khảo, tự chịu trách nhiệm

Chúc bạn trade thành công! 💪"""
    
    await update.message.reply_text(help_message, parse_mode='Markdown')

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stats command"""
    stats = storage.get_stats()
    user_id = update.effective_user.id
    user_data = storage._read_all().get(str(user_id), {})
    
    stats_message = f"""📊 **THỐNG KÊ BOT**

• 👥 Tổng người dùng: {stats['total_users']}
• ✅ Đang hoạt động: {stats['active_users']}
• 📨 Tổng tín hiệu đã gửi: {stats['total_signals']}
• 🏦 Số sàn sử dụng: {len(EXCHANGES)}
• ⏰ Quét mỗi: 5 phút

• 📈 Số tín hiệu bạn nhận: {user_data.get('signal_count', 0)}
• 📅 Tham gia từ: {user_data.get('joined_at', 'N/A')}

Bot đang chạy ổn định! 🚀"""
    
    await update.message.reply_text(stats_message, parse_mode='Markdown')

async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle unknown commands"""
    await update.message.reply_text(
        "❓ Tôi không hiểu lệnh này.\n\n"
        "Sử dụng /help để xem hướng dẫn."
    )

# ==================== MAIN ====================
def main():
    """Main function to start the bot"""
    # Create Telegram application
    telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Add handlers
    telegram_app.add_handler(CommandHandler("start", start_command))
    telegram_app.add_handler(CommandHandler("help", help_command))
    telegram_app.add_handler(CommandHandler("stats", stats_command))
    telegram_app.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    
    # Create and start scanner
    scanner = SignalScanner(telegram_app)
    
    # Start everything in separate threads
    def run_telegram():
        """Run Telegram bot in separate thread"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def start_all():
            await telegram_app.initialize()
            await telegram_app.start()
            
            # Start scanner
            scanner_task = asyncio.create_task(scanner.run())
            
            # Start polling
            await telegram_app.updater.start_polling()
            
            # Keep running
            await scanner_task
        
        try:
            loop.run_until_complete(start_all())
        except KeyboardInterrupt:
            logger.info("Shutting down...")
        finally:
            scanner.stop()
            loop.run_until_complete(telegram_app.stop())
            loop.close()
    
    # Start Telegram in background thread
    telegram_thread = threading.Thread(target=run_telegram, daemon=True)
    telegram_thread.start()
    
    logger.info("🤖 Bot started successfully!")
    logger.info(f"🌐 Web interface: http://0.0.0.0:{PORT}")
    logger.info(f"🔍 Scanning {len(SYMBOLS)} coins every {SCAN_INTERVAL} seconds")
    
    # Start Flask app in main thread
    app.run(host="0.0.0.0", port=PORT, debug=False)

if __name__ == "__main__":
    main()
