

import os
try:
    import config
    USE_CONFIG = True
except ImportError:
    USE_CONFIG = False

try:
    import alpaca_trade_api as tradeapi
except ImportError:
    print("ERROR: alpaca-trade-api not installed!")
    print("Run: pip install -r requirements.txt")
    exit(1)


def test_connection():
    """Test Alpaca API connection"""
    
    if USE_CONFIG and hasattr(config, 'ALPACA_API_KEY') and config.ALPACA_API_KEY:
        api_key = config.ALPACA_API_KEY
        secret_key = config.ALPACA_SECRET_KEY
        print("✓ Using credentials from config.py")
    else:
        api_key = os.getenv('APCA_API_KEY_ID', '')
        secret_key = os.getenv('APCA_API_SECRET_KEY', '')
        if api_key and secret_key:
            print("✓ Using credentials from environment variables")
        else:
            print("✗ No credentials found!")
            print("\nPlease either:")
            print("  1. Edit config.py and add your API keys")
            print("  2. Set environment variables APCA_API_KEY_ID and APCA_API_SECRET_KEY")
            return False
    
    print("\nTesting connection to Alpaca Paper Trading...")
    try:
        api = tradeapi.REST(
            api_key,
            secret_key,
            'https://paper-api.alpaca.markets',
            api_version='v2'
        )
        
        account = api.get_account()
        
        print("✓ Connection successful!")
        print(f"\nAccount Status: {account.status}")
        print(f"Buying Power: ${float(account.buying_power):,.2f}")
        print(f"Portfolio Value: ${float(account.portfolio_value):,.2f}")
        print(f"Cash: ${float(account.cash):,.2f}")
        
        print("\nTesting data fetch for TQQQ...")
        bars = api.get_bars('TQQQ', tradeapi.TimeFrame.Day, limit=1).df
        if not bars.empty:
            price = bars['close'].iloc[-1]
            print(f"✓ Latest TQQQ price: ${price:.2f}")
        else:
            print("✗ Could not fetch TQQQ data")
            return False
        
        print("\n" + "="*50)
        print("All tests passed! You're ready to run the bot.")
        print("="*50)
        print("\nNext step: python daily_rotation_bot.py")
        return True
        
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        print("\nPossible issues:")
        print("  - Invalid API keys")
        print("  - Using live trading keys instead of paper trading")
        print("  - Network/firewall blocking connection")
        return False


if __name__ == '__main__':
    test_connection()