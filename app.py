import streamlit as st
import pandas as pd
import yfinance as yf
import hashlib
import json
import os
import datetime
import plotly.express as px
import time  # Import the time module

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

import streamlit as st

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
    
    # Recalculate scores and penalties after loading user data
    for email in st.session_state.user_data:
        player = st.session_state.user_data[email]
        player['score'] = apply_penalties(player)
    save_user_data()

    # Ensure that every user has required fields
    for user_data in st.session_state.user_data.values():
        if 'portfolio_value' not in user_data:
            user_data['portfolio_value'] = 100000
        if 'name' not in user_data:
            user_data['name'] = ""
        if 'trades' not in user_data:
            user_data['trades'] = []
# Function to add a new player():
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
@st.cache_data(ttl=600)  # Cache for 10 minutes (600 seconds)
def get_stock_price_and_beta(stock_name):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            time.sleep(1)  # Introduce a 1-second delay
            stock_ticker = yf.Ticker(stock_name)
            stock_data = stock_ticker.history(period='1d')
            price = stock_data['Close'].iloc[-1] if not stock_data.empty else None
            beta = stock_ticker.info.get('beta')
            return price, beta
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff: 1, 2, 4 seconds
                time.sleep(wait_time)
                print(f"Retry {attempt + 1} for {stock_name} after error: {e}")
            else:
                error_message = f"Error fetching stock data for {stock_name} after multiple retries: {e}"
                print(error_message)
                st.error(error_message)
                return None, None

# Basic scoring functions - these need to be defined before they're used
def calculate_portfolio_score(player):
    """Calculate portfolio score based on percentage change weighted by initial stock price."""
    total_score = 0
    for trade in player['trades']:
        if trade['type'] == 'Buy':
            current_price, _ = get_stock_price_and_beta(trade['stock'])
            if current_price is not None and trade['initial_price'] != 0:  # Avoid division by zero
                percentage_change = ((current_price - trade['initial_price']) / trade['initial_price']) * 100
                score_contribution = percentage_change * trade['initial_price'] # Weight by initial price
                total_score += score_contribution

    return total_score

def calculate_overtrading_penalty(player):
    num_trades = len(player['trades'])
    print(f"calculate_overtrading_penalty - START - Number of trades: {num_trades}")
    print(f"calculate_overtrading_penalty - Trades list: {player['trades']}") # Print trades list for inspection
    current_portfolio_value = calculate_total_portfolio_value(player)
    print(f"calculate_overtrading_penalty - Portfolio Value: {current_portfolio_value}") # Print portfolio value
    
    if num_trades > 20:
        penalty_percentage = 0.10
        penalty_amount = current_portfolio_value * penalty_percentage
        print(f"calculate_overtrading_penalty - Overtrading penalty applied: {penalty_amount}") # Print penalty amount
        return penalty_amount
    else:
        print("calculate_overtrading_penalty - No penalty applied (trades <= 20)")
        return 0

import pandas as pd

