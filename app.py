import streamlit as st
import pandas as pd
import yfinance as yf

# Initialize session state for users' portfolios
if 'players' not in st.session_state:
    st.session_state.players = {}

st.title("Fantasy Stock League 🏆")

# Add new player
player_name = st.text_input("Enter your name to join:")
if st.button("Join League") and player_name:
    if player_name not in st.session_state.players:
        st.session_state.players[player_name] = {
            'portfolio_value': 100000,  # Starting cash
            'trades': [],
            'score': 0
        }
        st.success(f"{player_name} joined the league!")
    else:
        st.warning("Player already exists!")

# Select player to manage portfolio
selected_player = st.selectbox("Select Player:", list(st.session_state.players.keys()))

if selected_player:
    player = st.session_state.players[selected_player]
    
    # Trade input
    stock_name = st.text_input("Stock Ticker (e.g., AAPL, TSLA):")
    trade_type = st.selectbox("Trade Type:", ["Buy", "Sell"])
    trade_amount = st.number_input("Investment Amount ($):", min_value=1, step=100)
    
    if st.button("Submit Trade") and stock_name:
        stock_data = yf.Ticker(stock_name).history(period='1d')
        if not stock_data.empty:
            stock_price = stock_data['Close'].iloc[-1]
            shares = trade_amount / stock_price
            trade = {"stock": stock_name, "type": trade_type, "amount": trade_amount, "shares": shares, "price": stock_price}
            player['trades'].append(trade)
            
            # Update portfolio value
            if trade_type == "Buy":
                player['portfolio_value'] -= trade_amount
            else:
                player['portfolio_value'] += trade_amount
            
            st.success(f"Trade recorded: {trade_type} {shares:.2f} shares of {stock_name} at ${stock_price:.2f}")
        else:
            st.error("Invalid stock ticker. Try again.")
    
    # Display portfolio
    st.subheader("Portfolio Summary")
    st.write(f"Portfolio Value: ${player['portfolio_value']:.2f}")
    st.write("Trade History:", player['trades'])

    # Scoring system
    def calculate_score(player):
        score = 0
        portfolio_change = (player['portfolio_value'] - 100000) / 1000  # Each 1% = 1 pt
        score += portfolio_change
        
        # Penalty: Overtrading
        if len(player['trades']) > 20:
            score -= 5
        
        # Bonus: Diversification
        stock_count = len(set([trade['stock'] for trade in player['trades']]))
        if stock_count >= 5:
            score += 3
        
        # Penalty: Reckless Investing
        large_trades = [trade for trade in player['trades'] if trade['amount'] > 50000]
        if len(large_trades) > 3:
            score -= 7
        
        # Bonus: Beating the Market
        market_ticker = yf.Ticker("^GSPC")  # S&P 500 Index
        market_change = (market_ticker.history(period='1d')['Close'].iloc[-1] - 100000) / 1000
        if portfolio_change > market_change:
            score += 10
        else:
            score -= 5
        
        return max(0, score)  # Ensure score is not negative
    
    player['score'] = calculate_score(player)
    st.write(f"Fantasy Score: {player['score']:.2f}")

# Display leaderboard
st.subheader("🏅 Leaderboard")
leaderboard = pd.DataFrame(
    [(name, data['score'], data['portfolio_value']) for name, data in st.session_state.players.items()],
    columns=["Player", "Score", "Portfolio Value"]
).sort_values(by="Score", ascending=False)

st.dataframe(leaderboard)
