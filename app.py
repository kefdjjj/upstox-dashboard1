import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime, timedelta
from scipy.signal import find_peaks
import numpy as np

st.set_page_config(page_title="Upstox Trading Dashboard", layout="wide")

st.title("📈 Stock & Options Dashboard (Upstox API)")
st.markdown("Features: **UT Bot Alerts** & **Elliott Wave Analysis**")

# Sidebar inputs
st.sidebar.header("1. API Configuration")
access_token = st.sidebar.text_input("Upstox Access Token", type="password")
st.sidebar.caption("Generate this from your Upstox Developer Portal.")

st.sidebar.header("2. Data Configuration")
instrument_key = st.sidebar.text_input("Instrument Key", value="NSE_EQ|INE002A01018")
st.sidebar.caption("E.g. NSE_EQ|INE002A01018 (Reliance), NSE_FO|41234 (Options).")

interval = st.sidebar.selectbox("Interval", ["day", "1minute", "5minute", "15minute", "30minute"])
days_back = st.sidebar.number_input("Days to Fetch", min_value=1, max_value=365, value=30)

st.sidebar.header("3. UT Bot Parameters")
ut_key = st.sidebar.number_input("Key Value (Multiplier)", value=2.0, step=0.1)
ut_atr = st.sidebar.number_input("ATR Period", value=10, step=1)

def fetch_data():
    to_date = datetime.now().strftime('%Y-%m-%d')
    from_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
    
    # Upstox Historical API endpoint
    url = f"https://api.upstox.com/v2/historical-candle/{instrument_key}/{interval}/{to_date}/{from_date}"

    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {access_token}' if access_token else ''
    }
    
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        if 'data' in data and data['data'] and 'candles' in data['data']:
            candles = data['data']['candles']
            df = pd.DataFrame(candles, columns=['Timestamp', 'Open', 'High', 'Low', 'Close', 'Volume', 'OI'])
            df['Timestamp'] = pd.to_datetime(df['Timestamp'])
            df.set_index('Timestamp', inplace=True)
            df = df.sort_index()
            for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
                df[col] = pd.to_numeric(df[col])
            return df
        else:
            st.error("No data found for the given instrument in the specified date range.")
            return None
    else:
        st.error(f"API Error ({response.status_code}): {response.text}")
        return None

def apply_ut_bot(df, key=2.0, period=10):
    # Pure Python/Pandas Implementation of UT Bot (bypasses pandas-ta/numba dependency)
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    
    # TradingView style RMA (Exponential Moving Average)
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    nLoss = key * atr
    src = df['Close']
    
    xATRTrailingStop = np.zeros(len(df))
    
    for i in range(1, len(df)):
        prev_stop = xATRTrailingStop[i-1]
        curr_src = src.iloc[i]
        prev_src = src.iloc[i-1]
        curr_loss = nLoss.iloc[i]
        
        if curr_src > prev_stop and prev_src > prev_stop:
            xATRTrailingStop[i] = max(prev_stop, curr_src - curr_loss)
        elif curr_src < prev_stop and prev_src < prev_stop:
            xATRTrailingStop[i] = min(prev_stop, curr_src + curr_loss)
        elif curr_src > prev_stop:
            xATRTrailingStop[i] = curr_src - curr_loss
        else:
            xATRTrailingStop[i] = curr_src + curr_loss
            
    df['UTBot_Value'] = xATRTrailingStop
    
    # Calculate Position (1 for Buy, -1 for Sell)
    direction = np.zeros(len(df))
    for i in range(1, len(df)):
        if src.iloc[i] > xATRTrailingStop[i] and src.iloc[i-1] <= xATRTrailingStop[i-1]:
            direction[i] = 1
        elif src.iloc[i] < xATRTrailingStop[i] and src.iloc[i-1] >= xATRTrailingStop[i-1]:
            direction[i] = -1
        else:
            direction[i] = direction[i-1]
            
    df['UTBot_Direction'] = direction
    
    # Crosses to generate Buy/Sell
    df['Buy_Signal'] = (df['UTBot_Direction'] == 1) & (df['UTBot_Direction'].shift(1) == -1)
    df['Sell_Signal'] = (df['UTBot_Direction'] == -1) & (df['UTBot_Direction'].shift(1) == 1)
    
    # Fix initial 0 values
    df['UTBot_Value'].replace(0.0, np.nan, inplace=True)
    return df

