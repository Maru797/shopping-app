import streamlit as st
import pandas as pd
import numpy as np
import os
import re

# ページ設定
st.set_page_config(
    page_title="営業形態別 販売予測 & 実績蓄積アプリ",
    page_icon="☕",
    layout="wide"
)

st.title("☕ 営業形態別 販売予測 & 実績蓄積アプリ")
st.write("気温や営業形態（屋台スタイル / コーヒーショップスタイル）に合わせて、次回イベントの販売数をシンプルに予測・記録します。")

CSV_FILE = "menu_sales_with_weather.csv"

# データの読み込み＆自動タグ付け関数
def load_data():
    if os.path.exists(CSV_FILE):
        df = pd.read_csv(CSV_FILE, encoding='utf-8-sig')
    else:
        df = pd.DataFrame(columns=[
            '日付', 'イベント名', '出店場所', '天候', '気温',
            'メニュー名', '販売価格', '販売数', '売上額', '営業形態'
        ])
    
    def parse_temp(val):
        if pd.isna(val):
            return np.nan
        match = re.search(r'(\d+(\.\d+)?)', str(val))
        return float(match.group(1)) if match else np.nan

    def detect_mode(row):
        if '営業形態' in row and pd.notna(row['営業形態']) and str(row['営業形態']).strip() != "":
            return row['営業形態']
        
        event_name = str(row.get('イベント名', ''))
        if '祭り' in event_name or '屋台' in event_name:
            return '屋台'
        else:
            return 'コーヒーショップ'

    df['気温_数値'] = df['気温'].apply(parse_temp)
    df['営業形態'] = df.apply(detect_mode, axis=1)
    return df

df = load_data()

# サイドバー: データ管理
st.sidebar.header("📁 データ管理")

uploaded_file = st.sidebar.file_uploader("CSVファイルをアップロードして上書き", type=["csv"])
if uploaded_file is not None:
    temp_df = pd.read_csv(uploaded_file, encoding='utf-8-sig')
    temp_df.to_csv(CSV_FILE, index=False, encoding='utf-8-sig')
    st.sidebar.success("CSVを上書き保存しました！")
    st.rerun()

if not df.empty:
    csv_bytes = df.drop(columns=['気温_数値'], errors='ignore').to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
    st.sidebar.download_button(
        label="📥 最新CSVデータをダウンロード",
        data=csv_bytes,
        file_name="menu_sales_updated.csv",
        mime="text/csv"
    )

# タブ切り替え
tab_yatai, tab_coffee, tab_record, tab_analysis = st.tabs([
    "🍧 屋台スタイル 予測", 
    "☕ コーヒーショップスタイル 予測", 
    "📝 新規実績の記録", 
    "📊 データ分析・過去実績"
])

# 共通予測計算関数
def calculate_predictions(target_mode, target_temp, scale_factor, data_df):
    if data_df.empty or 'メニュー名' not in data_df.columns:
        return pd.DataFrame()

    menu_list = data_df['メニュー名'].dropna().unique()
    predictions = []

    for menu in menu_list:
        menu_df = data_df[data_df['メニュー名'] == menu].dropna(subset=['販売数']).copy()
        if menu_df.empty:
            continue

        latest_price = menu_df.iloc[-1]['販売価格'] if '販売価格' in menu_df.columns else 0
        
        # 営業形態の重み設定（屋台モード vs コーヒーショップモード）
        if target_mode == '屋台':
            weights = menu_df['営業形態'].apply(lambda x: 3.0 if x == '屋台' else 0.3).values
        else:
            weights = menu_df['営業形態'].apply(lambda x: 3.0 if x == 'コーヒーショップ' else 0.2).values

        base_pred = np.average(menu_df['販売数'], weights=weights)

        # 気温補正
        temp_valid = menu_df.dropna(subset=['気温_数値', '販売数'])
        if len(temp_valid) >= 2 and temp_valid['気温_数値'].nunique() > 1:
            try:
                a, b = np.polyfit(temp_valid['気温_数値'], temp_valid['販売数'], 1, w=weights[:len(temp_valid)])
                temp_pred = a * target_temp + b
                base_pred = (base_pred + temp_pred) / 2.0
            except Exception:
                pass

        predicted_qty = max(0, int(round(base_pred * scale_factor)))
        predicted_sales = int(predicted_qty * latest_price)

        mode_avg = menu_df[menu_df['営業形態'] == target_mode]['販売数'].mean()
        mode_avg_str = round(mode_avg, 1) if pd.notna(mode_avg) else "-"

        predictions.append({
            'メニュー名': menu,
            '販売価格(円)': int(latest_price),
            f'{target_mode}時 平均販売数': mode_avg_str,
            '予測販売数(個)': predicted_qty,
            '予測売上高(円)': predicted_sales
        })

    pred_df = pd.DataFrame(predictions)
    if not pred_df.empty:
        pred_df = pred_df.sort_values('予測販売数(個)', ascending=False).reset_index(drop=True)
    return pred_df

