#!/bin/bash
# Install all dependencies into the Python 3.10 venv.
# Run once before the first paper trading session.
#
# Usage:
#   chmod +x setup.sh
#   ./setup.sh

set -e
cd "$(dirname "$0")"

echo "==> Activating venv..."
source venv/bin/activate

echo "==> Installing tradingagents and its dependencies..."
pip install -e ../tradingagents/ --quiet

echo "==> Installing spy_trading extras..."
pip install \
    python-dotenv \
    rich \
    pytz \
    requests \
    praw \
    --quiet

echo ""
echo "✓ Setup complete."
echo ""
echo "Next steps:"
echo "  1. Make sure .env has your API keys:"
echo "       ANTHROPIC_API_KEY (or other LLM key)"
echo "       LLM_PROVIDER=anthropic"
echo "       FRED_API_KEY"
echo "       ALPHA_VANTAGE_API_KEY"
echo ""
echo "  2. Run tomorrow during market hours (9:30 AM – 4:00 PM ET):"
echo "       source venv/bin/activate"
echo "       python paper_trade_full.py"
echo ""
echo "  3. View results any time:"
echo "       python report.py"
echo "       python report.py --trades"
