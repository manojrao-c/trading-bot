# 🤖 Automated Trading Agent — Complete Setup Guide
## Paper Trading (Zero Real Money) | NSE India + US Stocks

---

## ⚡ What This Agent Does

- Scans **9 US stocks** (AAPL, MSFT, GOOGL, TSLA, NVDA, META, AMZN, SPY, QQQ) every 5 minutes during NYSE hours
- Scans **8 NSE India stocks** (RELIANCE, TCS, INFY, HDFCBANK, etc.) every 5 minutes during NSE hours
- Generates BUY/SELL signals using **EMA crossover + RSI + ATR** strategy
- Applies **strict risk management** (1.5% risk per trade, kill switch, position sizing)
- Sends **Telegram alerts** for every signal and trade
- Shows a **live terminal dashboard** with P&L, positions, and signals
- Runs on **100% free infrastructure** — zero real money risk

---

## 📋 PHASE 1 — Install on Your Computer (30 minutes)

### Step 1 — Install Python

**Windows:**
1. Go to https://python.org/downloads
2. Download Python 3.11 or 3.12
3. ✅ CHECK "Add Python to PATH" during install
4. Open Command Prompt and verify: `python --version`

**Mac:**
```bash
# Install Homebrew first (if not installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Then install Python
brew install python@3.11
python3 --version
```

**Linux/Ubuntu:**
```bash
sudo apt update && sudo apt install python3.11 python3-pip python3-venv -y
python3 --version
```

---

### Step 2 — Download the Agent

Open your terminal / Command Prompt and run:

```bash
# Navigate to where you want the project
cd ~/Desktop

# If you have git installed:
# (Otherwise just unzip the folder you received)

# Enter the folder
cd trading-agent

# Create a virtual environment (keeps dependencies isolated)
python -m venv venv

# Activate it:
# Windows:
venv\Scripts\activate

# Mac/Linux:
source venv/bin/activate

# Install all dependencies
pip install -r requirements.txt
```

---

### Step 3 — Set Up Alpaca (US Paper Trading) — FREE

1. Go to **https://alpaca.markets**
2. Click **Sign Up** — use your email, completely free
3. After login, click **Paper Trading** in the left sidebar
4. Click **Your API Keys** (top right)
5. Click **Regenerate** to create keys
6. Copy your:
   - **API Key ID** (looks like: `PKXXXXXXXXXXXXXXX`)
   - **Secret Key** (shown only once — save it!)

> 💡 Paper trading gives you $100,000 virtual USD to practice with. No real money ever.

---

### Step 4 — Set Up Telegram Bot — FREE

**Create your bot:**
1. Open Telegram and search for **@BotFather**
2. Send: `/newbot`
3. Enter a name: `My Trading Agent`
4. Enter a username: `mytrading_YOURNAME_bot`
5. Copy the **token** (looks like: `7123456789:AAHxxxxxxxxxxx`)

**Get your Chat ID:**
1. Search for **@userinfobot** on Telegram
2. Send `/start`
3. Copy your **Id** number (looks like: `987654321`)

---

### Step 5 — Configure the Agent

```bash
# Copy the template
cp config/.env.template config/.env

# Open and edit it
# Windows:
notepad config/.env

# Mac/Linux:
nano config/.env
```

Fill in your values:
```
ALPACA_API_KEY=PKXXXXXXXXXXXXXXX
ALPACA_SECRET_KEY=your_secret_key_here
TELEGRAM_BOT_TOKEN=7123456789:AAHxxxxxxxxxxx
TELEGRAM_CHAT_ID=987654321
```

**Save the file.** Leave everything else at defaults for now.

---

### Step 6 — Test the Setup

```bash
# Make sure your venv is active, then:

# Test 1: Run a backtest on AAPL (no API keys needed)
python backtest.py --market US --symbol AAPL --period 180d

# You should see a table with backtest results.
# If it errors, check: pip install -r requirements.txt

# Test 2: Run a single scan cycle
python main.py --once

# Test 3: Check portfolio summary
python main.py --summary
```

---

## 📋 PHASE 2 — Run the Agent (5 minutes)

### Start the Agent

```bash
# Make sure venv is activated, then:
python main.py
```

You'll see:
- Live terminal dashboard refreshing every 5 minutes
- Signals printed as they're detected
- Telegram messages arriving on your phone
- P&L tracking automatically

**Stop the agent:** Press `Ctrl + C`
- It will send a daily summary to Telegram before stopping

---

## 📋 PHASE 3 — Run on Free Cloud (Optional, 1 hour)

So the agent runs 24/7 without your computer being on.

### Option A: Railway.app (Easiest, Free tier)

1. Go to **https://railway.app** — sign up with GitHub
2. Click **New Project → Deploy from GitHub**
3. Push your trading-agent folder to a GitHub repo first:
   ```bash
   git init
   git add .
   git commit -m "Trading agent"
   git remote add origin https://github.com/YOURUSERNAME/trading-agent.git
   git push -u origin main
   ```
4. In Railway, select your repo
5. Add environment variables (Settings → Variables):
   - Add all the values from your `.env` file
6. Railway auto-deploys. Free tier = 500 hours/month ✅

### Option B: Google Cloud Run (Free tier)

Google gives 2 million free requests/month. Too technical for beginners — use Railway first.

### Option C: Your own machine with auto-start

