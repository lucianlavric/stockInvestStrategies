import streamlit as st
import pandas as pd
import yfinance as yf
import hashlib
import json
import os
import datetime
import plotly.express as px

USER_DATA_FILE = 'user_data.json'

def serialize_trade(trade):
    """Convert trade data to a JSON serializable format."""
    serialized_trade = trade.copy()
    
    # Convert specific datetime objects and handle None values
    for key, value in serialized_trade.items():
        print(f"Serializing - Key: {key}, Value: {value}, Type: {type(value)}") # Debug print
        if isinstance(value, datetime.datetime):  # Check for datetime objects
            serialized_trade[key] = value.isoformat()
        elif isinstance(value, pd.Timedelta):  # Check for Timedelta objects
            serialized_trade[key] = str(value)  # Convert Timedelta to string
            print(f"Serialized Timedelta - Key: {key}, Value: {serialized_trade[key]}, Type: {type(serialized_trade[key])}") # Debug print
        elif value is None:
            serialized_trade[key] = None
            
    return serialized_trade

def deserialize_trade(serialized_trade):
    """Convert serialized trade data back into a trade object."""
    deserialized_trade = serialized_trade.copy()
    
    for key, value in deserialized_trade.items():
        print(f"Deserializing - Key: {key}, Value: {value}, Type: {type(value)}") # Debug print
        if isinstance(value, str) and key in ['date', 'entry_time', 'exit_time']:
            try:
                deserialized_trade[key] = pd.to_datetime(value)
            except ValueError:
                deserialized_trade[key] = None
        elif key == 'time_diff' and isinstance(value, str):
            deserialized_trade[key] = value # Keep time_diff as string
            print(f"Deserialized time_diff - Key: {key}, Value: {deserialized_trade[key]}, Type: {type(deserialized_trade[key])}") # Debug print
        elif value is None:
            deserialized_trade[key] = None
            
    # Ensure initial_price exists
    if 'initial_price' not in deserialized_trade:
        deserialized_trade['initial_price'] = None
        
    return deserialized_trade

def save_user_data():
    """Save user data to file with error handling"""
    try:
        serialized_data = {}
        for email, user_data in st.session_state.user_data.items():
            serialized_user = user_data.copy()
            if 'trades' in user_data:
                serialized_user['trades'] = [serialize_trade(trade) for trade in user_data['trades']]
            serialized_data[email] = serialized_user

        with open(USER_DATA_FILE, 'w') as file:
            json.dump(serialized_data, file, indent=4)
        print("Serialized data saved successfully") # Debug print
    except Exception as e:
        st.error(f"Error saving user data: {str(e)}")
        # Log the error for debugging
        print(f"Error saving user data: {str(e)}")

def initialize_session():
    """Initialize session state with improved error handling"""
    if 'user_data' not in st.session_state:
        st.session_state.user_data = {}
    if 'current_user' not in st.session_state:
        st.session_state.current_user = None
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    if 'players' not in st.session_state:
        st.session_state.players = {}

    # Load user data from file if it exists
    if os.path.exists(USER_DATA_FILE):
        try:
            with open(USER_DATA_FILE, 'r') as file:
                loaded_data = json.load(file)
                
            # Deserialize the loaded data
            st.session_state.user_data = {}
            for email, user_data in loaded_data.items():
                deserialized_user = user_data.copy()
                if 'trades' in user_data:
                    try:
                        deserialized_user['trades'] = [deserialize_trade(trade) for trade in user_data['trades']]
                    except Exception as e:
                        print(f"Error deserializing trades for {email}: {str(e)}")
                        deserialized_user['trades'] = []
                st.session_state.user_data[email] = deserialized_user
                
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {str(e)}")
            print(e)
            st.session_state.user_data = {}
            st.error("Error reading user data file. Starting with empty data.")
        except Exception as e:
            print(f"Unexpected error loading user data: {str(e)}")
            print(e)
            st.session_state.user_data = {}
            st.error(f"An error occurred loading user data: {str(e)}")
    
    # Ensure that every user has required fields
    for user_data in st.session_state.user_data.values():
        if 'portfolio_value' not in user_data:
            user_data['portfolio_value'] = 100000
        if 'name' not in user_data:
            user_data['name'] = ""
        if 'trades' not in user_data:
            user_data['trades'] = []# [Rest of your existing code remains the same...]
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

