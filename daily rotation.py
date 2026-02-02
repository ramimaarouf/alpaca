

import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import alpaca_trade_api as tradeapi
import numpy as np

try:
    import config
    USE_CONFIG = True
except ImportError:
    USE_CONFIG = False


class DailyRotationLongShortBot:
    def __init__(self, api_key: str, secret_key: str, base_url: str = 'https://paper-api.alpaca.markets'):
        """
        Initialize the trading bot with Alpaca credentials
        
        Args:
            api_key: Alpaca API key
            secret_key: Alpaca secret key
            base_url: API endpoint (default is paper trading)
        """
        self.api = tradeapi.REST(api_key, secret_key, base_url, api_version='v2')
        
      
        if USE_CONFIG:
            self.watchlist = config.WATCHLIST
            self.store_file = config.STORE_FILE
        else:
            self.watchlist = ['TQQQ', 'SOXL', 'UPRO', 'BTC-USD']
            self.store_file = 'bot_store.json'
        
      
        if USE_CONFIG:
            self.params = {
                'SMA_FAST': config.SMA_FAST,
                'SMA_SLOW': config.SMA_SLOW,
                'ROC': config.ROC_PERIOD,
                'TOP_LONGS': config.TOP_LONGS,
                'BOTTOM_SHORTS': config.BOTTOM_SHORTS,
                'TAKE_PROFIT_PCT': config.TAKE_PROFIT_PCT,
                'MAX_TRADES_PER_DAY': config.MAX_TRADES_PER_DAY,
                'COOLDOWN_DAYS': config.COOLDOWN_DAYS,
                'MAX_POSITION_PCT': config.MAX_POSITION_PCT,
                'MAX_GROSS_EXPOSURE': config.MAX_GROSS_EXPOSURE
            }
        else:
            self.params = {
                'SMA_FAST': 20,
                'SMA_SLOW': 50,
                'ROC': 10,
                'TOP_LONGS': 2,
                'BOTTOM_SHORTS': 1,
                'TAKE_PROFIT_PCT': 0.10,
                'MAX_TRADES_PER_DAY': 10,
                'COOLDOWN_DAYS': 2,
                'MAX_POSITION_PCT': 0.30,
                'MAX_GROSS_EXPOSURE': 1.5
            }
        
      
        self.store = {}
        self.load_store()
        
    def load_store(self):
        """Load stored data from file if exists"""
        if os.path.exists(self.store_file):
            try:
                with open(self.store_file, 'r') as f:
                    self.store = json.load(f)
                print("Loaded existing store data")
            except Exception as e:
                print(f"Error loading store: {e}")
                self.store = {}
    
    def save_store(self):
        """Save store data to file"""
        try:
            with open(self.store_file, 'w') as f:
                json.dump(self.store, f, indent=2)
        except Exception as e:
            print(f"Error saving store: {e}")
    
    def log(self, message: str):
        """Log a message with timestamp"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{timestamp}] {message}")
    
    def init_record(self) -> Dict:
        """Initialize a new record for a symbol"""
        return {
            'prices': [],
            'indicators': {},
            'score': -999,
            'last_close_date': None,
            'last_trade_date': None
        }
    
    def get_latest_close(self, symbol: str) -> Optional[float]:
        """Fetch the latest closing price for a symbol"""
        try:
           
            barset = self.api.get_bars(
                symbol,
                tradeapi.TimeFrame.Day,
                limit=1
            ).df
            
            if barset.empty:
                return None
            
            return float(barset['close'].iloc[-1])
        except Exception as e:
            self.log(f"Error fetching data for {symbol}: {e}")
            return None
    
    def get_historical_prices(self, symbol: str, days: int = 120) -> List[float]:
        """Fetch historical closing prices"""
        try:
            end = datetime.now()
            start = end - timedelta(days=days * 2)  
            
            barset = self.api.get_bars(
                symbol,
                tradeapi.TimeFrame.Day,
                start=start.strftime('%Y-%m-%d'),
                end=end.strftime('%Y-%m-%d')
            ).df
            
            if barset.empty:
                return []
            
            return barset['close'].tolist()[-days:]
        except Exception as e:
            self.log(f"Error fetching historical data for {symbol}: {e}")
            return []
    
    def calculate_indicators(self, prices: List[float]) -> Dict:
        """Calculate technical indicators"""
        if len(prices) < self.params['SMA_SLOW']:
            return None
        
        sma_fast = np.mean(prices[-self.params['SMA_FAST']:])
        sma_slow = np.mean(prices[-self.params['SMA_SLOW']:])
        
        roc_idx = -self.params['ROC'] - 1
        if abs(roc_idx) > len(prices):
            roc = 0
        else:
            roc = (prices[-1] - prices[roc_idx]) / prices[roc_idx]
        
        score = 0
        if prices[-1] > sma_slow:
            score += 2
        if sma_fast > sma_slow:
            score += 1
        if roc > 0:
            score += 1
        
        return {
            'sma_fast': sma_fast,
            'sma_slow': sma_slow,
            'roc': roc,
            'score': score
        }
    
    def in_cooldown(self, symbol: str, today: str) -> bool:
        """Check if symbol is in cooldown period"""
        if symbol not in self.store:
            return False
        
        last_trade = self.store[symbol].get('last_trade_date')
        if not last_trade:
            return False
        
        try:
            last_trade_dt = datetime.strptime(last_trade, '%Y-%m-%d')
            today_dt = datetime.strptime(today, '%Y-%m-%d')
            days_since = (today_dt - last_trade_dt).days
            return days_since < self.params['COOLDOWN_DAYS']
        except:
            return False
    
    def get_portfolio_value(self) -> float:
        """Get total portfolio value"""
        try:
            account = self.api.get_account()
            return float(account.portfolio_value)
        except Exception as e:
            self.log(f"Error getting portfolio value: {e}")
            return 0
    
    def get_positions(self) -> Dict:
        """Get current positions as a dictionary"""
        positions = {}
        try:
            for position in self.api.list_positions():
                side = 'LONG' if float(position.qty) > 0 else 'SHORT'
                positions[position.symbol] = {
                    'side': side,
                    'shares': abs(float(position.qty)),
                    'entry_price': float(position.avg_entry_price),
                    'entry_date': None  
                }
        except Exception as e:
            self.log(f"Error getting positions: {e}")
        
        return positions
    
    def close_position(self, symbol: str):
        """Close a position"""
        try:
            self.api.close_position(symbol)
            self.log(f"Closed position: {symbol}")
        except Exception as e:
            self.log(f"Error closing {symbol}: {e}")
    
    def open_long(self, symbol: str, shares: int):
        """Open a long position"""
        try:
            self.api.submit_order(
                symbol=symbol,
                qty=shares,
                side='buy',
                type='market',
                time_in_force='day'
            )
            self.log(f"Opened LONG: {symbol} x {shares}")
        except Exception as e:
            self.log(f"Error opening long {symbol}: {e}")
    
    def open_short(self, symbol: str, shares: int):
        """Open a short position"""
        try:
            self.api.submit_order(
                symbol=symbol,
                qty=shares,
                side='sell',
                type='market',
                time_in_force='day'
            )
            self.log(f"Opened SHORT: {symbol} x {shares}")
        except Exception as e:
            self.log(f"Error opening short {symbol}: {e}")
    
    def calculate_position_size(self, symbol: str, portfolio_value: float) -> int:
        """Calculate position size based on max position percentage"""
        try:
            price = self.store[symbol]['prices'][-1]
            max_value = portfolio_value * self.params['MAX_POSITION_PCT']
            shares = int(max_value / price)
            return max(shares, 0)
        except Exception as e:
            self.log(f"Error calculating position size for {symbol}: {e}")
            return 0
    
    def check_exposure_limits(self, positions: Dict) -> bool:
        """Check if we're within exposure limits"""
        try:
            account = self.api.get_account()
            portfolio_value = float(account.portfolio_value)
            
            total_long = 0
            total_short = 0
            
            for pos in positions.values():
                if pos['side'] == 'LONG':
                    total_long += pos['shares'] * pos['entry_price']
                else:
                    total_short += pos['shares'] * pos['entry_price']
            
            gross_exposure = (total_long + total_short) / portfolio_value
            
            return gross_exposure < self.params['MAX_GROSS_EXPOSURE']
        except Exception as e:
            self.log(f"Error checking exposure: {e}")
            return True
    
    def run_daily(self):
        """Main daily execution function"""
        trades_today = 0
        today = datetime.now().strftime('%Y-%m-%d')
        
        self.log("=" * 60)
        self.log(f"RUN START: {today}")
        self.log("=" * 60)
        
        self.log("Fetching latest prices...")
        for symbol in self.watchlist:
            bar = self.get_latest_close(symbol)
            
            if bar is None:
                self.log(f"{symbol}: missing data -> skip")
                continue
            
            if symbol not in self.store:
                self.store[symbol] = self.init_record()
                historical = self.get_historical_prices(symbol, 120)
                if historical:
                    self.store[symbol]['prices'] = historical
            
            self.store[symbol]['prices'].append(bar)
            self.store[symbol]['prices'] = self.store[symbol]['prices'][-120:]  # Keep last 120
            self.store[symbol]['last_close_date'] = today
            
            self.log(f"{symbol}: ${bar:.2f}")
        
        self.log("\nCalculating indicators and scores...")
        for symbol in self.watchlist:
            if symbol not in self.store:
                continue
                
            prices = self.store[symbol]['prices']
            
            if len(prices) < self.params['SMA_SLOW']:
                self.store[symbol]['score'] = -999
                self.log(f"{symbol}: not enough data -> score invalid")
                continue
            
            indicators = self.calculate_indicators(prices)
            if indicators:
                self.store[symbol]['indicators'] = {
                    'sma_fast': indicators['sma_fast'],
                    'sma_slow': indicators['sma_slow'],
                    'roc': indicators['roc']
                }
                self.store[symbol]['score'] = indicators['score']
                self.log(f"{symbol}: score={indicators['score']}, ROC={indicators['roc']:.2%}")
        
        ranked = sorted(
            [(s, self.store[s]['score']) for s in self.watchlist if s in self.store],
            key=lambda x: x[1],
            reverse=True
        )
        
        self.log(f"\nRanking: {[(s, score) for s, score in ranked]}")
        
        top_longs = [s for s, _ in ranked[:self.params['TOP_LONGS']]]
        bottom_shorts = [s for s, _ in ranked[-self.params['BOTTOM_SHORTS']:]]
        
        self.log(f"Target LONGS: {top_longs}")
        self.log(f"Target SHORTS: {bottom_shorts}")
        
        target = {}
        for s in top_longs:
            target[s] = 'LONG'
        for s in bottom_shorts:
            target[s] = 'SHORT'
        
        positions = self.get_positions()
        self.log(f"\nCurrent positions: {list(positions.keys())}")
        
        self.log("\nChecking take-profit conditions...")
        for symbol in list(positions.keys()):
            pos = positions[symbol]
            price = self.store.get(symbol, {}).get('prices', [None])[-1]
            
            if price is None:
                continue
            
            if pos['side'] == 'LONG' and price >= pos['entry_price'] * (1 + self.params['TAKE_PROFIT_PCT']):
                self.close_position(symbol)
                self.store[symbol]['last_trade_date'] = today
                trades_today += 1
                self.log(f"{symbol}: CLOSE LONG (take-profit, +{self.params['TAKE_PROFIT_PCT']:.0%})")
                del positions[symbol]
                
            elif pos['side'] == 'SHORT' and price <= pos['entry_price'] * (1 - self.params['TAKE_PROFIT_PCT']):
                self.close_position(symbol)
                self.store[symbol]['last_trade_date'] = today
                trades_today += 1
                self.log(f"{symbol}: CLOSE SHORT (take-profit, +{self.params['TAKE_PROFIT_PCT']:.0%})")
                del positions[symbol]
        
        self.log("\nRotating out of non-target positions...")
        for symbol in list(positions.keys()):
            if symbol not in target and trades_today < self.params['MAX_TRADES_PER_DAY']:
                if not self.in_cooldown(symbol, today):
                    self.close_position(symbol)
                    self.store[symbol]['last_trade_date'] = today
                    trades_today += 1
                    self.log(f"{symbol}: CLOSE (not in target)")
                    del positions[symbol]
                else:
                    self.log(f"{symbol}: in cooldown, keeping position")
        
        self.log("\nOpening new target positions...")
        portfolio_value = self.get_portfolio_value()
        
        for symbol in target:
            if trades_today >= self.params['MAX_TRADES_PER_DAY']:
                self.log("Max trades per day reached, stopping")
                break
            
            if symbol in positions:
                continue
            
            if self.in_cooldown(symbol, today):
                self.log(f"{symbol}: cooldown -> no open")
                continue
            
            if not self.check_exposure_limits(positions):
                self.log("Exposure limits hit -> stop opening")
                break
            
            shares = self.calculate_position_size(symbol, portfolio_value)
            
            if shares <= 0:
                self.log(f"{symbol}: size too small -> skip")
                continue
            
            if target[symbol] == 'LONG':
                self.open_long(symbol, shares)
                self.store[symbol]['last_trade_date'] = today
                trades_today += 1
                
            elif target[symbol] == 'SHORT':
                self.open_short(symbol, shares)
                self.store[symbol]['last_trade_date'] = today
                trades_today += 1
        
        final_positions = self.get_positions()
        self.log("\n" + "=" * 60)
        self.log(f"Trades today: {trades_today}")
        self.log(f"Final holdings: {list(final_positions.keys())}")
        self.log(f"Portfolio value: ${portfolio_value:,.2f}")
        self.log("=" * 60)
        self.log("RUN END")
        
        self.save_store()


def main():
    """Main entry point"""
    if USE_CONFIG and config.ALPACA_API_KEY:
        API_KEY = config.ALPACA_API_KEY
        SECRET_KEY = config.ALPACA_SECRET_KEY
    else:
        API_KEY = os.getenv('APCA_API_KEY_ID', 'YOUR_API_KEY')
        SECRET_KEY = os.getenv('APCA_API_SECRET_KEY', 'YOUR_SECRET_KEY')
    
    if API_KEY == 'YOUR_API_KEY' or SECRET_KEY == 'YOUR_SECRET_KEY':
        print("ERROR: Please set your Alpaca API credentials!")
        print("You can either:")
        print("  1. Edit config.py and add your keys")
        print("  2. Set environment variables APCA_API_KEY_ID and APCA_API_SECRET_KEY")
        return
    
    bot = DailyRotationLongShortBot(API_KEY, SECRET_KEY)
    
    bot.run_daily()


if __name__ == '__main__':
    main()