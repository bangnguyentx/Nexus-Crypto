import os
import asyncio
import logging
import threading
import json
from datetime import datetime
from typing import Dict, List, Optional
import random
import time

import pandas as pd
import numpy as np
import ccxt
import ccxt.async_support as ccxt_async
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from flask import Flask, jsonify

# ==================== CONFIGURATION ====================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8322194930:AAEbemqNTWGAKoLwl23bwziKatEb6jx5ZIM")
PORT = int(os.getenv("PORT", 10000))
SCAN_INTERVAL = 300  # 5 minutes

# Multiple exchanges for load balancing
EXCHANGES = [
    {"id": "binance", "class": ccxt_async.binance},
    {"id": "bybit", "class": ccxt_async.bybit},
    {"id": "bitget", "class": ccxt_async.bitget},
    {"id": "okx", "class": ccxt_async.okx},
]

# 15 coins to scan
SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "LINK/USDT", "DOGE/USDT",
    "XRP/USDT", "ETC/USDT", "LTC/USDT", "BCH/USDT", "BNB/USDT",
    "ADA/USDT", "XMR/USDT", "DASH/USDT", "ZEC/USDT", "AVAX/USDT"
]

# Vietnamese days
VIETNAMESE_DAYS = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]

# ==================== SETUP LOGGING ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== STORAGE MANAGER ====================
class UserStorage:
    def __init__(self, filename="users.json"):
        self.filename = filename
        self.lock = threading.Lock()
        self._init_storage()
    
    def _init_storage(self):
        """Initialize storage file"""
        if not os.path.exists(self.filename):
            with self.lock:
                with open(self.filename, 'w') as f:
                    json.dump({}, f)
    
    def add_user(self, user_id: int, username: str = ""):
        """Add new user"""
        with self.lock:
            try:
                with open(self.filename, 'r') as f:
                    data = json.load(f)
            except:
                data = {}
            
            if str(user_id) not in data:
                data[str(user_id)] = {
                    "username": username,
                    "joined": datetime.now().isoformat(),
                    "active": True,
                    "signal_count": 0,
                    "last_signal": None
                }
                
                with open(self.filename, 'w') as f:
                    json.dump(data, f, indent=2)
                return True
        return False
    
    def get_active_users(self) -> List[int]:
        """Get list of active user IDs"""
        with self.lock:
            try:
                with open(self.filename, 'r') as f:
                    data = json.load(f)
            except:
                return []
            
            return [int(uid) for uid, user_data in data.items() 
                   if user_data.get("active", False)]
    
    def increment_signal_count(self, user_id: int):
        """Increment signal count for user"""
        with self.lock:
            try:
                with open(self.filename, 'r') as f:
                    data = json.load(f)
            except:
                return
            
            uid = str(user_id)
            if uid in data:
                data[uid]["signal_count"] = data[uid].get("signal_count", 0) + 1
                data[uid]["last_signal"] = datetime.now().isoformat()
                
                with open(self.filename, 'w') as f:
                    json.dump(data, f, indent=2)
    
    def deactivate_user(self, user_id: int):
        """Deactivate user (if blocked bot)"""
        with self.lock:
            try:
                with open(self.filename, 'r') as f:
                    data = json.load(f)
            except:
                return
            
            uid = str(user_id)
            if uid in data:
                data[uid]["active"] = False
                
                with open(self.filename, 'w') as f:
                    json.dump(data, f, indent=2)
    
    def get_stats(self) -> Dict:
        """Get system statistics"""
        with self.lock:
            try:
                with open(self.filename, 'r') as f:
                    data = json.load(f)
            except:
                return {"total_users": 0, "active_users": 0, "total_signals": 0}
            
            active = sum(1 for user in data.values() if user.get("active", False))
            total_signals = sum(user.get("signal_count", 0) for user in data.values())
            
            return {
                "total_users": len(data),
                "active_users": active,
                "total_signals": total_signals
            }

# Initialize storage
storage = UserStorage()

# ==================== FLASK APP ====================
app = Flask(__name__)

