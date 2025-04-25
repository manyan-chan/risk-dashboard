from datetime import datetime

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# --- 1. Data Simulation (Identical to the Dash version - Replace with your actual data) ---


# Simulate position data
def generate_dummy_positions(portfolio_name="Portfolio A"):
    # Simple mapping for deterministic generation based on portfolio name
    seed = sum(ord(c) for c in portfolio_name)
    np.random.seed(seed)
    n_positions = np.random.randint(10, 30)
    tickers = [f"TICKER_{i}" for i in range(n_positions)]
    asset_classes = np.random.choice(
        ["Equity", "Fixed Income", "FX", "Commodity"],
        n_positions,
        p=[0.5, 0.2, 0.15, 0.15],
    )
    market_values_usd = np.random.uniform(50000, 5000000, n_positions)
    # Simulate some factor sensitivities (simplified)
    beta_spx = np.random.normal(1, 0.5, n_positions) * (
        asset_classes == "Equity"
    ) + np.random.normal(0.1, 0.1, n_positions) * (asset_classes != "Equity")
    duration = np.random.normal(5, 2, n_positions) * (asset_classes == "Fixed Income")
    delta_oil = np.random.normal(0.05, 0.2, n_positions) * (
        asset_classes == "Commodity"
    )

    return pd.DataFrame(
        {
            "Ticker": tickers,
            "AssetClass": asset_classes,
            "MarketValueUSD": market_values_usd.round(2),
            "Beta_SPX": beta_spx.round(3),
            "Duration": duration.clip(0).round(3),  # Duration cannot be negative
            "Delta_Oil": delta_oil.round(3),
        }
    )


# Simulate historical risk metrics
# Use Streamlit's caching for better performance when portfolio doesn't change
@st.cache_data  # Caches the output based on input arguments
def generate_dummy_risk_history(portfolio_name="Portfolio A"):
    # Adding print to show when function re-runs (cache misses)
    print(f"Cache miss: Generating risk history for {portfolio_name}")
    seed = sum(ord(c) for c in portfolio_name) + 1
    np.random.seed(seed)
    dates = pd.date_range(
        end=datetime.today(), periods=252 * 2
    ).normalize()  # ~2 years daily
    nav_start = 100_000_000
    daily_returns = np.random.normal(0.0005, 0.01, len(dates))
    nav = nav_start * (1 + daily_returns).cumprod()
    var_99 = np.random.uniform(0.01, 0.03, len(dates)) * nav  # % VaR to absolute
    es_99 = var_99 * np.random.uniform(1.2, 1.5, len(dates))  # ES > VaR

    # Calculate drawdowns
    rolling_max = pd.Series(nav).cummax()
    drawdown = (nav - rolling_max) / rolling_max

    return pd.DataFrame(
        {
            "Date": dates,
            "NAV": nav,
            "VaR_99_USD": var_99,
            "ES_99_USD": es_99,
            "Drawdown_Pct": drawdown,
        }
    )


# --- 2. Simplified Risk Engine Simulation (Identical to Dash version - Replace) ---
def simulate_scenario_pnl(
    positions_df, spx_shock=0.0, rates_shock_bps=0.0, oil_shock=0.0
):
    rates_shock_decimal = rates_shock_bps / 10000.0
    positions_df["ScenarioPnL"] = positions_df["MarketValueUSD"] * (
        positions_df["Beta_SPX"] * spx_shock
        + positions_df["Delta_Oil"] * oil_shock
        - positions_df["Duration"] * rates_shock_decimal
    )
    return positions_df


# --- 3. Predefined Scenarios (Identical dictionary) ---
PREDEFINED_SCENARIOS = {
    "None (Baseline)": {"spx_shock": 0.0, "rates_shock_bps": 0.0, "oil_shock": 0.0},
    "Market Crash (-15% SPX)": {
        "spx_shock": -0.15,
        "rates_shock_bps": 0.0,
        "oil_shock": 0.0,
    },
    "Rates Shock (+50bps)": {
        "spx_shock": 0.0,
        "rates_shock_bps": 50.0,
        "oil_shock": 0.0,
    },
    "Oil Spike (+20%)": {"spx_shock": 0.0, "rates_shock_bps": 0.0, "oil_shock": 0.20},
    "Recession Combo (-10% SPX, -75bps Rates)": {
        "spx_shock": -0.10,
        "rates_shock_bps": -75.0,
        "oil_shock": -0.10,
    },
    "Custom": None,  # Placeholder for custom inputs
}

# --- 4. Streamlit App Layout and Logic ---

# Set page config for wide layout
st.set_page_config(layout="wide")

st.title("Interactive Risk Dashboard")

# --- Sidebar Controls ---
st.sidebar.header("Controls")

