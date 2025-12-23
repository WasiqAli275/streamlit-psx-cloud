import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, time
import time as tm
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import io
import os
from supabase import create_client, Client
from dotenv import load_dotenv
import pytz
import streamlit.components.v1 as components
import traceback

# Load environment variables
load_dotenv()

# Page configuration
st.set_page_config(
    page_title="PSX Stock Analyzer Cloud",
    page_icon="☁️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS with cloud theme
st.markdown("""
<style>
    /* Custom CSS styles */
    .cloud-card {
        background: white;
        padding: 1.5rem;
        border-radius: 1rem;
        border: 1px solid #e0e0e0;
        box-shadow: 0 4px 20px rgba(0,0,0,0.08);
        margin: 0.5rem 0;
        transition: all 0.3s ease;
    }
    
    .header-container {
        background: linear-gradient(135deg, #d32f2f 0%, #388e3c 100%);
        padding: 1rem 2rem;
        border-radius: 0.8rem;
        margin-bottom: 1.5rem;
        box-shadow: 0 4px 20px rgba(211, 47, 47, 0.3);
    }
    
    .logo-text {
        font-size: 1.5rem;
        font-weight: bold;
        margin: 0;
        background: linear-gradient(45deg, #ff6b6b, #4CAF50, #ff9800, #2196F3);
        background-size: 300% 300%;
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        animation: gradientFlow 5s ease infinite;
    }
</style>
""", unsafe_allow_html=True)

# Debug information
DEBUG = True

# Initialize Supabase client with better error handling
@st.cache_resource
def init_supabase():
    """Initialize Supabase client with detailed error handling"""
    try:
        # Get credentials from environment variables
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")
        
        if DEBUG:
            st.sidebar.write("🔍 Debug Info:")
            st.sidebar.write(f"SUPABASE_URL exists: {'Yes' if supabase_url else 'No'}")
            st.sidebar.write(f"SUPABASE_KEY exists: {'Yes' if supabase_key else 'No'}")
            if supabase_url:
                st.sidebar.write(f"URL starts with: {supabase_url[:20]}...")
        
        if not supabase_url:
            st.error("❌ SUPABASE_URL not found in .env file")
            st.info("Please add: SUPABASE_URL=your_project_url")
            return None
        
        if not supabase_key:
            st.error("❌ SUPABASE_KEY not found in .env file")
            st.info("Please add: SUPABASE_KEY=your_anon_public_key")
            return None
        
        # Create client
        client = create_client(supabase_url, supabase_key)
        
        # Test connection
        try:
            # Try to get count of records
            response = client.table('stock_data').select("*", count="exact").limit(1).execute()
            if DEBUG:
                st.sidebar.success(f"✅ Connected successfully!")
                st.sidebar.write(f"Total records: {response.count if hasattr(response, 'count') else 'N/A'}")
        except Exception as e:
            if DEBUG:
                st.sidebar.warning(f"⚠️ Connection test failed: {str(e)}")
        
        return client
        
    except Exception as e:
        st.error(f"❌ Error initializing Supabase: {str(e)}")
        if DEBUG:
            st.error(f"Detailed error: {traceback.format_exc()}")
        return None

# Initialize
supabase = init_supabase()

# Constants
PKT_TZ = pytz.timezone('Asia/Karachi')
TRADING_START = time(9, 30)
TRADING_END = time(15, 30)

class DataManager:
    """Manages data fetching and aggregation from Supabase"""
    
    @staticmethod
    def test_connection():
        """Test Supabase connection and data availability"""
        if not supabase:
            return False, "No Supabase client"
        
        try:
            # Test query
            response = supabase.table('stock_data').select("*").limit(5).execute()
            
            if not response.data:
                return True, "Connection OK but no data found"
            
            # Check column structure
            if response.data:
                sample = response.data[0]
                columns = list(sample.keys())
                return True, f"Connection OK. Found {len(response.data)} records. Columns: {', '.join(columns[:5])}..."
            
            return True, "Connection OK"
            
        except Exception as e:
            return False, f"Connection error: {str(e)}"
    
    @staticmethod
    def get_all_data(limit=1000):
        """Get all data without time filters"""
        try:
            if supabase is None:
                return None
            
            response = supabase.table('stock_data')\
                .select('*')\
                .order('scraped_at', desc=True)\
                .limit(limit)\
                .execute()
            
            if not response.data:
                return None
            
            df = pd.DataFrame(response.data)
            
            # Convert timestamp to PKT
            if 'scraped_at' in df.columns:
                df['scraped_at'] = pd.to_datetime(df['scraped_at']).dt.tz_convert(PKT_TZ)
            
            if DEBUG and not df.empty:
                st.sidebar.write(f"📊 Got {len(df)} records")
                st.sidebar.write(f"Latest timestamp: {df['scraped_at'].max()}")
                st.sidebar.write(f"Columns: {', '.join(df.columns.tolist()[:10])}...")
            
            return df
            
        except Exception as e:
            st.error(f"Error fetching all data: {str(e)}")
            if DEBUG:
                st.error(traceback.format_exc())
            return None
    
    @staticmethod
    def get_available_batches():
        """Get all available data batches"""
        try:
            if supabase is None:
                return []
            
            # Get distinct timestamps
            response = supabase.table('stock_data')\
                .select('scraped_at')\
                .order('scraped_at', desc=True)\
                .execute()
            
            if not response.data:
                # Try without order
                response = supabase.table('stock_data')\
                    .select('scraped_at')\
                    .execute()
                
                if not response.data:
                    return []
            
            # Extract unique timestamps
            timestamps = []
            seen = set()
            
            for item in response.data:
                try:
                    ts_str = item['scraped_at']
                    if ts_str not in seen:
                        seen.add(ts_str)
                        # Parse timestamp
                        ts = pd.to_datetime(ts_str)
                        # Make timezone aware
                        if ts.tzinfo is None:
                            ts = ts.tz_localize('UTC')
                        # Convert to PKT
                        ts = ts.tz_convert(PKT_TZ)
                        timestamps.append(ts)
                except Exception as e:
                    if DEBUG:
                        st.sidebar.warning(f"Timestamp parsing error: {e}")
                    continue
            
            # Sort descending
            timestamps.sort(reverse=True)
            
            if DEBUG:
                st.sidebar.write(f"Found {len(timestamps)} unique timestamps")
                if timestamps:
                    st.sidebar.write(f"Earliest: {timestamps[-1]}")
                    st.sidebar.write(f"Latest: {timestamps[0]}")
            
            return timestamps[:50]  # Limit to 50 most recent
            
        except Exception as e:
            st.error(f"Error fetching batches: {str(e)}")
            if DEBUG:
                st.error(traceback.format_exc())
            return []
    
    @staticmethod
    def get_data_by_timestamp(target_timestamp):
        """Get data for specific timestamp"""
        try:
            if supabase is None:
                return None
            
            # Convert to UTC for query
            if hasattr(target_timestamp, 'tzinfo') and target_timestamp.tzinfo:
                target_utc = target_timestamp.astimezone(pytz.UTC)
            else:
                # Assume it's in PKT
                target_utc = PKT_TZ.localize(target_timestamp).astimezone(pytz.UTC)
            
            # Query with tolerance
            start_time = target_utc - timedelta(minutes=5)
            end_time = target_utc + timedelta(minutes=5)
            
            response = supabase.table('stock_data')\
                .select('*')\
                .gte('scraped_at', start_time.isoformat())\
                .lte('scraped_at', end_time.isoformat())\
                .execute()
            
            if not response.data:
                return None
            
            df = pd.DataFrame(response.data)
            
            # Convert timestamp
            if 'scraped_at' in df.columns:
                df['scraped_at'] = pd.to_datetime(df['scraped_at']).dt.tz_convert(PKT_TZ)
            
            return df
            
        except Exception as e:
            st.error(f"Error fetching data by timestamp: {str(e)}")
            return None
    
    @staticmethod
    def format_data_for_display(df):
        """Format DataFrame for display"""
        if df is None or df.empty:
            return df
        
        display_df = df.copy()
        
        # Column mapping
        column_mapping = {
            'symbol': 'Symbol',
            'sector': 'Sector', 
            'listed_in': 'Listed_In',
            'ldcp': 'LDCP',
            'open': 'Open',
            'open_price': 'Open',
            'high': 'High',
            'low': 'Low',
            'current': 'Current',
            'current_price': 'Current',
            'change': 'Change',
            'change_percent': 'Change(%)',
            'volume': 'Volume'
        }
        
        # Rename columns that exist
        rename_dict = {}
        for old_col, new_col in column_mapping.items():
            if old_col in display_df.columns:
                rename_dict[old_col] = new_col
        
        if rename_dict:
            display_df = display_df.rename(columns=rename_dict)
        
        # Define desired column order
        desired_columns = [
            'Symbol', 'Sector', 'Listed_In', 'LDCP', 'Open', 
            'High', 'Low', 'Current', 'Change', 'Change(%)', 'Volume'
        ]
        
        # Keep only columns that exist
        existing_cols = [col for col in desired_columns if col in display_df.columns]
        
        return display_df[existing_cols] if existing_cols else display_df
    
    @staticmethod
    def calculate_metrics(df):
        """Calculate market metrics"""
        if df is None or df.empty:
            return {}
        
        metrics = {
            'total_stocks': len(df),
            'gainers': 0,
            'losers': 0,
            'unchanged': 0,
            'total_volume': 0,
            'top_gainer': None,
            'top_loser': None,
            'most_active': None
        }
        
        try:
            # Ensure numeric columns
            if 'change_percent' in df.columns:
                df['change_percent'] = pd.to_numeric(df['change_percent'], errors='coerce')
                metrics['gainers'] = (df['change_percent'] > 0).sum()
                metrics['losers'] = (df['change_percent'] < 0).sum()
                metrics['unchanged'] = (df['change_percent'] == 0).sum()
            
            if 'volume' in df.columns:
                df['volume'] = pd.to_numeric(df['volume'], errors='coerce')
                metrics['total_volume'] = df['volume'].sum()
            
            # Find top performers
            if 'change_percent' in df.columns and not df.empty:
                try:
                    metrics['top_gainer'] = df.loc[df['change_percent'].idxmax()]
                    metrics['top_loser'] = df.loc[df['change_percent'].idxmin()]
                except:
                    pass
            
            if 'volume' in df.columns and not df.empty:
                try:
                    metrics['most_active'] = df.loc[df['volume'].idxmax()]
                except:
                    pass
        
        except Exception as e:
            if DEBUG:
                st.error(f"Error calculating metrics: {e}")
        
        return metrics

def main():
    # Header
    st.markdown("""
    <div class="header-container">
        <h1 class="logo-text">📈 PSX Stock Analyzer Cloud</h1>
        <p style="color: white; margin: 0;">Real-time Market Data Analysis</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Initialize session state
    if 'current_data' not in st.session_state:
        st.session_state.current_data = None
    if 'available_batches' not in st.session_state:
        st.session_state.available_batches = []
    
    # Sidebar
    with st.sidebar:
        st.markdown('<div class="cloud-card">', unsafe_allow_html=True)
        st.title("⚙️ Control Panel")
        
        # Connection status
        st.markdown("---")
        st.subheader("🔗 Database Connection")
        
        if supabase:
            st.success("✅ Connected to Supabase")
            
            # Test connection button
            if st.button("Test Connection", key="test_conn"):
                with st.spinner("Testing..."):
                    success, message = DataManager.test_connection()
                    if success:
                        st.success(f"✅ {message}")
                    else:
                        st.error(f"❌ {message}")
        else:
            st.error("❌ Not Connected")
            st.info("Check your .env file:")
            st.code("""
            SUPABASE_URL=https://your-project.supabase.co
            SUPABASE_KEY=your-anon-key
            """)
        
        # Debug toggle
        st.markdown("---")
        global DEBUG
        DEBUG = st.checkbox("Enable Debug Mode", value=True)
        
        # Data loading options
        st.markdown("---")
        st.subheader("📥 Load Data")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🔄 Load All Data", use_container_width=True):
                with st.spinner("Loading all data..."):
                    st.session_state.current_data = DataManager.get_all_data()
                    if st.session_state.current_data is not None:
                        st.success(f"Loaded {len(st.session_state.current_data)} records")
                    else:
                        st.error("No data found")
        
        with col2:
            if st.button("🕐 Load Batches", use_container_width=True):
                with st.spinner("Fetching batches..."):
                    st.session_state.available_batches = DataManager.get_available_batches()
                    if st.session_state.available_batches:
                        st.success(f"Found {len(st.session_state.available_batches)} batches")
                    else:
                        st.warning("No batches found")
        
        # Batch selection if available
        if st.session_state.available_batches:
            st.markdown("---")
            st.subheader("📅 Select Batch")
            
            # Format for display
            batch_options = []
            for ts in st.session_state.available_batches:
                try:
                    display_text = ts.strftime("%Y-%m-%d %H:%M:%S")
                    batch_options.append((display_text, ts))
                except:
                    continue
            
            if batch_options:
                selected_display = st.selectbox(
                    "Available Timestamps",
                    options=[opt[0] for opt in batch_options],
                    index=0
                )
                
                # Find selected timestamp
                selected_ts = None
                for display_text, ts in batch_options:
                    if display_text == selected_display:
                        selected_ts = ts
                        break
                
                if selected_ts and st.button("📊 Load This Batch", use_container_width=True):
                    with st.spinner(f"Loading {selected_display}..."):
                        st.session_state.current_data = DataManager.get_data_by_timestamp(selected_ts)
                        if st.session_state.current_data is not None:
                            st.success(f"Loaded {len(st.session_state.current_data)} records")
                        else:
                            st.error("Could not load batch data")
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Main content area
    if not supabase:
        st.error("""
        ## Database Connection Required
        
        Please setup your `.env` file:
        
        ```env
        SUPABASE_URL=https://your-project.supabase.co
        SUPABASE_KEY=your-anon-public-key
        ```
        
        **Note:** These are different from database connection strings.
        Get them from your Supabase project dashboard under:
        - Settings > API
        - Use "Project URL" and "anon public key"
        """)
        
        st.info("""
        ### For Scraping Data:
        Use separate scraping code that inserts data into Supabase table `stock_data`.
        
        This app only reads and displays the data.
        """)
        return
    
    # Display current data
    if st.session_state.current_data is not None and not st.session_state.current_data.empty:
        df = st.session_state.current_data
        
        # Show data info
        st.success(f"📊 Displaying {len(df)} stock records")
        
        # Calculate and show metrics
        metrics = DataManager.calculate_metrics(df)
        
        # Metrics cards
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Stocks", metrics['total_stocks'])
        
        with col2:
            st.metric("Gainers", metrics['gainers'], delta=f"+{metrics['gainers']}")
        
        with col3:
            st.metric("Losers", metrics['losers'], delta=f"-{metrics['losers']}")
        
        with col4:
            st.metric("Total Volume", f"{metrics['total_volume']:,.0f}")
        
        # Format for display
        display_df = DataManager.format_data_for_display(df)
        
        # Filters
        st.markdown("---")
        st.subheader("🔍 Filter Data")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Search
            search_term = st.text_input("Search Symbol", "")
            
            # Sector filter
            if 'Sector' in display_df.columns:
                sectors = ['All'] + sorted(display_df['Sector'].dropna().unique().tolist())
                selected_sector = st.selectbox("Sector", sectors)
        
        with col2:
            # Performance filter
            perf_filter = st.selectbox(
                "Performance",
                ["All", "Gainers Only", "Losers Only", "Unchanged"]
            )
            
            # Sort by
            sort_by = st.selectbox(
                "Sort By",
                ["Symbol A-Z", "Change % High-Low", "Volume High-Low", "Current Price High-Low"]
            )
        
        # Apply filters
        filtered_df = display_df.copy()
        
        if search_term and 'Symbol' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['Symbol'].str.contains(search_term, case=False, na=False)]
        
        if 'Sector' in filtered_df.columns and selected_sector != 'All':
            filtered_df = filtered_df[filtered_df['Sector'] == selected_sector]
        
        if 'Change(%)' in filtered_df.columns:
            if perf_filter == "Gainers Only":
                filtered_df = filtered_df[pd.to_numeric(filtered_df['Change(%)'], errors='coerce') > 0]
            elif perf_filter == "Losers Only":
                filtered_df = filtered_df[pd.to_numeric(filtered_df['Change(%)'], errors='coerce') < 0]
            elif perf_filter == "Unchanged":
                filtered_df = filtered_df[pd.to_numeric(filtered_df['Change(%)'], errors='coerce') == 0]
        
        # Apply sorting
        if sort_by == "Symbol A-Z" and 'Symbol' in filtered_df.columns:
            filtered_df = filtered_df.sort_values('Symbol')
        elif sort_by == "Change % High-Low" and 'Change(%)' in filtered_df.columns:
            filtered_df = filtered_df.sort_values('Change(%)', ascending=False)
        elif sort_by == "Volume High-Low" and 'Volume' in filtered_df.columns:
            filtered_df = filtered_df.sort_values('Volume', ascending=False)
        elif sort_by == "Current Price High-Low" and 'Current' in filtered_df.columns:
            filtered_df = filtered_df.sort_values('Current', ascending=False)
        
        # Display table
        st.markdown(f"### 📋 Market Data ({len(filtered_df)} stocks)")
        
        if not filtered_df.empty:
            # Format numeric columns
            display_formatted = filtered_df.copy()
            
            numeric_columns = ['LDCP', 'Open', 'High', 'Low', 'Current', 'Change', 'Change(%)', 'Volume']
            for col in numeric_columns:
                if col in display_formatted.columns:
                    if col == 'Change(%)':
                        display_formatted[col] = display_formatted[col].apply(
                            lambda x: f"{float(x):+.2f}%" if pd.notnull(x) else "N/A"
                        )
                    elif col == 'Change':
                        display_formatted[col] = display_formatted[col].apply(
                            lambda x: f"{float(x):+.2f}" if pd.notnull(x) else "N/A"
                        )
                    elif col == 'Volume':
                        display_formatted[col] = display_formatted[col].apply(
                            lambda x: f"{int(x):,}" if pd.notnull(x) else "N/A"
                        )
                    else:
                        display_formatted[col] = display_formatted[col].apply(
                            lambda x: f"{float(x):.2f}" if pd.notnull(x) else "N/A"
                        )
            
            st.dataframe(display_formatted, use_container_width=True, height=500)
            
            # Download button
            csv = filtered_df.to_csv(index=False)
            st.download_button(
                label="📥 Download CSV",
                data=csv,
                file_name=f"psx_data_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv"
            )
            
            # Visualizations
            st.markdown("---")
            st.subheader("📈 Visualizations")
            
            col1, col2 = st.columns(2)
            
            with col1:
                if 'Volume' in filtered_df.columns and 'Symbol' in filtered_df.columns:
                    top_10 = filtered_df.nlargest(10, 'Volume')
                    fig1 = px.bar(
                        top_10,
                        x='Symbol',
                        y='Volume',
                        title='Top 10 by Volume'
                    )
                    st.plotly_chart(fig1, use_container_width=True)
            
            with col2:
                if 'Change(%)' in filtered_df.columns and 'Symbol' in filtered_df.columns:
                    # Get top and bottom 5
                    top_gainers = filtered_df.nlargest(5, 'Change(%)')
                    top_losers = filtered_df.nsmallest(5, 'Change(%)')
                    combined = pd.concat([top_gainers, top_losers])
                    
                    fig2 = px.bar(
                        combined,
                        x='Symbol',
                        y='Change(%)',
                        color='Change(%)',
                        title='Top Gainers & Losers',
                        color_continuous_scale='RdYlGn'
                    )
                    st.plotly_chart(fig2, use_container_width=True)
        
        else:
            st.warning("No data matches your filters")
    
    else:
        # Welcome/instructions
        st.markdown("""
        <div class="cloud-card">
            <h2>👋 Welcome to PSX Stock Analyzer Cloud</h2>
            
            <h3>📌 Getting Started:</h3>
            
            <h4>1. Database Setup:</h4>
            <p>Make sure your <code>.env</code> file has:</p>
            <pre>
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-public-key
            </pre>
            
            <h4>2. Load Data:</h4>
            <ul>
                <li>Click <b>"Load All Data"</b> in sidebar to see all records</li>
                <li>Click <b>"Load Batches"</b> to see available timestamps</li>
                <li>Select a timestamp and click <b>"Load This Batch"</b></li>
            </ul>
            
            <h4>3. Data Requirements:</h4>
            <p>Your Supabase table <code>stock_data</code> should have these columns:</p>
            <ul>
                <li><code>symbol</code> - Stock symbol</li>
                <li><code>sector</code> - Company sector</li>
                <li><code>current_price</code> or <code>current</code> - Current price</li>
                <li><code>change_percent</code> - Percentage change</li>
                <li><code>volume</code> - Trading volume</li>
                <li><code>scraped_at</code> - Timestamp</li>
            </ul>
            
            <div style="background: #e8f4ff; padding: 15px; border-radius: 8px; margin-top: 20px;">
                <h4>💡 Important Note:</h4>
                <p>This app <b>ONLY READS</b> data from Supabase.</p>
                <p>To add data, you need to run the scraper separately that inserts data into the <code>stock_data</code> table.</p>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # Quick test buttons
        st.markdown("---")
        st.subheader("Quick Tests")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("Test Database Connection", type="primary"):
                with st.spinner("Testing..."):
                    success, message = DataManager.test_connection()
                    if success:
                        st.success(f"✅ {message}")
                    else:
                        st.error(f"❌ {message}")
        
        with col2:
            if st.button("Check Table Structure"):
                if supabase:
                    try:
                        response = supabase.table('stock_data').select("*").limit(1).execute()
                        if response.data:
                            sample = response.data[0]
                            st.json(sample)
                        else:
                            st.warning("Table exists but has no data")
                    except Exception as e:
                        st.error(f"Error: {str(e)}")
                else:
                    st.error("Not connected to Supabase")

if __name__ == "__main__":
    main()
