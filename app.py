import streamlit as st
import pandas as pd
import math
import io
import os
import glob
import re
from datetime import datetime

st.set_page_config(page_title="Amazon Ads Dashboard", layout="wide")

st.title("Amazon Ads Management Dashboard")

def process_acos(val):
    """Safely parse ACoS values to decimal format."""
    if pd.isna(val):
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        val_clean = val.replace('%', '').replace(',', '').strip()
        try:
            v = float(val_clean)
            if '%' in val:
                return v / 100.0
            return v
        except:
            return 0.0
    return 0.0

def parse_currency(val):
    """Safely parse currency fields like '$4.00' to float."""
    if pd.isna(val):
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        val_clean = val.replace('$', '').replace('€', '').replace('£', '').strip()
        try:
            return float(val_clean)
        except:
            return 0.0
    return 0.0

def get_most_recent_csv_by_date(data_dir="DATA"):
    if not os.path.exists(data_dir):
        return None
        
    csv_files = glob.glob(os.path.join(data_dir, "*.csv"))
    if not csv_files:
        return None
        
    def extract_date(filepath):
        filename = os.path.basename(filepath)
        
        # Try common formats: Month_DD_YYYY
        # e.g. Campaign_May_19_2026.csv
        match_alpha = re.search(r'([A-Za-z]+)_(\d{1,2})_(\d{4})', filename)
        if match_alpha:
            try:
                date_str = f"{match_alpha.group(1)} {match_alpha.group(2)} {match_alpha.group(3)}"
                return datetime.strptime(date_str, "%b %d %Y")
            except:
                pass
                
        # Fallback to file modified time if we can't parse the title
        return datetime.fromtimestamp(os.path.getmtime(filepath))
        
    # Sort files based on the extracted date, newest first
    csv_files.sort(key=extract_date, reverse=True)
    return csv_files[0]

target_file = get_most_recent_csv_by_date()

if target_file is not None:
    st.info(f"📁 Auto-loaded most recent file: **{os.path.basename(target_file)}**")
    # 1. Load data
    df = pd.read_csv(target_file)
    file_name_for_state = os.path.basename(target_file)
    
    # Identify bidding strategy column (Standard: 'Bidding strategy', but handle variations)
    bid_strategy_col = next((c for c in df.columns if 'bid strategy' in c.lower() or 'bidding strategy' in c.lower()), None)
    
    # 2. Critical Safety Flags
    if bid_strategy_col and df[bid_strategy_col].astype(str).str.contains("maximize off-site impressions", case=False, na=False).any():
        st.error('🚨 CRITICAL WARNING: Dataset contains campaigns with "maximize off-site impressions" strategy! Please review immediately.', icon="🚨")
    
    # Check if necessary columns exist (using 'Max Bid', but gracefully fail if missing)
    if 'Max Bid' not in df.columns:
        st.warning("⚠️ Could not find a 'Max Bid' column. Your file might be a Campaign-level report instead of a Keyword/Targeting level report. Please upload a standard bulk sheet.")
        # Fallback to Campaign budget amount for demonstration purposes if Max Bid is absent
        if 'Campaign budget amount' in df.columns:
            st.info("💡 Found 'Campaign budget amount'. Using it as a temporary stand-in for 'Max Bid' so you can see the logic work!")
            df['Max Bid'] = df['Campaign budget amount']
    
    if 'Max Bid' in df.columns and 'ACoS' in df.columns:
        # Initialize custom columns if they don't exist yet in session state for this file
        if 'processed_df' not in st.session_state or st.session_state.get('last_uploaded_name') != file_name_for_state:
            df['BSR Push (Loss Leader)'] = False
            
            # 3. Automated Logic & Default States
            df['parsed_acos'] = df['ACoS'].apply(process_acos)
            
            def calculate_suggested_bid(row):
                # Placeholder for complex logic branches
                # TODO: Bleeder keywords - High impressions / zero sales
                # TODO: Hidden Gems - High CTR
                
                max_bid = parse_currency(row['Max Bid'])
                acos = row['parsed_acos']
                
                # Baseline logic: If ACoS > 25% and ACoS < 35%, decrease by 5% rounded down to nearest cent
                if 0.25 < acos < 0.35:
                    new_bid = max_bid * 0.95
                    return math.floor(new_bid * 100) / 100.0
                
                return max_bid
                
            df['Suggested Bid'] = df.apply(calculate_suggested_bid, axis=1)
            
            # Store in session state to allow edits
            st.session_state.processed_df = df
            st.session_state.last_uploaded_name = file_name_for_state
        
        # 4. Manual Overrides (Interactive UI)
        st.subheader("Bulk Operations Editor")
        st.caption("Edit 'Suggested Bid' or toggle 'BSR Push (Loss Leader)' below. All other columns are read-only for safety.")
        
        # Configure column editing permissions
        editor_df = st.session_state.processed_df.copy()
        
        # Drop temporary parsing columns for display
        if 'parsed_acos' in editor_df.columns:
            editor_df = editor_df.drop(columns=['parsed_acos'])
        
        # Place custom columns at the front for easy access
        cols_order = ['BSR Push (Loss Leader)', 'Suggested Bid', 'Max Bid', 'ACoS']
        cols_order += [c for c in editor_df.columns if c not in cols_order]
        editor_df = editor_df[cols_order]
        
        disabled_cols = [c for c in editor_df.columns if c not in ['BSR Push (Loss Leader)', 'Suggested Bid']]
        
        edited_df = st.data_editor(
            editor_df,
            disabled=disabled_cols,
            hide_index=True,
            use_container_width=True,
            height=600
        )
        
        # 5. Export Mechanics
        st.subheader("Export")
        
        def prepare_export_df(df):
            export_df = df.copy()
            # If BSR Push is False, apply Suggested Bid, otherwise keep original Max Bid
            export_df['Max Bid'] = export_df.apply(
                lambda r: r['Max Bid'] if r['BSR Push (Loss Leader)'] else r['Suggested Bid'], 
                axis=1
            )
            # Strip out custom columns
            columns_to_drop = ['BSR Push (Loss Leader)', 'Suggested Bid']
            export_df = export_df.drop(columns=columns_to_drop)
            return export_df
            
        final_export_df = prepare_export_df(edited_df)
        
        csv_buffer = io.StringIO()
        final_export_df.to_csv(csv_buffer, index=False)
        
        st.download_button(
            label="⬇️ Export to Amazon",
            data=csv_buffer.getvalue(),
            file_name="bulk_upload_ready.csv",
            mime="text/csv",
            type="primary"
        )
    else:
        if 'ACoS' not in df.columns:
            st.warning("⚠️ Could not find an 'ACoS' column in your dataset.")
else:
    st.warning("Could not find any CSV files in the `DATA` directory. Please add your bulk operations CSV there to get started.")