# ----------------------------------------------------
# TAB 1: 屋台スタイル 予測
# ----------------------------------------------------
with tab_yatai:
    st.subheader("🍧 屋台スタイルでの出店予測")
    st.info("💡 **夏祭り・屋台系の過去データ（比重 3.0）** を重視して予測を計算しています。")

    col1, col2 = st.columns(2)
    with col1:
        temp_y = st.number_input("想定気温 (℃)", min_value=-5.0, max_value=45.0, value=30.0, step=1.0, key="temp_y")
    with col2:
        scale_y = st.slider("人出・イベント規模（倍率）", min_value=0.5, max_value=3.0, value=1.0, step=0.1, key="scale_y")

    pred_df_y = calculate_predictions('屋台', temp_y, scale_y, df)

    if not pred_df_y.empty:
        st.markdown("---")
        m1, m2, m3 = st.columns(3)
        m1.metric("総予測販売数", f"{pred_df_y['予測販売数(個)'].sum():,} 個")
        m2.metric("総予測売上額", f"{pred_df_y['予測売上高(円)'].sum():,} 円")
        m3.metric("対象メニュー数", f"{len(pred_df_y)} 種類")

        st.subheader("📋 屋台向け 仕入れ予測リスト")
        st.dataframe(pred_df_y, use_container_width=True)
        st.bar_chart(pred_df_y, x="メニュー名", y="予測販売数(個)", color="#d9534f")

# ----------------------------------------------------
# TAB 2: コーヒーショップスタイル 予測
# ----------------------------------------------------
with tab_coffee:
    st.subheader("☕ コーヒーショップスタイルでの出店予測")
    st.info("💡 **マルシェ・通常イベント系の過去データ（比重 3.0）** を重視して予測を計算しています。")

    col1, col2 = st.columns(2)
    with col1:
        temp_c = st.number_input("想定気温 (℃)", min_value=-5.0, max_value=45.0, value=22.0, step=1.0, key="temp_c")
    with col2:
        scale_c = st.slider("人出・イベント規模（倍率）", min_value=0.5, max_value=3.0, value=1.0, step=0.1, key="scale_c")

    pred_df_c = calculate_predictions('コーヒーショップ', temp_c, scale_c, df)

    if not pred_df_c.empty:
        st.markdown("---")
        m1, m2, m3 = st.columns(3)
        m1.metric("総予測販売数", f"{pred_df_c['予測販売数(個)'].sum():,} 個")
        m2.metric("総予測売上額", f"{pred_df_c['予測売上高(円)'].sum():,} 円")
        m3.metric("対象メニュー数", f"{len(pred_df_c)} 種類")

        st.subheader("📋 コーヒーショップ向け 仕入れ予測リスト")
        st.dataframe(pred_df_c, use_container_width=True)
        st.bar_chart(pred_df_c, x="メニュー名", y="予測販売数(個)", color="#2b5c8f")