# Function to get stock price and beta
def get_stock_price_and_beta(stock_name):
    try:
        stock_ticker = yf.Ticker(stock_name)
        stock_data = stock_ticker.history(period='1d')
        price = stock_data['Close'].iloc[-1] if not stock_data.empty else None
        beta = stock_ticker.info.get('beta') # Use .get() to avoid KeyError if beta is not available
        return price, beta
    except Exception as e:
        print(f"Error fetching stock data for {stock_name}: {e}")
        return None, None

# Basic scoring functions - these need to be defined before they're used
def calculate_portfolio_score(player):
    """Calculate portfolio score based on percentage change relative to initial stock prices."""
    total_percentage_change = 0
    num_trades = 0
    for trade in player['trades']:
        if trade['type'] == 'Buy':
            current_price, _ = get_stock_price_and_beta(trade['stock'])
            if current_price is not None and trade['initial_price'] != 0:  # Avoid division by zero
                percentage_change = ((current_price - trade['initial_price']) / trade['initial_price']) * 100
                total_percentage_change += percentage_change
                num_trades += 1

    if num_trades > 0:
        average_percentage_change = total_percentage_change / num_trades
        return average_percentage_change
    else:
        return 0  # Return 0 if no buy trades to avoid division by zero

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
            date = trade['date'].date()
            stock = trade['stock']

            # Find buy trades for the same stock on the same day
            buy_trades = [t for t in player['trades']
                         if t['stock'] == stock
                         and t['type'] == "Buy"
                         and t['date'].date() == date]

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

    # Adjust score based on beta values of stocks in portfolio
    for trade in player['trades']:
        if trade['type'] == 'Buy' and trade['beta'] is not None:
            if trade['beta'] >= 2:
                score -= 2  # Apply penalty for high beta stocks (risky)
            else:
                score += 3   # Apply bonus for low beta stocks (conservative)

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
        "date": entry_time
    }
    player['trades'].append(trade)

    st.success(f"Sell order recorded: {shares} shares of {stock_name} at ${stock_price:.2f}")

# Function to execute a trade
def execute_trade(player, stock_name, trade_type, shares):
    stock_price, beta = get_stock_price_and_beta(stock_name)
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
            "beta": beta, # Store beta value
            "entry_time": entry_time,
            "exit_time": None,
            "time_diff": None,
            "date": entry_time,
            "initial_price": stock_price # Store initial price
        }
        player['trades'].append(trade)
        player['portfolio_value'] -= trade_amount
        st.success(f"Buy order recorded: {shares} shares of {stock_name} at ${stock_price:.2f}")

    elif trade_type == "Sell":
        process_sell_trade(player, stock_name, shares, entry_time, stock_price)

# Function to display the player's portfolio
def display_portfolio(player):
    st.subheader("Portfolio Summary")
    total_portfolio_value = calculate_total_portfolio_value(player)
    st.write(f"Total Portfolio Value: ${total_portfolio_value:,.2f}")
    st.write(f"Cash Balance: ${player['portfolio_value']:,.2f}") # Display cash balance separately

    # Display day trading activity
    day_trades = get_day_trades(player)
    print(f"Day trades: {day_trades}") # Debug print
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
def calculate_total_portfolio_value(player):
    """Calculates the total portfolio value including cash and stock holdings."""
    portfolio_value = player['portfolio_value'] # Start with cash
    for trade in player['trades']:
        if trade['type'] == 'Buy' and trade['exit_time'] is None: # Consider only currently held stocks
            current_price, _ = get_stock_price_and_beta(trade['stock'])
            if current_price is not None:
                portfolio_value += trade['shares'] * current_price # Add current value of stocks
    return portfolio_value