# Portfolio Selection
portfolio_list = [f"Portfolio {chr(ord('A') + i)}" for i in range(5)]  # Dummy names
selected_portfolio = st.sidebar.selectbox(
    "Select Portfolio:",
    options=portfolio_list,
    index=0,  # Default to Portfolio A
)

st.sidebar.markdown("---")  # Divider

# Scenario Selection
st.sidebar.subheader("Scenario Analysis")
scenario_name = st.sidebar.selectbox(
    "Select Scenario:",
    options=list(PREDEFINED_SCENARIOS.keys()),
    index=0,  # Default to Baseline
)

# Custom Scenario Inputs (conditionally displayed)
custom_spx_shock = 0.0
custom_rates_shock = 0.0
custom_oil_shock = 0.0
if scenario_name == "Custom":
    st.sidebar.markdown("**Custom Scenario Inputs:**")
    custom_spx_shock = st.sidebar.number_input(
        "S&P 500 Shock (%):", value=0.0, step=1.0, format="%.1f"
    )
    custom_rates_shock = st.sidebar.number_input(
        "Rates Shock (bps):", value=0.0, step=1.0, format="%.1f"
    )
    custom_oil_shock = st.sidebar.number_input(
        "Oil Shock (%):", value=0.0, step=1.0, format="%.1f"
    )

# Run Button - Use session state to store results
run_button = st.sidebar.button("Run Scenario Analysis", key="run_button")

# Initialize session state for scenario results if it doesn't exist
if "scenario_results" not in st.session_state:
    st.session_state.scenario_results = None
if "last_run_portfolio" not in st.session_state:
    st.session_state.last_run_portfolio = None
if "last_run_scenario_name" not in st.session_state:
    st.session_state.last_run_scenario_name = None
if "last_custom_shocks" not in st.session_state:
    st.session_state.last_custom_shocks = (
        0.0,
        0.0,
        0.0,
    )  # Tuple for immutability checks

# --- Main Panel Display ---

# --- Historical Risk Section ---
st.header(f"Historical Risk Metrics: {selected_portfolio}")

# Fetch historical data using the cached function
df_hist = generate_dummy_risk_history(selected_portfolio)

col1, col2 = st.columns(2)  # Create two columns for side-by-side charts

with col1:
    st.subheader("VaR & Expected Shortfall")
    fig_var_es = go.Figure()
    fig_var_es.add_trace(
        go.Scatter(
            x=df_hist["Date"],
            y=df_hist["VaR_99_USD"],
            mode="lines",
            name="VaR 99% (USD)",
            line=dict(color="orange"),
        )
    )
    fig_var_es.add_trace(
        go.Scatter(
            x=df_hist["Date"],
            y=df_hist["ES_99_USD"],
            mode="lines",
            name="ES 99% (USD)",
            line=dict(color="red"),
        )
    )
    fig_var_es.update_layout(
        xaxis_title="Date",
        yaxis_title="Amount (USD)",
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
        margin=dict(l=10, r=10, t=30, b=10),
        height=350,
    )  # Adjusted margin and height
    st.plotly_chart(fig_var_es, use_container_width=True)  # Use container width

with col2:
    st.subheader("Drawdown")
    fig_drawdown = go.Figure()
    fig_drawdown.add_trace(
        go.Scatter(
            x=df_hist["Date"],
            y=df_hist["Drawdown_Pct"],
            mode="lines",
            name="Drawdown",
            fill="tozeroy",
            line=dict(color="firebrick"),
        )
    )
    fig_drawdown.update_layout(
        xaxis_title="Date",
        yaxis_title="Drawdown (%)",
        yaxis_tickformat=".1%",
        showlegend=False,
        margin=dict(l=10, r=10, t=30, b=10),
        height=350,
    )  # Adjusted margin and height
    st.plotly_chart(fig_drawdown, use_container_width=True)  # Use container width


st.markdown("---")  # Divider

# --- Scenario Analysis Section ---
st.header("Stress Tests & Scenario Analysis")