def calculate_overtrading_penalty(player):
    today_date = pd.Timestamp.now().date()
    today_trades = [trade for trade in player['trades'] if trade['date'].date() == today_date]
    num_today_trades = len(today_trades)
    print(f"calculate_overtrading_penalty - START - Number of trades today: {num_today_trades}") # Debug print

    if num_today_trades >= 20:
        penalty_percentage = 0.10
        initial_scores_sum_today = sum(trade.get("initial_score_contribution", 0) for trade in today_trades)
        penalty_amount = initial_scores_sum_today * penalty_percentage
        print(f"calculate_overtrading_penalty - Overtrading penalty applied: {penalty_amount}") # Debug print
        return penalty_amount
    else:
        print(f"calculate_overtrading_penalty - No penalty applied (trades < 20)") # Debug print
        return 0

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
    total_penalty = 0
    print(f"calculate_day_trading_penalty - START - Day Trades: {day_trades}")
    if not day_trades:  # Check if day_trades is empty
        print("calculate_day_trading_penalty - No day trades found, penalty is 0")
        return 0

    for date, stocks in day_trades.items():
        print(f"calculate_day_trading_penalty - Date: {date}, Type: {type(date)}, Stocks: {stocks}")
        for stock, trade_count in stocks.items():
            sell_trade = next((t for t in player['trades']
                               if t['stock'] == stock
                               and t['type'] == 'Sell'
                               and t['date'].date() == date), None)
            print(f"calculate_day_trading_penalty - Sell Trade: {sell_trade}, Type: {type(sell_trade)}")
            if sell_trade:
                print(f"calculate_day_trading_penalty - Sell Trade Date: {sell_trade['date']}, Type: {type(sell_trade['date'])}")
                print(f"calculate_day_trading_penalty - Date from day_trades: {date}, Type: {type(date)}")
                penalty_per_share = sell_trade['price'] * 0.30
                penalty_for_stock = penalty_per_share * trade_count
                print(f"calculate_day_trading_penalty - Stock: {stock}, Trade Count: {trade_count}, Penalty per share: {penalty_per_share}, Penalty for stock: {penalty_for_stock}")
                total_penalty += penalty_for_stock
    print(f"calculate_day_trading_penalty - Total Day Trading Penalty: {total_penalty}")
    return total_penalty

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
    print(f"apply_penalties - START - Number of trades: {len(player['trades'])}")
    score = calculate_portfolio_score(player)
    print(f"apply_penalties - Initial Score (portfolio score): {score}")

    initial_score_bonus = sum(trade.get("initial_score_contribution", 0) for trade in player['trades'])
    score += initial_score_bonus
    print(f"apply_penalties - Score after initial bonus: {score}")

    overtrading_penalty = calculate_overtrading_penalty(player)
    print(f"apply_penalties - Overtrading Penalty: {overtrading_penalty}")
    score -= overtrading_penalty
    print(f"apply_penalties - Score after overtrading penalty: {score}")

    reckless_investing_penalty = calculate_reckless_investing_penalty(player)
    print(f"apply_penalties - Reckless Investing Penalty: {reckless_investing_penalty}")
    score -= reckless_investing_penalty
    print(f"apply_penalties - Score after reckless investing penalty: {score}")

    day_trading_penalty = calculate_day_trading_penalty(player)
    print(f"apply_penalties - Day Trading Penalty: {day_trading_penalty}")
    score_before_day_trade_penalty = score
    print(f"apply_penalties - Score before day trade penalty: {score_before_day_trade_penalty}") # Debugging line
    score -= day_trading_penalty
    print(f"apply_penalties - Score after day trading penalty: {score}") # Debugging line

    diversification_bonus = calculate_diversification_bonus(player)
    print(f"apply_penalties - Diversification Bonus: {diversification_bonus}")
    score += diversification_bonus
    print(f"apply_penalties - Score after diversification bonus: {score}")

    market_performance_bonus = calculate_market_performance_bonus(player)
    print(f"apply_penalties - Market Performance Bonus: {market_performance_bonus}")
    score += market_performance_bonus
    print(f"apply_penalties - Score after market performance bonus: {score}")

    for trade in player['trades']:
        if trade['type'] == 'Buy' and trade['beta'] is not None:
            if trade['beta'] >= 2:
                score -= 2
                print(f"apply_penalties - High Beta Penalty for {trade['stock']}: -2")
            else:
                score += 3
                print(f"apply_penalties - Low Beta Bonus for {trade['stock']}: +3")

    print(f"apply_penalties - Score before final adjustment: {score}")
    final_score = max(0, score) # Ensure score is not negative
    final_score = min(final_score, 100000) # Cap the score - arbitrarily high max score for reasonable gameplay
    print(f"apply_penalties - Final Score: {final_score}")
    print(f"apply_penalties - Score being returned: {final_score}")
    return final_score