def apply_elliott_wave(df):
    # Basic peak/trough detection to simulate Elliott Wave structural pivots
    distance = max(len(df) // 20, 3) 
    peaks, _ = find_peaks(df['High'], distance=distance)
    troughs, _ = find_peaks(-df['Low'], distance=distance)
    
    return df, peaks, troughs

if st.button("Fetch & Analyze"):
    if not access_token:
        st.warning("Please enter your Upstox Access Token in the sidebar.")
    else:
        with st.spinner("Fetching data from Upstox..."):
            df = fetch_data()
            
        if df is not None and not df.empty:
            st.success(f"Data fetched successfully! ({len(df)} candles)")
            
            # Apply indicators
            df = apply_ut_bot(df, key=ut_key, period=ut_atr)
            df, peaks, troughs = apply_elliott_wave(df)
            
            fig = go.Figure()
            
            # 1. Candlestick Chart
            fig.add_trace(go.Candlestick(
                x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
                name='Price'
            ))
            
            # 2. UT Bot Stop Line & Buy/Sell Signals
            if 'UTBot_Value' in df.columns:
                fig.add_trace(go.Scatter(
                    x=df.index, y=df['UTBot_Value'], mode='lines',
                    line=dict(color='purple', width=1, dash='dot'),
                    name='UT Bot Trailing Stop'
                ))
                
                buy_dates = df[df['Buy_Signal']].index
                buy_prices = df.loc[df['Buy_Signal'], 'Low'] - (df['Close'].mean() * 0.005)
                fig.add_trace(go.Scatter(
                    x=buy_dates, y=buy_prices, mode='markers+text',
                    marker=dict(symbol='triangle-up', color='#00ff00', size=14),
                    text=['BUY'] * len(buy_dates), textposition='bottom center',
                    name='UT Bot Buy'
                ))
                
                sell_dates = df[df['Sell_Signal']].index
                sell_prices = df.loc[df['Sell_Signal'], 'High'] + (df['Close'].mean() * 0.005)
                fig.add_trace(go.Scatter(
                    x=sell_dates, y=sell_prices, mode='markers+text',
                    marker=dict(symbol='triangle-down', color='#ff0000', size=14),
                    text=['SELL'] * len(sell_dates), textposition='top center',
                    name='UT Bot Sell'
                ))
            
            # 3. Elliott Wave Paths
            wave_x = []
            wave_y = []
            combined_pts = []
            for p in peaks: combined_pts.append((df.index[p], df['High'].iloc[p], 'Peak'))
            for t in troughs: combined_pts.append((df.index[t], df['Low'].iloc[t], 'Trough'))
            combined_pts.sort(key=lambda x: x[0])
            
            wave_labels = ['1', '2', '3', '4', '5', 'A', 'B', 'C']
            label_idx = 0
            
            for pt in combined_pts:
                wave_x.append(pt[0])
                wave_y.append(pt[1])
                if label_idx < len(wave_labels):
                    fig.add_annotation(
                        x=pt[0], y=pt[1],
                        text=f"W-{wave_labels[label_idx]}",
                        showarrow=True, arrowhead=1,
                        yshift=20 if pt[2] == 'Peak' else -20,
                        font=dict(color="orange", size=12)
                    )
                    label_idx = (label_idx + 1) % len(wave_labels)
            
            fig.add_trace(go.Scatter(
                x=wave_x, y=wave_y, mode='lines',
                line=dict(color='orange', width=2),
                name='Elliott Wave Path'
            ))
            
            fig.update_layout(
                title=f"Technical Analysis - {instrument_key}",
                yaxis_title="Price", xaxis_title="Date",
                height=800, template='plotly_dark',
                xaxis_rangeslider_visible=False,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            st.subheader("Recent Market Data")
            st.dataframe(df.tail(50))
