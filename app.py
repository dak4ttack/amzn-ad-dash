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

def get_most_recent_csv_by_date(data_dir="DATA"):
    if not os.path.exists(data_dir):
        return None
        
    csv_files = glob.glob(os.path.join(data_dir, "*.csv"))
    if not csv_files:
        return None
        
    def extract_date(filepath):
        filename = os.path.basename(filepath)
        match_alpha = re.search(r'([A-Za-z]+)_(\d{1,2})_(\d{4})', filename)
        if match_alpha:
            try:
                date_str = f"{match_alpha.group(1)} {match_alpha.group(2)} {match_alpha.group(3)}"
                return datetime.strptime(date_str, "%b %d %Y")
            except:
                pass
        return datetime.fromtimestamp(os.path.getmtime(filepath))
        
    csv_files.sort(key=extract_date, reverse=True)
    return csv_files[0]

target_file = get_most_recent_csv_by_date()

if target_file is not None:
    st.info(f"📁 Auto-loaded most recent file: **{os.path.basename(target_file)}**")
    df = pd.read_csv(target_file)
    file_name_for_state = os.path.basename(target_file)
    
    bid_strategy_col = next((c for c in df.columns if 'bid strategy' in c.lower() or 'bidding strategy' in c.lower()), None)
    if bid_strategy_col and df[bid_strategy_col].astype(str).str.contains("maximize off-site impressions", case=False, na=False).any():
        st.error('🚨 CRITICAL WARNING: Dataset contains campaigns with "maximize off-site impressions" strategy! Please review immediately.', icon="🚨")
    
    if 'Campaign budget amount' in df.columns:
        df.rename(columns={'Campaign budget amount': 'Daily Limit'}, inplace=True)
            
    acos_col = next((c for c in df.columns if c.lower() == 'acos'), None)
    if acos_col and acos_col != 'ACoS':
        df.rename(columns={acos_col: 'ACoS'}, inplace=True)
    
    if 'Daily Limit' in df.columns and 'ACoS' in df.columns:
        if 'processed_df' not in st.session_state or st.session_state.get('last_uploaded_name') != file_name_for_state:
            df['parsed_acos'] = df['ACoS'].apply(process_acos)
            st.session_state.processed_df = df
            st.session_state.last_uploaded_name = file_name_for_state
        
        st.write("") # Vertical spacing
        export_container = st.container()
        st.write("") # Vertical spacing
        
        editor_df = st.session_state.processed_df.copy()
        
        # --- UI FORMATTING FOR EYES ---
        def format_acos_display(val):
            if pd.isna(val) or val == 0:
                return "0"
            percent_val = val * 100
            if percent_val.is_integer():
                return f"{int(percent_val)}%"
            else:
                s = f"{percent_val:.2f}".rstrip('0').rstrip('.')
                return f"{s}%"
                
        editor_df['ACoS'] = editor_df['parsed_acos'].apply(format_acos_display)
        
        if 'Country' in editor_df.columns:
            editor_df['Country'] = editor_df['Country'].replace('United States', 'US')
            
        if 'Status' in editor_df.columns:
            editor_df['Status'] = editor_df['Status'].replace('CAMPAIGN_STATUS_ENABLED', 'Enabled')
            
        cols_to_drop = ['Retailer', 'Detail page views', 'parsed_acos']
        
        cols_to_drop.extend([
            'Purchases (new to brand)',
            'Percent of purchases new to brand',
            'Sales (new to brand) (converted)',
            'Sales (new to brand)',
            'Percent of sales new to brand',
            'Long-term sales (converted)',
            'Long-term sales',
            'Long-term ROAS',
            'User reach',
            'Viewable impressions'
        ])
        
        for col in cols_to_drop:
            if col in editor_df.columns:
                editor_df.drop(columns=[col], inplace=True)
                
        if 'CPM' in editor_df.columns:
            cpm_idx = editor_df.columns.get_loc('CPM')
            cols_after_cpm = editor_df.columns[cpm_idx + 1:]
            for col in cols_after_cpm:
                if col != 'Viewable CTR (vCTR)':
                    editor_df.drop(columns=[col], inplace=True)
        # -------------------------------

        cols_order = ['Total cost (converted)', 'ACoS', 'Purchases', 'Sales (converted)', 'Daily Limit']
        cols_order = [c for c in cols_order if c in editor_df.columns]
        
        right_cols = ['State', 'Status', 'Type', 'Portfolio name']
        middle_cols = [c for c in editor_df.columns if c not in cols_order and c not in right_cols]
        
        cols_order += middle_cols
        cols_order += [c for c in right_cols if c in editor_df.columns]
        
        editor_df = editor_df[cols_order]
        
        col_config = {}
        rename_mapping = {}
        for col in editor_df.columns:
            match = re.search(r'^(.*?)\s*\((.*?)\)$', col)
            if match:
                base_name = match.group(1).strip()
                parenthetical = match.group(2).strip()
                new_col_name = f"{base_name} *"
                
                original_new_name = new_col_name
                counter = 1
                while new_col_name in rename_mapping.values() or new_col_name in editor_df.columns:
                    new_col_name = f"{original_new_name} {counter}"
                    counter += 1
                    
                rename_mapping[col] = new_col_name
                col_config[new_col_name] = st.column_config.Column(
                    new_col_name,
                    help=f"({parenthetical})"
                )
                
        editor_df.rename(columns=rename_mapping, inplace=True)
        
        disabled_cols = [c for c in editor_df.columns if c != 'Daily Limit']
        
        calculated_height = (len(editor_df) + 1) * 36 + 3
        edited_df = st.data_editor(
            editor_df,
            disabled=disabled_cols,
            hide_index=True,
            use_container_width=True,
            height=calculated_height,
            column_config=col_config
        )
        
        def prepare_export_df(edited_ui_df):
            # Map edited UI data back to the ORIGINAL raw dataframe to preserve Amazon-required formats
            export_df = st.session_state.processed_df.copy()
            export_df['Daily Limit'] = edited_ui_df['Daily Limit']
            export_df.rename(columns={'Daily Limit': 'Campaign budget amount'}, inplace=True)
            if 'parsed_acos' in export_df.columns:
                export_df.drop(columns=['parsed_acos'], inplace=True)
            return export_df
            
        final_export_df = prepare_export_df(edited_df)
        
        csv_buffer = io.StringIO()
        final_export_df.to_csv(csv_buffer, index=False)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_filename = f"bulk_upload_ready_{timestamp}.csv"
        
        with export_container:
            st.download_button(
                label="⬇️ Export to Amazon",
                data=csv_buffer.getvalue(),
                file_name=export_filename,
                mime="text/csv",
                type="primary"
            )
    else:
        if 'ACoS' not in df.columns:
            st.warning("⚠️ Could not find an 'ACoS' column in your dataset.")
        if 'Daily Limit' not in df.columns:
            st.warning("⚠️ Could not find a 'Campaign budget amount' column in your dataset.")
else:
    st.warning("Could not find any CSV files in the `DATA` directory. Please add your bulk operations CSV there to get started.")