# ----------------------------------------------------
# TAB 3: 出店実績の記録
# ----------------------------------------------------
with tab_record:
    st.subheader("📝 新規出店実績の記録")
    st.write("出店終了後、どちらの営業形態で営業したかを選択して登録してください。")

    with st.form("add_event_form", clear_on_submit=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            event_date = st.date_input("日付")
            event_name = st.text_input("イベント名", placeholder="例: 秋の納涼市")
        with col2:
            event_mode = st.selectbox("今回の営業形態", ["屋台", "コーヒーショップ"])
            event_location = st.text_input("出店場所", placeholder="例: 公園広場")
        with col3:
            event_weather = st.selectbox("天候", ["晴れ", "曇り", "雨", "快晴", "寒かった", "その他"])
            event_temp = st.number_input("気温 (℃)", min_value=-10.0, max_value=50.0, value=25.0, step=1.0)

        st.markdown("---")
        st.write("##### 📦 メニュー別販売実績の入力")

        existing_menus = list(df['メニュー名'].dropna().unique()) if not df.empty else []
        input_menus = existing_menus + [""] * 3
        
        new_records = []
        
        for idx, m_name in enumerate(input_menus):
            cols = st.columns([3, 2, 2, 2])
            with cols[0]:
                menu_val = st.text_input(f"メニュー名 #{idx+1}", value=m_name, key=f"menu_{idx}")
            with cols[1]:
                price_val = st.number_input(f"単価(円) #{idx+1}", min_value=0, value=300, step=50, key=f"price_{idx}")
            with cols[2]:
                qty_val = st.number_input(f"販売数 #{idx+1}", min_value=0, value=0, step=1, key=f"qty_{idx}")
            with cols[3]:
                sales_val = price_val * qty_val
                st.write(f"\n売上: **￥{sales_val:,}**")

            if menu_val.strip() != "" and qty_val > 0:
                new_records.append({
                    '日付': event_date.strftime('%Y/%m/%d'),
                    'イベント名': event_name,
                    '営業形態': event_mode,
                    '出店場所': event_location,
                    '天候': event_weather,
                    '気温': f"{event_temp}℃",
                    'メニュー名': menu_val.strip(),
                    '販売価格': price_val,
                    '販売数': qty_val,
                    '売上額': sales_val
                })

        submit_btn = st.form_submit_button("💾 実績データを保存・蓄積")

    if submit_btn:
        if not event_name:
            st.error("イベント名を入力してください。")
        elif not new_records:
            st.error("少なくとも1つのメニューの販売数を1以上に設定してください。")
        else:
            new_df = pd.DataFrame(new_records)
            save_df = pd.concat([df.drop(columns=['気温_数値'], errors='ignore'), new_df], ignore_index=True)
            save_df.to_csv(CSV_FILE, index=False, encoding='utf-8-sig')
            
            st.success(f"🎉 '{event_name}' ({event_mode}スタイル) の実績データを正常に保存しました！")
            st.rerun()

# ----------------------------------------------------
# TAB 4: データ分析・過去実績
# ----------------------------------------------------
with tab_analysis:
    st.subheader("📊 営業形態別の実績比較")
    
    if not df.empty:
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            mode_filter = st.selectbox("営業形態フィルター", ["すべて", "屋台", "コーヒーショップ"])
        
        display_df = df if mode_filter == "すべて" else df[df['営業形態'] == mode_filter]
        st.dataframe(display_df.drop(columns=['気温_数値'], errors='ignore').sort_values('日付', ascending=False), use_container_width=True)

        st.markdown("---")
        st.subheader("☕ 営業形態ごとの平均販売数グラフ")
        
        avg_df = df.groupby(['メニュー名', '営業形態'])['販売数'].mean().unstack().fillna(0)
        st.bar_chart(avg_df)
    else:
        st.info("データがありません。")