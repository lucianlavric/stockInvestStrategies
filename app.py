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
                            "time_diff": None
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

    # Display leaderboard
    st.subheader("🏅 Leaderboard")
    leaderboard = pd.DataFrame(
        [(name, data['portfolio_value']) for name, data in st.session_state.players.items()],
        columns=["Player", "Portfolio Value"]
    ).sort_values(by="Portfolio Value", ascending=False)
    leaderboard['Portfolio Value'] = leaderboard['Portfolio Value'].map('${:,.2f}'.format)
    st.dataframe(leaderboard)
else:
    st.info("No players have joined yet. Be the first to join!")