**Windows:** Create a Task Scheduler task to run `python main.py` on login
**Mac:** Create a launchd plist
**Linux:** Add a cron job:
```bash
# Run at 9am IST (3:30am UTC) Monday-Friday
30 3 * * 1-5 cd /path/to/trading-agent && source venv/bin/activate && python main.py >> logs/cron.log 2>&1
```

---

## 📋 PHASE 4 — Backtesting Your Strategy (Before Trusting It)

Run backtests BEFORE trusting the agent with real money:

```bash
# Backtest single stock
python backtest.py --market US --symbol AAPL --period 180d
python backtest.py --market NSE --symbol RELIANCE --period 180d

# Backtest full watchlist
python backtest.py --market US --all --period 180d
python backtest.py --market NSE --all --period 180d
```

**What to look for in results:**
| Metric         | Acceptable | Good    | Excellent |
|----------------|------------|---------|-----------|
| Win Rate       | > 40%      | > 50%   | > 60%     |
| Profit Factor  | > 1.2      | > 1.5   | > 2.0     |
| Return %       | > 5%       | > 15%   | > 30%     |

> ⚠️ Only move to real money if backtests AND 60 days of paper trading BOTH show profit.

---

## 📋 PHASE 5 — Going Live with Real Money (When Ready)

### US Stocks — Alpaca Live
1. In Alpaca dashboard, switch from **Paper** to **Live**
2. Fund with minimum $100 USD
3. Change in your `.env`:
   ```
   ALPACA_BASE_URL=https://api.alpaca.markets
   ```
4. Replace paper API keys with live API keys
5. Start small: risk only what you can afford to lose entirely

### NSE India — Zerodha Kite
1. Open Zerodha account at **https://zerodha.com** (free, takes 2-3 days)
2. Subscribe to **Kite Connect API** (₹2000/month, or free for retail via Kite web)
3. Install: `pip install kiteconnect`
4. Replace `NSEPaperBroker` with Zerodha's `KiteConnect` client
5. Full Zerodha API docs: https://kite.trade/docs/

---

## 🛡️ Risk Management Rules (Built In)

The agent enforces these automatically — do not disable them:

| Rule                    | Default | What It Does                              |
|-------------------------|---------|-------------------------------------------|
| Risk per trade          | 1.5%    | Never risks more than 1.5% of capital     |
| Max trades/day          | 10      | Stops trading after 10 trades             |
| Daily loss kill switch  | 3%      | Halts ALL trading if daily loss hits 3%   |
| Min reward:risk ratio   | 2:1     | Only takes trades where target ≥ 2× stop  |
| ATR-based stops         | 2× ATR  | Stop losses adapt to market volatility    |

---

## 🔧 Customising the Agent

### Change which stocks to watch
Edit `config/.env`:
```
US_WATCHLIST=AAPL,NVDA,AMD,SOFI,PLTR
NSE_WATCHLIST=RELIANCE,TCS,TITAN,BAJAJ-AUTO,ONGC
```

### Change scan frequency
In `main.py`, find:
```python
time.sleep(300)  # 5 minutes
```
Change to `60` for 1-minute scans (more CPU usage).

### Change strategy aggressiveness
In `config/.env`:
```
RISK_PER_TRADE_PCT=1.0     # More conservative
MAX_DAILY_LOSS_PCT=2.0     # Tighter kill switch
MIN_RR_RATIO=3.0           # Only 3:1 reward:risk trades
```

---

## ❓ Troubleshooting

| Error | Fix |
|-------|-----|
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` |
| `Invalid API key` | Double-check `.env` — no spaces around `=` |
| `No data for symbol` | Yahoo Finance may be rate-limiting. Wait 1 min. |
| `Market closed` | Normal! Agent skips scans when market is closed |
| Telegram not sending | Verify token and chat ID. Start chat with your bot first. |
| `Insufficient data` | Normal for new symbols — needs 55+ candles to signal |

---

## 📁 File Structure

```
trading-agent/
├── main.py              ← Start here. Runs the agent.
├── backtest.py          ← Test strategies on historical data
├── requirements.txt     ← Python dependencies
├── config/
│   ├── .env.template    ← Copy to .env and fill in your keys
│   └── settings.py      ← Loads all config
├── strategies/
│   └── signal_engine.py ← EMA + RSI + ATR signal logic
├── brokers/
│   ├── alpaca_broker.py ← US stocks (Alpaca paper)
│   └── nse_broker.py    ← NSE India (paper simulator)
├── risk/
│   └── manager.py       ← Position sizing, kill switch, P&L tracking
├── alerts/
│   └── telegram_alert.py← All Telegram notifications
├── dashboard/
│   └── terminal.py      ← Live terminal display
└── logs/                ← Auto-created. Trade logs saved here.
```

---

## 🗓️ Recommended Timeline

| Week | Action |
|------|--------|
| Week 1 | Install, configure, run backtests on all watchlist symbols |
| Week 2 | Start paper trading. Watch Telegram alerts. Don't intervene. |
| Week 3-4 | Review signals. Are they making sense? Adjust watchlist if needed. |
| Month 2 | If paper P&L is consistently positive → consider small real capital |
| Month 3+ | Scale gradually. Add more symbols. Tune parameters. |

---

> 💬 **Questions?** Share your backtest results and I can help tune the strategy for better performance on your specific watchlist.
