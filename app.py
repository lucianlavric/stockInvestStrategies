import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime

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
if st.session_state.players:  # Only show if there are players
    selected_player = st.selectbox("Select Player:", list(st.session_state.players.keys()))

    if selected_player:
        player = st.session_state.players[selected_player]
        
        # Trade input
        stock_name = st.text_input("Stock Ticker (e.g., AAPL, TSLA):")
        trade_type = st.selectbox("Trade Type:", ["Buy", "Sell"])
        shares = st.number_input("Number of Shares:", min_value=1, step=1)

        if st.button("Submit Trade") and stock_name:
            try:
                stock_data = yf.Ticker(stock_name).history(period='1d')
                if not stock_data.empty:
                    stock_price = stock_data['Close'].iloc[-1]
                    trade_amount = shares * stock_price
                    entry_time = pd.Timestamp.now()

                    # Validate trade
                    if trade_type == "Buy" and trade_amount > player['portfolio_value']:
                        st.error("Insufficient funds for this trade!")
                    else:
                        trade = {
                            "stock": stock_name,
                            "type": trade_type,
                            "shares": shares,
                            "price": stock_price,
                            "entry_time": entry_time,
                            "exit_time": None,
                            "time_diff": None,
                            "date": entry_time.date()  # Add date to check for day trading
                        }

                        if trade_type == "Buy":
                            player['trades'].append(trade)
                            player['portfolio_value'] -= trade_amount
                            st.success(f"Buy order recorded: {shares} shares of {stock_name} at ${stock_price:.2f}")
                        
                        elif trade_type == "Sell":
                            # Find matching buy trades
                            available_shares = sum(t['shares'] for t in player['trades'] 
                                                if t['stock'] == stock_name and t['type'] == 'Buy' 
                                                and t['exit_time'] is None)
                            
                            if shares > available_shares:
                                st.error(f"You only have {available_shares} shares available to sell")
                            else:
                                # Mark the corresponding buy trades as sold
                                shares_to_sell = shares
                                for t in player['trades']:
                                    if (t['stock'] == stock_name and t['type'] == 'Buy' 
                                        and t['exit_time'] is None and shares_to_sell > 0):
                                        t['exit_time'] = entry_time
                                        t['time_diff'] = entry_time - t['entry_time']
                                        shares_to_sell -= t['shares']
                                
                                trade['exit_time'] = entry_time
                                player['trades'].append(trade)
                                player['portfolio_value'] += trade_amount
                                st.success(f"Sell order recorded: {shares} shares of {stock_name} at ${stock_price:.2f}")
                else:
                    st.error("Could not fetch stock data. Please check the ticker symbol.")
            except Exception as e:
                st.error(f"Error processing trade: {str(e)}")

        # Display portfolio
        st.subheader("Portfolio Summary")
        st.write(f"Portfolio Value: ${player['portfolio_value']:,.2f}")

        if player['trades']:
            trades_df = pd.DataFrame(player['trades'])
            trades_df['time_diff'] = trades_df['time_diff'].astype(str)
            st.write("Trade History:")
            st.dataframe(trades_df)

            # Calculate and display current positions
            positions = {}
            for trade in player['trades']:
                symbol = trade['stock']
                if symbol not in positions:
                    positions[symbol] = 0
                if trade['type'] == 'Buy':
                    positions[symbol] += trade['shares']
                else:
                    positions[symbol] -= trade['shares']
            
            if positions:
                st.subheader("Current Positions")
                positions_df = pd.DataFrame(positions.items(), columns=['Stock', 'Shares'])
                positions_df = positions_df[positions_df['Shares'] > 0]  # Only show active positions
                if not positions_df.empty:
                    st.dataframe(positions_df)

        # Display stock chart with trade overlays
        if stock_name:
            try:
                stock_history = yf.Ticker(stock_name).history(period='1mo')
                if not stock_history.empty:
                    st.subheader(f"{stock_name} Stock History (1 Month)")
                    
                    # Create base chart
                    chart_data = pd.DataFrame({
                        'Price': stock_history['Close']
                    })
                    st.line_chart(chart_data)

                    # Display trade markers
                    stock_trades = [t for t in player['trades'] if t['stock'] == stock_name]
                    if stock_trades:
                        st.write("Trade Markers:")
                        for trade in stock_trades:
                            marker = "🟢" if trade['type'] == "Buy" else "🔴"
                            st.write(f"{marker} {trade['type']}: {trade['shares']} shares @ ${trade['price']:.2f} on {trade['entry_time'].strftime('%Y-%m-%d %H:%M')}")
            except Exception as e:
                st.error(f"Error displaying stock chart: {str(e)}")

    # Function for applying penalties
    def apply_penalties(player):
        score = 0
        portfolio_change = (player['portfolio_value'] - 100000) / 1000  # Each 1% = 1 pt
        score += portfolio_change
        
        # Penalty: Overtrading (more than 20 trades)
        if len(player['trades']) > 20:
            score -= 5
        
        # Bonus: Diversification (more than 5 different stocks)
        stock_count = len(set([trade['stock'] for trade in player['trades']]))
        if stock_count >= 5:
            score += 3
        
        # Penalty: Reckless Investing (more than 3 trades over 50,000)
        large_trades = [trade for trade in player['trades'] if trade['shares'] * trade['price'] > 50000]
        if len(large_trades) > 3:
            score -= 7
        
        # Bonus: Beating the Market
        market_ticker = yf.Ticker("^GSPC")  # S&P 500 Index
        market_change = (market_ticker.history(period='1d')['Close'].iloc[-1] - 100000) / 1000
        if portfolio_change > market_change:
            score += 10
        else:
            score -= 5
        
        # Day trading penalty: Check if a player bought and sold on the same day
        day_trade_penalty = 0
        day_trading_flag = False  # Initialize flag for day trading
        for trade in player['trades']:
            if trade['type'] == "Sell":
                # Check if there's a buy on the same date
                buy_trades_on_same_day = [
                    t for t in player['trades'] if t['stock'] == trade['stock'] and t['type'] == "Buy" and t['date'] == trade['date']
                ]
                if buy_trades_on_same_day:
                    day_trade_penalty += 5  # Deduct 5 points for day trading
                    day_trading_flag = True  # Set flag to True when day trading occurs
        
        # Display day trading flag if triggered
        if day_trading_flag:
            st.warning("Day trading detected! A penalty has been applied.")
        
        # Subtract the day trade penalty from the score
        score -= day_trade_penalty
        
        return max(0, score)  # Ensure score is not negative

    # Apply penalties and calculate the final score
    player['score'] = apply_penalties(player)
    st.write(f"Fantasy Score: {player['score']:.2f}")

# Display leaderboard
st.subheader("🏅 Leaderboard")
leaderboard = pd.DataFrame(
    [(name, data['score'], data['portfolio_value']) for name, data in st.session_state.players.items()],
    columns=["Player", "Score", "Portfolio Value"]
).sort_values(by="Score", ascending=False)

st.dataframe(leaderboard)