# Function to process a sell trade
def process_sell_trade(player, stock_name, shares, entry_time, stock_price):
    available_shares = sum(t['shares'] for t in player['trades']
                         if t['stock'] == stock_name and t['type'] == 'Buy' and t['exit_time'] is None)

    if shares > available_shares:
        st.error(f"You only have {available_shares} shares available to sell")
        return

    trade_amount = shares * stock_price
    shares_to_sell = shares
    initial_score_contribution_deduction = 0

    for t in player['trades']:
        if (t['stock'] == stock_name and t['type'] == 'Buy' and
            t['exit_time'] is None and shares_to_sell > 0):
            shares_sold = min(shares_to_sell, t['shares'])
            t['exit_time'] = entry_time
            t['time_diff'] = entry_time - t['entry_time']
            shares_to_sell -= shares_sold
            initial_score_contribution_deduction += t.get('initial_score_contribution', 0) * (shares_sold / t['shares']) # Deduct proportionally

    player['portfolio_value'] += trade_amount

    # Deduct initial score contribution upon selling - REMOVE THIS LINE
    player['score'] -= initial_score_contribution_deduction
    score_change = -initial_score_contribution_deduction

    print(f"process_sell_trade - Score before potential deduction: {player['score']}", flush=True) # Debug print - forced flush
    st.write(f"Debug - process_sell_trade - Score before potential deduction: {player['score']}") # Streamlit debug output
    print(f"process_sell_trade - initial_score_contribution_deduction: {initial_score_contribution_deduction}", flush=True) # Debug print - forced flush
    st.write(f"Debug - process_sell_trade - initial_score_contribution_deduction: {initial_score_contribution_deduction}") # Streamlit debug output
    print(f"process_sell_trade - score_change: {score_change}", flush=True) # Debug print - forced flush
    st.write(f"Debug - process_sell_trade - score_change: {score_change}") # Streamlit debug output
    print(f"process_sell_trade - Before apply_penalties call, current score: {player['score']}", flush=True) # Debug print - forced flush
    st.write(f"Debug - process_sell_trade - Before apply_penalties call, current score: {player['score']}") # Streamlit debug output
    player['score'] = apply_penalties(player) # Recalculate score after sell
    print(f"process_sell_trade - Score after recalculating penalties: {player['score']}", flush=True) # Debug print - forced flush
    st.write(f"Debug - process_sell_trade - Score after recalculating penalties: {player['score']}") # Streamlit debug output

    # Add sell trade to history
    trade = {
        "stock": stock_name,
        "type": "Sell",
        "shares": shares,
        "price": stock_price,
        "entry_time": entry_time,
        "exit_time": None,
        "time_diff": None,
        "date": entry_time,
        "initial_score_contribution_deduction": initial_score_contribution_deduction, # Record deduction for audit
        "score_change": score_change # Record score change for sell
    }
    print(f"process_sell_trade - BEFORE APPEND - trade['score_change']: {trade['score_change']}") # Debug print
    st.write(f"Debug - process_sell_trade - BEFORE APPEND - trade['score_change']: {trade['score_change']}") # Streamlit debug output
    player['trades'].append(trade)

    st.success(f"Sell order recorded: {shares} shares of {stock_name} at ${stock_price:.2f}. Score deduction: {initial_score_contribution_deduction:.2f}, Score Change: {score_change:.2f}")

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
            "initial_price": stock_price, # Store initial price
            "initial_score_contribution": 0 # Initialize initial score contribution
        }

        # Calculate initial score contribution based on stock price and beta
        if beta is not None and beta >= 2:
            initial_score_contribution = stock_price * (1 - (beta / 2.5)) # Increased penalty for high beta
        else:
            initial_score_contribution = stock_price * (1 - (beta if beta is not None else 1)/5)
        trade["initial_score_contribution"] = initial_score_contribution
        trade["score_change"] = initial_score_contribution
        player['trades'].append(trade)
        player['portfolio_value'] -= trade_amount
        st.success(f"Buy order recorded: {shares} shares of {stock_name} at ${stock_price:.2f}. Initial score contribution: {initial_score_contribution:.2f}")

    elif trade_type == "Sell":
        process_sell_trade(player, stock_name, shares, entry_time, stock_price)
        print(f"Number of trades after sell trade execution: {len(player['trades'])}")  # Debug print after sell trade

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

    print("Calculating overtrading penalty...")  # Debug print
    overtrading_penalty = calculate_overtrading_penalty(player)
    print(f"Overtrading penalty value: {overtrading_penalty}")  # Debug print
    print(f"Number of trades: {len(player['trades'])}")  # Debug print
    print("Overtrading penalty is being displayed...")  # Debug print
    print(f"Overtrading penalty: {overtrading_penalty}") # Debug print
    print(f"display_portfolio - Number of trades: {len(player['trades'])}")
    print(f"display_portfolio - Overtrading penalty value: {overtrading_penalty}")
    if overtrading_penalty > 0:
        st.subheader("⚠️ Overtrading Penalty")
        st.write(f"Overtrading Penalty Value: ${overtrading_penalty:.2f}")
        st.write(f"Overtrading Penalty: -{overtrading_penalty:.2f} points (More than 20 trades)")


    if player['trades']:
        st.subheader("Trade History")
        trades_df = pd.DataFrame(player['trades'])
        trades_df['time_diff'] = trades_df['time_diff'].astype(str)
        trades_df['score_change'] = trades_df['score_change'].fillna(0) # Ensure NaN values are 0 for display
        trades_df['Cumulative Score Change'] = trades_df['score_change'].cumsum()
        trades_df.index = trades_df.index + 1
        st.dataframe(trades_df)