# Logic for handling the button press and storing results
if run_button:
    current_custom_shocks = (custom_spx_shock, custom_rates_shock, custom_oil_shock)
    # Determine scenario parameters
    if scenario_name == "Custom":
        shocks = {
            "spx_shock": (custom_spx_shock or 0.0) / 100.0,
            "rates_shock_bps": custom_rates_shock or 0.0,
            "oil_shock": (custom_oil_shock or 0.0) / 100.0,
        }
        current_scenario_display_name = f"Custom ({custom_spx_shock}%, {custom_rates_shock}bps, {custom_oil_shock}%)"

    elif scenario_name in PREDEFINED_SCENARIOS:
        shocks = PREDEFINED_SCENARIOS[scenario_name]
        current_scenario_display_name = scenario_name
    else:
        shocks = {"spx_shock": 0.0, "rates_shock_bps": 0.0, "oil_shock": 0.0}
        current_scenario_display_name = "None (Baseline)"

    # Get current positions and run simulation
    df_positions = generate_dummy_positions(
        selected_portfolio
    )  # Regenerate positions for the current portfolio
    with st.spinner(
        f"Running scenario '{current_scenario_display_name}' for {selected_portfolio}..."
    ):
        df_results = simulate_scenario_pnl(df_positions, **shocks)

        # --- Create P&L Histogram ---
        total_pnl = df_results["ScenarioPnL"].sum()
        fig_hist = px.histogram(
            df_results,
            x="ScenarioPnL",
            nbins=30,
            title=f"P&L Distribution",
            labels={"ScenarioPnL": "Position P&L (USD)"},
        )
        fig_hist.update_layout(
            yaxis_title="Number of Positions",
            margin=dict(l=10, r=10, t=50, b=10),
            height=400,  # Add title margin
            title_font_size=16,
            title_x=0.5,  # Center title
        )

        # --- Create Impact Scatter Plot ---
        fig_scatter = px.scatter(
            df_results,
            x="MarketValueUSD",
            y="ScenarioPnL",
            color="AssetClass",
            hover_name="Ticker",
            hover_data=["MarketValueUSD", "ScenarioPnL"],  # Add hover data explicitly
            size="MarketValueUSD",
            size_max=15,
            title=f"Impact: P&L vs Market Value",
            labels={
                "MarketValueUSD": "Market Value (USD)",
                "ScenarioPnL": "Scenario P&L (USD)",
            },
        )
        fig_scatter.update_layout(
            xaxis_title="Market Value (USD)",
            yaxis_title="Scenario P&L (USD)",
            margin=dict(l=10, r=10, t=50, b=10),
            height=400,  # Add title margin
            title_font_size=16,
            title_x=0.5,  # Center title
        )
        fig_scatter.add_hline(y=0, line_dash="dash", line_color="grey")

        # --- Create Summary Table ---
        summary = (
            df_results.groupby("AssetClass")["ScenarioPnL"]
            .agg(["sum", "mean", "count"])
            .reset_index()
        )
        summary.rename(
            columns={"sum": "Total PnL", "mean": "Avg PnL", "count": "N Positions"},
            inplace=True,
        )

        total_row = pd.DataFrame(
            {
                "AssetClass": ["**TOTAL**"],  # Bold Total
                "Total PnL": [summary["Total PnL"].sum()],
                "Avg PnL": [np.nan],  # No average of averages
                "N Positions": [summary["N Positions"].sum()],
            }
        )
        summary_df = pd.concat([summary, total_row], ignore_index=True)

        # Store results in session state
        st.session_state.scenario_results = {
            "portfolio": selected_portfolio,
            "scenario_name": current_scenario_display_name,  # Use descriptive name
            "fig_hist": fig_hist,
            "fig_scatter": fig_scatter,
            "summary_df": summary_df,
            "total_pnl": total_pnl,
        }
        st.session_state.last_run_portfolio = selected_portfolio
        st.session_state.last_run_scenario_name = current_scenario_display_name
        st.session_state.last_custom_shocks = (
            current_custom_shocks if scenario_name == "Custom" else None
        )


# Display scenario results stored in session state
if st.session_state.scenario_results:
    results = st.session_state.scenario_results
    st.subheader(
        f"Results for: {results['portfolio']} - Scenario: {results['scenario_name']}"
    )
    st.metric("Total Scenario P&L", f"${results['total_pnl']:,.0f}")

    col3, col4 = st.columns([0.6, 0.4])  # Adjust column widths if needed

    with col3:
        st.plotly_chart(results["fig_hist"], use_container_width=True)
        st.plotly_chart(results["fig_scatter"], use_container_width=True)

    with col4:
        st.subheader("Scenario P&L Summary")
        # Format numeric columns before display (using style for better visuals)
        formatted_summary = (
            results["summary_df"]
            .style.format(
                {
                    "Total PnL": "${:,.0f}",
                    "Avg PnL": "${:,.0f}",
                    "N Positions": "{:,.0f}",
                }
            )
            .hide(axis="index")
        )  # Hide the default index
        st.dataframe(formatted_summary, use_container_width=True)

        # Optional: Display the positions data used for the run
        # st.subheader("Positions Data Used in Calculation")
        # st.dataframe(generate_dummy_positions(results['portfolio']).style.format({
        #     'MarketValueUSD':'${:,.2f}',
        #     'ScenarioPnL':'${:,.2f}', # If Pnl was added back to original df
        # }, precision=3))


else:
    st.info(
        "Select scenario parameters in the sidebar and click 'Run Scenario Analysis' to see results."
    )
