import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime

# Initialize session state
def initialize_session():
    if 'players' not in st.session_state:
        st.session_state.players = {}

# Function to add a new player
def add_new_player():
    player_name = st.text_input("Enter your name to join:")
    if st.button("Join League") and player_name:
        if player_name not in st.session_state.players:
            st.session_state.players[player_name] = {
                'portfolio_value': 100000,
                'trades': [],
                'score': 0
            }
            st.success(f"{player_name} joined the league!")
        else:
            st.warning("Player already exists!")

# Function to get stock price
def get_stock_price(stock_name):
    try:
        stock_data = yf.Ticker(stock_name).history(period='1d')
        return stock_data['Close'].iloc[-1] if not stock_data.empty else None
    except:
        return None

# Basic scoring functions - these need to be defined before they're used
def calculate_portfolio_score(player):
    initial_portfolio_value = 100000
    return ((player['portfolio_value'] - initial_portfolio_value) / initial_portfolio_value) * 100

def calculate_overtrading_penalty(player):
    return 5 if len(player['trades']) > 20 else 0

def calculate_reckless_investing_penalty(player):
    large_trades = [trade for trade in player['trades'] if trade['shares'] * trade['price'] > 50000]
    return min(len(large_trades), 2) * 3

def calculate_diversification_bonus(player):
    return 5 if len(set(trade['stock'] for trade in player['trades'])) >= 5 else 0

def get_day_trades(player):
    day_trades = {}
    for trade in player['trades']:
        if trade['type'] == "Sell":
            date = trade['date']
            stock = trade['stock']
            
            # Find buy trades for the same stock on the same day
            buy_trades = [t for t in player['trades'] 
                         if t['stock'] == stock 
                         and t['type'] == "Buy" 
                         and t['date'] == date]
            
            if buy_trades:
                if date not in day_trades:
                    day_trades[date] = {}
                if stock not in day_trades[date]:
                    day_trades[date][stock] = 0
                day_trades[date][stock] += len(buy_trades)
    
    return day_trades

def calculate_day_trading_penalty(player):
    day_trades = get_day_trades(player)
    penalty = sum(len(stocks) * 5 for stocks in day_trades.values())
    return penalty

def calculate_market_performance_bonus(player):
    try:
        portfolio_change_percentage = calculate_portfolio_score(player)
        market_data = yf.Ticker("^GSPC").history(period='1d')
        if not market_data.empty:
            sp500_price = market_data['Close'].iloc[-1]
            sp500_prev_price = market_data['Open'].iloc[0]
            market_change_percentage = ((sp500_price - sp500_prev_price) / sp500_prev_price) * 100
            return 10 if portfolio_change_percentage > market_change_percentage else -5
    except:
        pass
    return 0

def apply_penalties(player):
    score = calculate_portfolio_score(player)
    score -= calculate_overtrading_penalty(player)
    score -= calculate_reckless_investing_penalty(player)
    score -= calculate_day_trading_penalty(player)
    score += calculate_diversification_bonus(player)
    score += calculate_market_performance_bonus(player)
    return max(0, score)

# Function to process a sell trade
def process_sell_trade(player, stock_name, shares, entry_time, stock_price):
    available_shares = sum(t['shares'] for t in player['trades'] 
                         if t['stock'] == stock_name and t['type'] == 'Buy' and t['exit_time'] is None)
    
    if shares > available_shares:
        st.error(f"You only have {available_shares} shares available to sell")
        return
    
    trade_amount = shares * stock_price
    shares_to_sell = shares
    
    for t in player['trades']:
        if (t['stock'] == stock_name and t['type'] == 'Buy' and 
            t['exit_time'] is None and shares_to_sell > 0):
            shares_sold = min(shares_to_sell, t['shares'])
            t['exit_time'] = entry_time
            t['time_diff'] = entry_time - t['entry_time']
            shares_to_sell -= shares_sold
    
    player['portfolio_value'] += trade_amount
    
    # Add sell trade to history
    trade = {
        "stock": stock_name,
        "type": "Sell",
        "shares": shares,
        "price": stock_price,
        "entry_time": entry_time,
        "exit_time": None,
        "time_diff": None,
        "date": entry_time.date()
    }
    player['trades'].append(trade)
    
    st.success(f"Sell order recorded: {shares} shares of {stock_name} at ${stock_price:.2f}")

