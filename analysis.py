import pandas as pd
import pandas_ta as ta
import numpy as np
from typing import Dict, Any, Optional

def ohlcv_to_df(ohlcv):
    """Convert OHLCV data to DataFrame"""
    if not ohlcv:
        return pd.DataFrame()
    
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    return df

def calculate_indicators(df: pd.DataFrame) -> Dict[str, Any]:
    """Calculate all technical indicators"""
    if df.empty or len(df) < 50:
        return {"error": "insufficient_data"}

    try:
        # RSI
        df['rsi'] = ta.rsi(df['close'], length=14)
        
        # Bollinger Bands
        bb = ta.bbands(df['close'], length=20, std=2)
        if bb is not None:
            df['bb_upper'] = bb.get('BBU_20_2.0', pd.Series(index=df.index))
            df['bb_lower'] = bb.get('BBL_20_2.0', pd.Series(index=df.index))
            df['bb_middle'] = bb.get('BBM_20_2.0', pd.Series(index=df.index))
        
        # Velocity (3-candle price change SMA)
        df['price_change'] = df['close'].pct_change() * 100
        df['velocity'] = df['price_change'].rolling(window=3, min_periods=1).mean()
        
        # Acceleration
        df['acceleration'] = df['velocity'].diff()

        # Get latest values
        latest = df.iloc[-1]
        prev = df.iloc[-2]

        return {
            "success": True,
            "rsi": float(latest['rsi']) if pd.notna(latest['rsi']) else 50,
            "bb_upper": float(latest['bb_upper']) if pd.notna(latest['bb_upper']) else latest['close'] * 1.1,
            "bb_lower": float(latest['bb_lower']) if pd.notna(latest['bb_lower']) else latest['close'] * 0.9,
            "close": float(latest['close']),
            "velocity": float(latest['velocity']) if pd.notna(latest['velocity']) else 0,
            "acceleration": float(latest['acceleration']) if pd.notna(latest['acceleration']) else 0,
            "prev_velocity": float(prev['velocity']) if pd.notna(prev['velocity']) else 0
        }
    except Exception as e:
        return {"error": str(e)}

def check_signal(indicators: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Check for trading signals based on Physics Momentum"""
    if not indicators.get("success", False):
        return None
    
    rsi = indicators['rsi']
    close = indicators['close']
    bb_lower = indicators['bb_lower']
    bb_upper = indicators['bb_upper']
    acceleration = indicators['acceleration']
    velocity = indicators['velocity']
    prev_velocity = indicators['prev_velocity']

    # LONG signal: RSI < 30, price below lower BB, acceleration > 0, velocity increasing
    long_conditions = (
        rsi < 30 and
        close < bb_lower and
        acceleration > 0 and
        velocity > prev_velocity
    )

    # SHORT signal: RSI > 70, price above upper BB, acceleration < 0, velocity decreasing
    short_conditions = (
        rsi > 70 and
        close > bb_upper and
        acceleration < 0 and
        velocity < prev_velocity
    )

    if long_conditions:
        return {
            "signal": "LONG",
            "type": "BUY",
            "entry": close,
            "strength": min(abs(30 - rsi) * 3 + abs(acceleration) * 10, 100)
        }
    elif short_conditions:
        return {
            "signal": "SHORT",
            "type": "SELL",
            "entry": close,
            "strength": min(abs(rsi - 70) * 3 + abs(acceleration) * 10, 100)
        }
    
    return None
