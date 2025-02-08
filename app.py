import streamlit as st
import pandas as pd
import yfinance as yf
import hashlib
import json
import os
from datetime import datetime

USER_DATA_FILE = 'user_data.json'

# Initialize session state
def initialize_session():
    if 'players' not in st.session_state:
        st.session_state.players = {}
    if 'current_user' not in st.session_state:
        st.session_state.current_user = None
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    if 'name_entered' not in st.session_state:
        st.session_state.name_entered = False  # Track if the user has entered their name

    # Load user data from file if it exists
    if os.path.exists(USER_DATA_FILE):
        try:
            with open(USER_DATA_FILE, 'r') as file:
                st.session_state.user_data = json.load(file)
        except json.JSONDecodeError:
            # If JSON is invalid, log the error and use an empty dictionary
            st.session_state.user_data = {}
            st.error("Error reading user data from file. Using default empty data.")
        except Exception as e:
            # Catch any other exceptions
            st.session_state.user_data = {}
            st.error(f"An error occurred: {e}")
    else:
        st.session_state.user_data = {}

    # Ensure that every user has 'portfolio_value' and 'trades'
    for user_data in st.session_state.user_data.values():
        if 'portfolio_value' not in user_data:
            user_data['portfolio_value'] = 100000  # Initialize with a default value
        if 'name' not in user_data:
            user_data['name'] = ""
        if 'trades' not in user_data:
            user_data['trades'] = []

# Save user data to file
def save_user_data():
    try:
        with open(USER_DATA_FILE, 'w') as file:
            json.dump(st.session_state.user_data, file, indent=4)  # Added indent for better readability
    except Exception as e:
        st.error(f"Error saving user data: {e}")

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

    # Initial Sign-in / Registration Page
    if not st.session_state.authenticated:
        action = st.radio("Select Action", ["Sign In", "Create Account"])
        
        if action == "Create Account":
            st.subheader("Create an Account")

            email = st.text_input("Enter your email:")
            password = st.text_input("Create a password:", type="password")
            confirm_password = st.text_input("Confirm your password:", type="password")

            if st.button("Create Account"):
                if email and password:
                    if password != confirm_password:
                        st.error("Passwords do not match!")
                    elif email in st.session_state.user_data:
                        st.error("Email is already registered!")
                    else:
                        # Store user email and hashed password
                        hashed_password = hashlib.sha256(password.encode()).hexdigest()
                        st.session_state.user_data[email] = {'password': hashed_password, 'name': '', 'trades': []}
                        st.session_state.current_user = email  # Auto-login after registration
                        st.session_state.authenticated = True
                        st.session_state.name_entered = False  # Proceed to name entry
                        save_user_data()  # Save user data to file
                        st.success(f"Account created successfully! Welcome, {email}!")
                        st.rerun()  # Reload the page to show the name input page
                else:
                    st.warning("Please enter both email and password.")
        
        elif action == "Sign In":
            st.subheader("Sign In")

            email = st.text_input("Enter your email:")
            password = st.text_input("Enter your password:", type="password")

            if st.button("Sign In"):
                if email in st.session_state.user_data:
                    hashed_password = st.session_state.user_data[email]['password']
                    if hashed_password == hashlib.sha256(password.encode()).hexdigest():
                        st.session_state.current_user = email
                        st.session_state.authenticated = True
                        # If the user has already entered their name, no need to prompt them again
                        if email in st.session_state.players:
                            st.session_state.name_entered = True
                        st.success(f"Welcome back, {email}!")
                        st.rerun()  # Reload the page to show the name input page
                    else:
                        st.error("Incorrect password!")
                else:
                    st.error("Email not registered!")
    
    elif st.session_state.authenticated:
        # Add new player or manage existing player's portfolio
        if not st.session_state.name_entered:
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

        # Logout button
        if st.button("Logout"):
            st.session_state.clear()  # Clears all session state variables
            st.success("Logged out successfully.")
            st.rerun()  # Rerun the app to return to the login screen
        
        display_leaderboard()

if __name__ == "__main__":
    main()