# Function to execute a trade
def execute_trade(player, stock_name, trade_type, shares):
    stock_price = get_stock_price(stock_name)
    if stock_price is None:
        st.error("Could not fetch stock data. Please check the ticker symbol.")
        return
    
    trade_amount = shares * stock_price
    entry_time = pd.Timestamp.now()

    if trade_type == "Buy":
        if trade_amount > player['portfolio_value']:
            st.error("Insufficient funds for this trade!")
            return
        
        trade = {
            "stock": stock_name,
            "type": trade_type,
            "shares": shares,
            "price": stock_price,
            "entry_time": entry_time,
            "exit_time": None,
            "time_diff": None,
            "date": entry_time.date()
        }
        player['trades'].append(trade)
        player['portfolio_value'] -= trade_amount
        st.success(f"Buy order recorded: {shares} shares of {stock_name} at ${stock_price:.2f}")
    
    elif trade_type == "Sell":
        process_sell_trade(player, stock_name, shares, entry_time, stock_price)

# Function to display the player's portfolio
def display_portfolio(player):
    st.subheader("Portfolio Summary")
    st.write(f"Portfolio Value: ${player['portfolio_value']:,.2f}")
    
    # Display day trading activity
    day_trades = get_day_trades(player)
    if day_trades:
        st.subheader("⚠️ Day Trading Activity")
        st.write("Same-day buy and sell transactions:")
        for date, stocks in day_trades.items():
            st.write(f"Date: {date}")
            for stock, trades in stocks.items():
                st.write(f"- {stock}: {trades} trades")
        
        penalty = calculate_day_trading_penalty(player)
        st.write(f"Day Trading Penalty: -{penalty} points")
    
    if player['trades']:
        st.subheader("Trade History")
        trades_df = pd.DataFrame(player['trades'])
        trades_df['time_diff'] = trades_df['time_diff'].astype(str)
        st.dataframe(trades_df)

# Display leaderboard function
def display_leaderboard():
    st.subheader("🏅 Leaderboard")
    if not st.session_state.players:
        st.write("No players yet.")
        return

    leaderboard = pd.DataFrame(
        [(name, data['score'], data['portfolio_value']) 
         for name, data in st.session_state.players.items()],
        columns=["Player", "Score", "Portfolio Value"]
    ).sort_values(by="Score", ascending=False)
    
    st.dataframe(leaderboard)

# Function to display stock history graph
def display_stock_history(stock_name):
    if stock_name:
        try:
            stock_data = yf.Ticker(stock_name).history(period='1mo')
            if not stock_data.empty:
                st.subheader(f"Stock Price History for {stock_name}")
                st.line_chart(stock_data['Close'])
            else:
                st.error("Could not fetch stock history.")
        except:
            st.error("Error fetching stock data. Please check the ticker symbol.")

# Main function
def main():
    initialize_session()
    st.title("Fantasy Stock League 🏆")
    add_new_player()
    
    if st.session_state.players:
        selected_player = st.selectbox("Select Player:", list(st.session_state.players.keys()))
        if selected_player:
            player = st.session_state.players[selected_player]
            stock_name = st.text_input("Stock Ticker (e.g., AAPL, TSLA):")
            trade_type = st.selectbox("Trade Type:", ["Buy", "Sell"])
            shares = st.number_input("Number of Shares:", min_value=1, step=1)

            # Display stock history chart above submit button
            display_stock_history(stock_name)

            if st.button("Submit Trade") and stock_name:
                execute_trade(player, stock_name, trade_type, shares)
            
            display_portfolio(player)
            player['score'] = apply_penalties(player)
            st.write(f"Fantasy Score: {player['score']:.2f}")

    display_leaderboard()

if __name__ == "__main__":
    main()