# Display leaderboard function
def calculate_total_portfolio_value(player):
    """Calculates the total portfolio value including cash and stock holdings."""
    portfolio_value = player['portfolio_value'] # Start with cash
    print(f"calculate_total_portfolio_value - Initial cash: {portfolio_value}")
    for trade in player['trades']:
        if trade['type'] == 'Buy' and trade['exit_time'] is None: # Consider only currently held stocks
            current_price, _ = get_stock_price_and_beta(trade['stock'])
            print(f"calculate_total_portfolio_value - Stock: {trade['stock']}, Shares: {trade['shares']}, Current Price: {current_price}")
            if current_price is not None:
                portfolio_value += trade['shares'] * current_price # Add current value of stocks
    print(f"calculate_total_portfolio_value - Final portfolio value: {portfolio_value}")
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

@st.cache_data(ttl=300)  # Cache for 5 minutes
def prefetch_stock_data(stock_list):
    """Prefetches stock data for a list of stock tickers."""
    for stock_name in stock_list:
        get_stock_price_and_beta(stock_name)

def display_stock_spread(player):
    """Displays a pie chart of the player's stock holdings, showing only open buy positions."""
    stock_counts = {}
    open_buy_trades = []
    sold_stocks = set()

    # Identify stocks that have been sold
    for trade in player['trades']:
        if trade['type'] == 'Sell':
            sold_stocks.add(trade['stock'])

    # Filter out buy trades for stocks that have been sold
    for trade in player['trades']:
        if trade['type'] == 'Buy' and trade['stock'] not in sold_stocks:
            open_buy_trades.append(trade)

    # Calculate stock counts for open buy trades
    for trade in open_buy_trades:
        if trade['stock'] not in stock_counts:
            stock_counts[trade['stock']] = 0
        stock_counts[trade['stock']] += trade['shares']

    if not stock_counts:
        st.write("No open stock holdings to display.")
        stock_df = pd.DataFrame({'Stock': [], 'Shares': []}) # Create empty DataFrame
    else:
        # Create a DataFrame for the pie chart
        stock_df = pd.DataFrame(list(stock_counts.items()), columns=['Stock', 'Shares'])
    stock_df.index = stock_df.index + 1

    # Create the pie chart using Plotly
    fig = px.pie(stock_df, names='Stock', values='Shares', title='Open Stock Holdings Distribution (Buy Trades Only)')
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
                        # Prefetch stock data after account creation
                        user_trades = st.session_state.user_data[email]['trades']
                        stock_list = list(set([trade['stock'] for trade in user_trades])) if user_trades else []
                        prefetch_stock_data(stock_list)
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
                        # Prefetch stock data after login
                        user_trades = st.session_state.user_data[email]['trades']
                        stock_list = list(set([trade['stock'] for trade in user_trades])) if user_trades else []
                        prefetch_stock_data(stock_list)
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
            st.rerun() # Rerun to update chart immediately

        print("Before apply_penalties") # Debug print
        player['score'] = apply_penalties(player)
        print("After apply_penalties, score:", player['score']) # Debug print
        display_portfolio(player)
        st.write(f"Fantasy Score: {player['score']:.2f}")
        save_user_data()  # Save after score update
        print("After save_user_data") # Debug print

        if st.button("Logout"):
            st.session_state.clear()
            st.success("Logged out successfully.")
            st.rerun()

        display_leaderboard()


if __name__ == "__main__":
    main()