def display_leaderboard():
    st.subheader("🏅 Leaderboard")
    
    if not st.session_state.user_data:
        st.write("No users registered yet.")
        return

    # Prepare leaderboard data
    leaderboard_data = []
    for email, user_data in st.session_state.user_data.items():
        total_portfolio_value = calculate_total_portfolio_value(user_data)
        leaderboard_data.append({
            "Player": user_data['name'],
            "Score": user_data['score'],
            "Portfolio Value": total_portfolio_value
        })

    # Convert the list to a DataFrame and sort by Score in descending order
    leaderboard_df = pd.DataFrame(leaderboard_data).sort_values(by="Score", ascending=False)

    # Add a 'Rank' column based on the sorted order
    leaderboard_df['Rank'] = range(1, len(leaderboard_df) + 1)

    # Reorder columns to display rank first
    leaderboard_df = leaderboard_df[['Rank', 'Player', 'Score', 'Portfolio Value']]

    # Display the leaderboard without index
    st.dataframe(leaderboard_df.set_index('Rank'))


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

# Previous imports and functions remain the same until the main() function

def display_stock_spread(player):
    """Displays a pie chart of the player's stock holdings."""
    stock_counts = {}
    
    # Loop through the player's trades and calculate the total number of shares for each stock
    for trade in player['trades']:
        if trade['type'] == 'Buy':
            if trade['stock'] not in stock_counts:
                stock_counts[trade['stock']] = 0
            stock_counts[trade['stock']] += trade['shares']
    
    if not stock_counts:
        st.write("No stock holdings to display.")
        return
    
    # Create a DataFrame for the pie chart
    stock_df = pd.DataFrame(list(stock_counts.items()), columns=['Stock', 'Shares'])

    # Create the pie chart using Plotly
    fig = px.pie(stock_df, names='Stock', values='Shares', title='Stock Holdings Distribution')
    st.plotly_chart(fig)

def main():
    initialize_session()
    st.title("Fantasy Stock League 🏆")

    # Initial Sign-in / Registration Page
    if not st.session_state.authenticated:
        action = st.radio("Select Action", ["Sign In", "Create Account"])
        
        if action == "Create Account":
            st.subheader("Create an Account")
            email = st.text_input("Enter your email:")
            name = st.text_input("Enter your name:")
            password = st.text_input("Create a password:", type="password")
            confirm_password = st.text_input("Confirm your password:", type="password")

            if st.button("Create Account"):
                if email and password and name:
                    if password != confirm_password:
                        st.error("Passwords do not match!")
                    elif email in st.session_state.user_data:
                        st.error("Email is already registered!")
                    else:
                        hashed_password = hashlib.sha256(password.encode()).hexdigest()
                        st.session_state.user_data[email] = {
                            'password': hashed_password,
                            'name': name,
                            'trades': [],
                            'portfolio_value': 100000,
                            'score': 0
                        }
                        st.session_state.current_user = email
                        st.session_state.authenticated = True
                        save_user_data()
                        st.success(f"Account created successfully! Welcome, {name}!")
                        st.rerun()
                else:
                    st.warning("Please enter email, name, and password.")

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
                        st.success(f"Welcome back, {st.session_state.user_data[email]['name']}!")
                        st.rerun()
                    else:
                        st.error("Incorrect password!")
                else:
                    st.error("Email not registered!")

    elif st.session_state.authenticated:
        # Get current user's data
        current_user = st.session_state.current_user
        player = st.session_state.user_data[current_user]
        
        st.write(f"Welcome, {player['name']}!")

        # Display stock holdings pie chart
        display_stock_spread(player)  # Display pie chart of stock holdings

        stock_name = st.text_input("Stock Ticker (e.g., AAPL, TSLA):")
        trade_type = st.selectbox("Trade Type:", ["Buy", "Sell"])
        shares = st.number_input("Number of Shares:", min_value=1, step=1)

        display_stock_history(stock_name)

        if st.button("Submit Trade") and stock_name:
            execute_trade(player, stock_name, trade_type, shares)
            save_user_data()  # Save after each trade

        display_portfolio(player)
        player['score'] = apply_penalties(player)
        st.write(f"Fantasy Score: {player['score']:.2f}")
        save_user_data()  # Save after score update

        if st.button("Logout"):
            st.session_state.clear()
            st.success("Logged out successfully.")
            st.rerun()

        display_leaderboard()


if __name__ == "__main__":
    main()
