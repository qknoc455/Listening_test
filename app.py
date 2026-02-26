import streamlit as st
import os
import random
import pandas as pd
from datetime import datetime

# 設定頁面資訊
st.set_page_config(page_title="語音品質聽測系統 (AB Test)", layout="centered")

# --- 初始化 Session State ---
if 'current_idx' not in st.session_state:
    st.session_state.current_idx = 0
if 'results' not in st.session_state:
    st.session_state.results = []
if 'test_data' not in st.session_state:
    st.session_state.test_data = []
if 'shuffled' not in st.session_state:
    st.session_state.shuffled = False

# --- 功能函式 ---
def load_files(test_type):
    """根據選擇的類型，自動配對兩個資料夾內同名的檔案"""
    base_path = f"data/{test_type}"
    subfolders = [f for f in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, f))]
    
    if len(subfolders) != 2:
        st.error(f"資料夾結構錯誤：{test_type} 下應有兩個資料夾")
        return []
    
    folder1, folder2 = subfolders[0], subfolders[1]
    path1 = os.path.join(base_path, folder1)
    path2 = os.path.join(base_path, folder2)
    
    files = sorted([f for f in os.listdir(path1) if f.endswith(('.wav', '.mp3'))])
    
    paired_data = []
    for f in files:
        if os.path.exists(os.path.join(path2, f)):
            paired_data.append({
                "file_name": f,
                "path_1": os.path.join(path1, f),
                "label_1": folder1,
                "path_2": os.path.join(path2, f),
                "label_2": folder2
            })
    return paired_data

# --- UI 介面 ---
st.title("🎧 語音品質主觀聽測 (AB Test)")

# 1. 選擇測試組別
test_options = ["baseline_LLM", "DNSMOS_LLM", "Noisy_LLM"]
selected_test = st.selectbox("請選擇測試組別：", test_options, on_change=lambda: st.session_state.update(current_idx=0, results=[], shuffled=False))

# 2. 載入資料
if not st.session_state.shuffled:
    all_pairs = load_files(selected_test)
    random.shuffle(all_pairs) # 打亂 10 句的順序
    st.session_state.test_data = all_pairs
    st.session_state.shuffled = True

data = st.session_state.test_data

if data and st.session_state.current_idx < len(data):
    current_trial = data[st.session_state.current_idx]
    
    st.subheader(f"進度：{st.session_state.current_idx + 1} / {len(data)}")
    st.info("請聽以下兩段音訊，並選出您認為品質較好（雜訊較少、聲音較自然）的一項。")

    # 隨機決定 A/B 誰是哪個資料夾 (盲測核心)
    # 使用當前索引作為隨機種子確保重新整理時 A/B 不會互換
    random.seed(st.session_state.current_idx)
    is_swapped = random.choice([True, False])
    
    if is_swapped:
        audio_a, label_a = current_trial['path_2'], current_trial['label_2']
        audio_b, label_b = current_trial['path_1'], current_trial['label_1']
    else:
        audio_a, label_a = current_trial['path_1'], current_trial['label_1']
        audio_b, label_b = current_trial['path_2'], current_trial['label_2']

    # 播放器佈局
    col1, col2 = st.columns(2)
    with col1:
        st.write("**選項 A**")
        st.audio(audio_a)
    with col2:
        st.write("**選項 B**")
        st.audio(audio_b)

    # 評分按鈕
    st.write("---")
    c1, c2, c3 = st.columns(3)
    
    def save_choice(choice_label, winner_name):
        st.session_state.results.append({
            "File": current_trial['file_name'],
            "Winner": winner_name,
            "Choice": choice_label,
            "Test_Group": selected_test
        })
        st.session_state.current_idx += 1

    if c1.button("⬅️ A 較好", use_container_width=True):
        save_choice("A", label_a)
        st.rerun()
    if c2.button("平手 / 無差異", use_container_width=True):
        save_choice("Tie", "No Difference")
        st.rerun()
    if c3.button("B 較好 ➡️", use_container_width=True):
        save_choice("B", label_b)
        st.rerun()

# --- 3. 測試完成報告 ---
elif st.session_state.current_idx >= len(data) and len(data) > 0:
    st.success("🎉 測試已完成！感謝您的參與。")
    
    df = pd.DataFrame(st.session_state.results)
    
    # 統計結果
    st.subheader("本次測試統計")
    win_counts = df['Winner'].value_counts()
    st.bar_chart(win_counts)
    
    st.dataframe(df)

    # 匯出功能
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="下載測試結果 CSV",
        data=csv,
        file_name=f"result_{selected_test}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime='text/csv',
    )
    
    if st.button("重新開始測試"):
        st.session_state.current_idx = 0
        st.session_state.results = []
        st.session_state.shuffled = False
        st.rerun()