@app.route('/')
def home():
    stats = storage.get_stats()
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>📈 Signal Trading Bot</title>
        <style>
            body {{
                font-family: 'Segoe UI', Arial, sans-serif;
                margin: 0;
                padding: 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                min-height: 100vh;
            }}
            .container {{
                max-width: 800px;
                margin: 0 auto;
                background: rgba(255, 255, 255, 0.1);
                backdrop-filter: blur(10px);
                border-radius: 20px;
                padding: 40px;
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
            }}
            h1 {{ margin-top: 0; color: white; }}
            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                margin: 30px 0;
            }}
            .stat-card {{
                background: rgba(255, 255, 255, 0.2);
                padding: 20px;
                border-radius: 10px;
                text-align: center;
            }}
            .stat-value {{
                font-size: 2.5em;
                font-weight: bold;
                color: #4ade80;
            }}
            .stat-label {{
                font-size: 0.9em;
                opacity: 0.8;
                margin-top: 5px;
            }}
            .info-box {{
                background: rgba(255, 255, 255, 0.15);
                padding: 20px;
                border-radius: 10px;
                margin-top: 30px;
            }}
            .symbol-list {{
                display: flex;
                flex-wrap: wrap;
                gap: 10px;
                margin-top: 10px;
            }}
            .symbol {{
                background: rgba(255, 255, 255, 0.2);
                padding: 8px 16px;
                border-radius: 20px;
                font-size: 0.9em;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 Signal Trading Bot</h1>
            <p>Auto-scanning 15 cryptocurrencies every 5 minutes</p>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-value">{stats['total_users']}</div>
                    <div class="stat-label">Total Users</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{stats['active_users']}</div>
                    <div class="stat-label">Active Users</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{stats['total_signals']}</div>
                    <div class="stat-label">Signals Sent</div>
                </div>
            </div>
            
            <div class="info-box">
                <h3>📊 System Status: <span style="color:#4ade80">✅ ACTIVE</span></h3>
                <p>🔄 Scanning interval: 5 minutes</p>
                <p>⚡ Using 4 exchanges for reliability</p>
                <p>⏰ Last update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                
                <h4>📈 Tracking Coins:</h4>
                <div class="symbol-list">
                    {' '.join(f'<div class="symbol">{s.replace("/USDT", "")}</div>' for s in SYMBOLS)}
                </div>
            </div>
            
            <div style="margin-top: 30px; font-size: 0.9em; opacity: 0.7; text-align: center;">
                <p>Bot Token: {TELEGRAM_TOKEN[:10]}... | Running on Render</p>
            </div>
        </div>
    </body>
    </html>
    """

@app.route('/health')
def health_check():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "signal-bot",
        "active_users": storage.get_stats()["active_users"]
    })

# ==================== TECHNICAL INDICATORS ====================
class TechnicalIndicators:
    @staticmethod
    def calculate_rsi(prices: List[float], period: int = 14) -> float:
        """Calculate RSI manually"""
        if len(prices) < period + 1:
            return 50.0
        
        deltas = np.diff(prices[-period-1:])
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return float(rsi)
    
    @staticmethod
    def calculate_bollinger_bands(prices: List[float], period: int = 20, std_dev: int = 2) -> Dict:
        """Calculate Bollinger Bands"""
        if len(prices) < period:
            current_price = prices[-1] if prices else 100
            return {
                "upper": current_price * 1.02,
                "middle": current_price,
                "lower": current_price * 0.98
            }
        
        recent_prices = prices[-period:]
        middle = np.mean(recent_prices)
        std = np.std(recent_prices)
        
        return {
            "upper": middle + (std * std_dev),
            "middle": middle,
            "lower": middle - (std * std_dev)
        }
    
    @staticmethod
    def calculate_velocity(prices: List[float], period: int = 3) -> float:
        """Calculate velocity (rate of price change)"""
        if len(prices) < period + 1:
            return 0.0
        
        changes = []
        for i in range(-period, 0):
            if i < -1:
                change = ((prices[i] - prices[i-1]) / prices[i-1]) * 100
                changes.append(change)
        
        return float(np.mean(changes)) if changes else 0.0
    
    @staticmethod
    def analyze_symbol(prices: List[float]) -> Optional[Dict]:
        """Analyze symbol and return signal if any"""
        if len(prices) < 50:
            return None
        
        try:
            # Calculate indicators
            rsi = TechnicalIndicators.calculate_rsi(prices)
            bb = TechnicalIndicators.calculate_bollinger_bands(prices)
            velocity = TechnicalIndicators.calculate_velocity(prices)
            
            # Calculate acceleration (change in velocity)
            last_3_prices = prices[-4:-1] if len(prices) >= 5 else prices[-3:]
            prev_velocity = TechnicalIndicators.calculate_velocity(last_3_prices, period=2)
            acceleration = velocity - prev_velocity
            
            current_price = prices[-1]
            
            # Signal conditions
            long_conditions = (
                rsi < 30 and
                current_price < bb["lower"] and
                acceleration > 0 and
                velocity > prev_velocity
            )
            
            short_conditions = (
                rsi > 70 and
                current_price > bb["upper"] and
                acceleration < 0 and
                velocity < prev_velocity
            )
            
            if long_conditions:
                signal_strength = min(abs(30 - rsi) * 3 + abs(acceleration) * 10, 100)
                return {
                    "signal": "LONG",
                    "entry": current_price,
                    "rsi": rsi,
                    "velocity": velocity,
                    "acceleration": acceleration,
                    "strength": signal_strength
                }
            elif short_conditions:
                signal_strength = min(abs(rsi - 70) * 3 + abs(acceleration) * 10, 100)
                return {
                    "signal": "SHORT",
                    "entry": current_price,
                    "rsi": rsi,
                    "velocity": velocity,
                    "acceleration": acceleration,
                    "strength": signal_strength
                }
                
        except Exception as e:
            logger.error(f"Analysis error: {e}")
        
        return None

# ==================== HELPER FUNCTIONS ====================
def get_vietnamese_day() -> str:
    """Get current day in Vietnamese"""
    day_index = datetime.now().weekday()
    return VIETNAMESE_DAYS[day_index]

def calculate_tp_sl(signal_type: str, entry_price: float) -> Dict:
    """Calculate Take Profit and Stop Loss"""
    if signal_type == "LONG":
        tp = entry_price * 1.02  # +2%
        sl = entry_price * 0.99  # -1%
        rr = 2.0
    else:  # SHORT
        tp = entry_price * 0.98  # -2%
        sl = entry_price * 1.01  # +1%
        rr = 2.0
    
    return {
        "tp": round(tp, 4 if entry_price < 100 else 2),
        "sl": round(sl, 4 if entry_price < 100 else 2),
        "rr": rr
    }

def format_price(price: float) -> str:
    """Format price based on value"""
    if price < 1:
        return f"{price:.6f}"
    elif price < 100:
        return f"{price:.4f}"
    else:
        return f"{price:.2f}"

def format_signal_message(symbol: str, signal_data: Dict) -> str:
    """Format the final signal message"""
    day_name = get_vietnamese_day()
    coin_name = symbol.replace("/USDT", "")
    
    levels = calculate_tp_sl(signal_data["signal"], signal_data["entry"])
    
    entry_fmt = format_price(signal_data["entry"])
    tp_fmt = format_price(levels["tp"])
    sl_fmt = format_price(levels["sl"])
    
    message = f"""🤖 Tín hiệu {day_name}
#{coin_name} – {signal_data['signal']} 📌

🔴 Entry: {entry_fmt}
🆗 Take Profit: {tp_fmt}
🙅‍♂️ Stop-Loss: {sl_fmt}
🪙 Tỉ lệ RR: {levels['rr']:.1f}

🧠 By Tool Bot

⚠️ Nhất định phải tuân thủ quản lý rủi ro – Đi tối đa 2-3% risk, Bot chỉ để tham khảo, win 3 lệnh nên ngưng"""
    
    return message

async def fetch_ohlcv_data(exchange_class, symbol: str) -> Optional[List[float]]:
    """Fetch OHLCV data from exchange"""
    exchange = exchange_class({
        'enableRateLimit': True,
        'options': {'defaultType': 'future'}
    })
    
    try:
        await exchange.load_markets()
        ohlcv = await exchange.fetch_ohlcv(symbol, '5m', limit=100)
        await exchange.close()
        
        # Extract closing prices
        prices = [float(candle[4]) for candle in ohlcv]  # [timestamp, o, h, l, close, volume]
        return prices
    except Exception as e:
        logger.error(f"Error fetching {symbol}: {e}")
        await exchange.close()
        return None

# ==================== SCANNER ====================
class SignalScanner:
    def __init__(self, bot_app):
        self.bot_app = bot_app
        self.running = False
        self.indicators = TechnicalIndicators()
        
    async def scan_symbol(self, symbol: str, exchange_class) -> bool:
        """Scan a single symbol for signals"""
        try:
            # Fetch data
            prices = await fetch_ohlcv_data(exchange_class, symbol)
            if not prices or len(prices) < 50:
                return False
            
            # Analyze
            signal = self.indicators.analyze_symbol(prices)
            
            if signal and signal.get("strength", 0) > 40:
                # Send to all users
                await self.send_signal(symbol, signal)
                return True
                
        except Exception as e:
            logger.error(f"Scan error for {symbol}: {e}")
        
        return False
    
    async def send_signal(self, symbol: str, signal_data: Dict):
        """Send signal to all active users"""
        message = format_signal_message(symbol, signal_data)
        users = storage.get_active_users()
        
        success_count = 0
        failed_users = []
        
        for user_id in users:
            try:
                await self.bot_app.bot.send_message(
                    chat_id=user_id,
                    text=message
                )
                storage.increment_signal_count(user_id)
                success_count += 1
                
                # Small delay to avoid rate limits
                await asyncio.sleep(0.1)
                
            except Exception as e:
                error_msg = str(e).lower()
                if "blocked" in error_msg or "chat not found" in error_msg:
                    failed_users.append(user_id)
                logger.warning(f"Failed to send to {user_id}: {e}")
        
        # Deactivate blocked users
        for user_id in failed_users:
            storage.deactivate_user(user_id)
        
        if success_count > 0:
            logger.info(f"✅ Sent {signal_data['signal']} signal for {symbol} to {success_count} users")
    
    async def run_scan(self):
        """Run one complete scan of all symbols"""
        logger.info(f"🔍 Starting scan... (Active users: {len(storage.get_active_users())})")
        
        # Distribute symbols among exchanges
        symbols_per_exchange = max(1, len(SYMBOLS) // len(EXCHANGES))
        
        for i, exchange_config in enumerate(EXCHANGES):
            exchange_class = exchange_config["class"]
            exchange_name = exchange_config["id"]
            
            start_idx = i * symbols_per_exchange
            end_idx = min(start_idx + symbols_per_exchange, len(SYMBOLS))
            exchange_symbols = SYMBOLS[start_idx:end_idx]
            
            if not exchange_symbols:
                continue
            
            logger.info(f"📊 Using {exchange_name} for {len(exchange_symbols)} symbols")
            
            for symbol in exchange_symbols:
                try:
                    signal_found = await self.scan_symbol(symbol, exchange_class)
                    if signal_found:
                        # Wait a bit after sending signal
                        await asyncio.sleep(2)
                except Exception as e:
                    logger.error(f"Error processing {symbol}: {e}")
                
                # Small delay between symbols
                await asyncio.sleep(0.5)
        
        logger.info("✅ Scan completed")
    
    async def run(self):
        """Main scanner loop"""
        self.running = True
        logger.info("🚀 Signal Scanner started successfully!")
        
        scan_count = 0
        while self.running:
            try:
                scan_count += 1
                logger.info(f"🔄 Scan #{scan_count}")
                
                await self.run_scan()
                
                # Wait for next scan interval
                for _ in range(SCAN_INTERVAL):
                    if not self.running:
                        break
                    await asyncio.sleep(1)
                    
            except Exception as e:
                logger.error(f"Scanner loop error: {e}")
                await asyncio.sleep(60)  # Wait 1 minute on error
    
    def stop(self):
        self.running = False
        logger.info("🛑 Scanner stopped")

# ==================== TELEGRAM HANDLERS ====================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    added = storage.add_user(user.id, user.username or user.first_name)
    
    if added:
        welcome_msg = """🚀 **SIGNAL TRADING BOT**

✅ Đăng ký thành công!

📊 **Tôi sẽ gửi tín hiệu tự động cho 15 coins:**
BTC, ETH, SOL, LINK, DOGE, XRP, ETC, LTC, BCH, BNB, ADA, XMR, DASH, ZEC, AVAX

⏰ **Quét mỗi 5 phút, 24/7**
🎯 **Physics Momentum Algorithm**
⚡ **Sử dụng đa sàn: Binance, Bybit, Bitget, OKX**

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
    else:
        welcome_msg = """✅ Bạn đã đăng ký rồi!

Bot sẽ tiếp tục gửi tín hiệu tự động khi phát hiện cơ hội.

Sử dụng /help để xem hướng dẫn
Sử dụng /stats để xem thống kê"""
    
    await update.message.reply_text(welcome_msg, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_text = """📖 **HƯỚNG DẪN SỬ DỤNG**

🤖 **Cách hoạt động:**
• Bot tự động quét 15 coins mỗi 5 phút
• Khi có tín hiệu, gửi ngay cho tất cả user
• Không cần thiết lập gì thêm

📊 **Coins được theo dõi:**
BTC, ETH, SOL, LINK, DOGE, XRP, ETC, LTC, BCH, BNB, ADA, XMR, DASH, ZEC, AVAX

⚡ **Lệnh có sẵn:**
/start - Đăng ký nhận tín hiệu
/help - Hiển thị hướng dẫn này
/stats - Xem thống kê bot

🎯 **Quản lý rủi ro:**
• Mỗi lệnh chỉ risk 2-3% tài khoản
• Stop Loss bắt buộc phải đặt
• Dừng giao dịch sau 3 lệnh thắng
• Bot chỉ để tham khảo, tự chịu trách nhiệm

💡 **Mẹo:**
• Chờ xác nhận thêm từ khung thời gian cao hơn
• Kết hợp với phân tích cơ bản
• Không FOMO, tuân thủ kỷ luật

Chúc bạn trade thành công! 💪"""
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stats command"""
    stats = storage.get_stats()
    users = storage.get_active_users()
    
    stats_text = f"""📊 **THỐNG KÊ HỆ THỐNG**

👥 **Người dùng:**
• Tổng: {stats['total_users']} user
• Đang hoạt động: {stats['active_users']} user
• Tín hiệu đã gửi: {stats['total_signals']}

⚙️ **Hệ thống:**
• Số sàn sử dụng: {len(EXCHANGES)}
• Coins theo dõi: {len(SYMBOLS)}
• Quét mỗi: 5 phút
• Uptime: 24/7

🎯 **Coins đang scan:**
{', '.join([s.replace('/USDT', '') for s in SYMBOLS])}

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

# ==================== MAIN FUNCTION ====================
def main():
    """Start the bot"""
    logger.info("🚀 Starting Signal Trading Bot...")
    
    # Create Telegram application
    telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Add handlers
    telegram_app.add_handler(CommandHandler("start", start_command))
    telegram_app.add_handler(CommandHandler("help", help_command))
    telegram_app.add_handler(CommandHandler("stats", stats_command))
    telegram_app.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    
    # Create scanner
    scanner = SignalScanner(telegram_app)
    
    # Run Telegram bot in background thread
    def run_telegram():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def start_all():
            await telegram_app.initialize()
            await telegram_app.start()
            await telegram_app.updater.start_polling()
            
            # Start scanner
            await scanner.run()
        
        try:
            loop.run_until_complete(start_all())
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            scanner.stop()
        except Exception as e:
            logger.error(f"Telegram thread error: {e}")
    
    # Start Telegram thread
    telegram_thread = threading.Thread(target=run_telegram, daemon=True)
    telegram_thread.start()
    
    logger.info(f"🤖 Bot started with token: {TELEGRAM_TOKEN[:10]}...")
    logger.info(f"🌐 Web dashboard: http://0.0.0.0:{PORT}")
    logger.info(f"🔍 Scanning {len(SYMBOLS)} coins every {SCAN_INTERVAL//60} minutes")
    
    # Start Flask app (main thread)
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)

if __name__ == "__main__":
    main()
