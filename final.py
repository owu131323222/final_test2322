import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import requests
import matplotlib.font_manager as fm
import os
import sqlite3
from datetime import datetime, timedelta

# --- 初期設定 ---
# Streamlit secretsからAPIキーを読み込む
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except KeyError:
    API_KEY = None
    st.error("🔐 Gemini APIキーがStreamlit secretsに設定されていません。`secrets.toml`ファイルを確認するか、Streamlit CloudのSecretsを設定してください。")

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

# アプリ全体のページ設定とテーマ調整
st.set_page_config(
    page_title="学習進捗トラッカー",
    layout="wide",
    initial_sidebar_state="expanded",
    # ▼ここにカラーテーマのカスタマイズを追加できます（任意）
    # primaryColor="#4CAF50",   # メインカラー（例: 落ち着いたグリーン）
    # backgroundColor="#F0F2F6",   # 背景色（明るいグレーで目に優しい）
    # secondaryBackgroundColor="#E0E5EC",   # サブ背景色（セクションの区切りなどに）
    # textColor="#333333",   # テキスト色（読みやすい濃い色）
    # font="sans serif"   # フォント
)

plt.rcParams['font.sans-serif'] = ['IPAexGothic', 'Noto Sans CJK JP', 'Yu Gothic', 'Meiryo', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

if os.name == "nt":
    plt.rcParams['font.family'] = 'Yu Gothic'
elif os.name == 'posix':
    try:
        if fm.findfont('IPAexGothic', fallback_to_default=False):
            plt.rcParams['font.family'] = 'IPAexGothic'
        else:
            raise ValueError("IPAexGothic not found")
    except (ValueError, RuntimeError):
        try:
            if fm.findfont('Noto Sans CJK JP', fallback_to_default=False):
                plt.rcParams['font.family'] = 'Noto Sans CJK JP'
            else:
                raise ValueError("Noto Sans CJK JP not found")
        except (ValueError, RuntimeError):
            plt.rcParams['font.family'] = 'sans-serif'
else:
    plt.rcParams['font.family'] = 'sans-serif'


def init_db():
    conn = sqlite3.connect("learning_log.db")
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS learning_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            subject TEXT,
            topic TEXT,
            score INTEGER,
            study_time INTEGER DEFAULT 0
        )
    """)
    conn.commit()

    try:
        cursor.execute("SELECT study_time FROM learning_log LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE learning_log ADD COLUMN study_time INTEGER DEFAULT 0")
        conn.commit()
    conn.close()

# データをデータベースに保存
def save_data_to_db(date, subject, topic, score, study_time):
    conn = sqlite3.connect("learning_log.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO learning_log (date, subject, topic, score, study_time) VALUES (?, ?, ?, ?, ?)",
                   (date.strftime("%Y-%m-%d"), subject, topic, score, study_time))
    conn.commit()
    conn.close()

# データベースからデータを読み込む
def load_data_from_db():
    conn = sqlite3.connect("learning_log.db")
    df = pd.read_sql_query("SELECT * FROM learning_log", conn)
    conn.close()

    df.rename(columns={"subject": "科目", "score": "理解度", "study_time": "学習時間(分)"}, inplace=True)
    df['date'] = pd.to_datetime(df['date'])
    return df

# --- データ状態管理 ---
init_db()
if 'df' not in st.session_state:
    st.session_state.df = load_data_from_db()

# --- ユーザー入力セクション ---
def input_section():
    with st.form("学習記録", clear_on_submit=True):
        st.subheader("📝 新しい学習記録を追加")
        st.markdown("日々の学習内容を記録して、**成長の軌跡**を残しましょう！")

        col1, col2 = st.columns(2)
        with col1:
            date = st.date_input("🗓️ 学習日", value=datetime.now().date())

            subject_options = ["IT/プログラミング", "ビジネス/経済", "語学", "人文科学", "自然科学", "芸術/デザイン", "その他 (自由記述)"]
            selected_subject = st.selectbox("📚 科目を選択", subject_options)

            subject_to_save = selected_subject
            if selected_subject == "その他 (自由記述)":
                custom_subject = st.text_input("💡 その他の科目を入力してください (例: 心理学、料理)")
                if custom_subject:
                    subject_to_save = custom_subject
                else:
                    st.warning("「その他」を選択した場合は、科目を入力してください。")
                    subject_to_save = None

        with col2:
            topic = st.text_input("📖 学習内容/テーマ (例: TOEIC単語50個、経済学)")
            score = st.slider("✨ 理解度 (1: 🤔まだ難しい 〜 5: 🎉バッチリ理解！)", min_value=1, max_value=5)
            study_time = st.number_input("⏰ 学習時間 (分)", min_value=0, value=60, step=5)

        st.markdown("---")
        submitted = st.form_submit_button("✅ この記録を追加する！")

    if submitted:
        if not topic:
            st.warning("内容を入力してください。")
        elif subject_to_save is None:
            st.warning("科目を選択または入力してください。")
        else:
            save_data_to_db(date, subject_to_save, topic, score, study_time)
            st.session_state.df = load_data_from_db() # データの更新
            if selected_subject == "その他 (自由記述)" and subject_to_save:
                st.success(f"✅ 記録を追加しました！科目「**{subject_to_save}**」の内容が保存されました。")
            else:
                st.success("✅ 記録を追加しました！")
            # ここにあった st.experimental_rerun() は削除しました。
            # st.form の submit_button が自動的にアプリを再実行するため、
            # 明示的な再実行は不要です。

# --- 勉強時間グラフ表示 ---
def show_progress_chart(df):
    st.subheader("📈 科目別 合計学習時間グラフ")
    st.markdown("頑張りをグラフで確認しよう！")

    if df.empty:
        st.info("まだ学習記録がありません。記録を追加するとグラフが表示されます。")
        return

    time_range_option = st.selectbox(
        "グラフの表示期間を選択",
        ["今日", "直近1週間", "直近1ヶ月", "全期間"], # 「全期間」を追加
        key="time_range_select"
    )

    filtered_df = df.copy()
    today = datetime.now().date()

    if time_range_option == "今日":
        filtered_df = df[df['date'].dt.date == today]
        chart_title_suffix = " (今日)"
    elif time_range_option == "直近1週間":
        seven_days_ago = today - timedelta(days=7)
        filtered_df = df[df['date'].dt.date >= seven_days_ago]
        chart_title_suffix = " (直近1週間)"
    elif time_range_option == "直近1ヶ月":
        thirty_days_ago = today - timedelta(days=30)
        filtered_df = df[df['date'].dt.date >= thirty_days_ago]
        chart_title_suffix = " (直近1ヶ月)"
    elif time_range_option == "全期間":
        chart_title_suffix = " (全期間)"


    if filtered_df.empty:
        st.info(f"{time_range_option}の学習記録がありません。")
        return

    total_study_time = filtered_df.groupby("科目")["学習時間(分)"].sum().sort_values(ascending=False) # 降順に変更

    if total_study_time.empty or total_study_time.sum() == 0:
        st.info(f"{time_range_option}に学習時間が記録されていません。")
        return

    fig, ax = plt.subplots(figsize=(10, 6)) # グラフサイズを少し大きく
    total_study_time.plot(kind='bar', ax=ax, color='skyblue') # 色を変更
    ax.set_ylabel("合計学習時間 (分) ⏰") # アイコンを追加
    ax.set_xlabel("科目 📚") # アイコンを追加
    ax.set_title(f"科目別合計学習時間{chart_title_suffix}", fontsize=16) # タイトルフォントサイズ変更
    plt.xticks(rotation=45, ha='right')
    plt.grid(axis='y', linestyle='--', alpha=0.7) # グリッド線を追加
    plt.tight_layout()
    st.pyplot(fig)

# --- 直近の学習記録を表示 ---
def show_recent_records(df):
    st.subheader("🔍 直近の学習記録一覧")
    st.markdown("最新の学習記録をチェック！何に取り組んだか振り返ってみましょう。")
    if df.empty:
        st.info("まだ学習記録がありません。")
        return

    today = datetime.now().date()
    seven_days_ago = today - timedelta(days=7)

    recent_df = df[df['date'].dt.date >= seven_days_ago].sort_values(by='date', ascending=False)

    if recent_df.empty:
        st.info("直近1週間分の学習記録はありません。")
    else:
        display_df = recent_df[['date', '科目', 'topic', '理解度', '学習時間(分)']].copy()
        display_df['date'] = display_df['date'].dt.strftime("%Y-%m-%d")
        st.dataframe(display_df, use_container_width=True)

# --- Gemini APIで課題提案 ---
def suggest_tasks(subject, topic=None):
    st.subheader("💡 AIコーチからのパーソナルアドバイス")
    st.markdown("あなたの苦手を見つけて、次の一歩をサポートします！")

    if API_KEY is None:
        st.warning("🔐 Gemini APIキーが設定されていません。AI機能は利用できません。Streamlit CloudのSecretsに`GEMINI_API_KEY`を設定してください。")
        return

    prompt_base = f"あなたは学習支援AIです。ユーザーは「{subject}」の学習を進めています。"
    if topic:
        prompt = f"{prompt_base}\n特に「{topic}」という内容で理解度が低いようです。この内容の理解を助けるために、初心者にもわかりやすい具体的な3つのおすすめ課題（例: 〇〇を読み込む、△△の練習問題を解く、関連動画を見る）を提案してください。ポジティブで励ますトーンでお願いします。"
    else:
        prompt = f"{prompt_base}\n全体的な理解度を深めるために、わかりやすい具体的な3つのおすすめ課題を提案してください。ポジティブで励ますトーンでお願いします。"

    headers = {"Content-Type": "application/json"}
    data = {"contents": [{"parts": [{"text": prompt}]}]}

    try:
        with st.spinner("AIが分析中です...しばらくお待ちください！"): # AI応答中のスピナー
            response = requests.post(f"{API_URL}?key={API_KEY}", headers=headers, json=data, timeout=30) # タイムアウト設定
            response.raise_for_status()
            result = response.json()

            suggestions = (
                result.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
            )

            if suggestions:
                st.markdown(f"**あなたの苦手科目: {subject}**")
                if topic:
                    st.markdown(f"**特に苦手な内容: {topic}**")
                st.info(suggestions) # st.info でAIの応答を目立たせる
            else:
                st.error("❌ Gemini APIの応答が空でした。プロンプトを見直すか、APIの制限を確認してください。")
    except requests.exceptions.Timeout:
        st.error("⏰ AIからの応答がタイムアウトしました。もう一度お試しください。")
    except requests.exceptions.RequestException as e:
        st.error(f"API呼び出し中にエラーが発生しました: {e}")
        st.error(f"レスポンス内容: {response.text if 'response' in locals() else 'APIからの応答がありませんでした。'}")
    except Exception as e:
        st.error(f"不明なエラーが発生しました: {e}")

# --- アプリケーションメイン処理 ---

# アプリケーションのメイン表示エリア
st.title("📚✨ 学習アシスタント✨📚")
st.markdown("**目標達成を楽しく、スマートに。**")
st.markdown("---")

# サイドバーにアプリの説明とカテゴリを配置
with st.sidebar:
    # st.image("https://example.com/your_logo_or_icon.png", width=150) # アプリのロゴやアイコンがあれば追加
    st.header("✨ アプリでできること")
    st.info("このアプリは、あなたの**学習記録**を管理し、**進捗を可視化**します。AIがあなたの**苦手分野を分析**し、**アドバイス・課題*提案することで、効率的な学習をサポートします！")
    st.markdown("---")
    st.header("🎯 学習カテゴリの例")
    st.write("📖 IT/プログラミング")
    st.write("📈 ビジネス/経済")
    st.write("🗣️ 語学")
    st.write("🧠 人文科学")
    st.write("🔬 自然科学")
    st.write("🎨 芸術/デザイン")
    st.write("その他")
    st.markdown("---")
    st.caption("© 2024 Your Name. 大妻女子大学 社会情報学部 WebプログラミングI")


# タブを使ったレイアウトで各機能を整理
tab1, tab2, tab3 = st.tabs(["📝 記録・追加", "📊 進捗確認", "🤖 AIアドバイス"])

with tab1:
    input_section() # 記録追加セクションを呼び出し

with tab2:
    show_recent_records(st.session_state.df) # 直近の記録を表示
    st.markdown("---") # 区切り線
    show_progress_chart(st.session_state.df) # 学習時間グラフを表示

with tab3:
    # 課題提案のための理解度データは別途計算する
    df_for_ai = st.session_state.df # AI分析用のデータフレームをコピー

    if not df_for_ai.empty:
        avg_scores_for_suggestion = df_for_ai.groupby("科目")["理解度"].mean()
        if not avg_scores_for_suggestion.empty:
            weakest_subject = avg_scores_for_suggestion.idxmin()

            lowest_score_topic = None
            weakest_subject_df = df_for_ai[df_for_ai['科目'] == weakest_subject]
            if not weakest_subject_df.empty:
                lowest_score_record = weakest_subject_df.loc[weakest_subject_df['理解度'].idxmin()]
                lowest_score_topic = lowest_score_record['topic']

            suggest_tasks(weakest_subject, lowest_score_topic)
        else:
            st.info("まだ科目別の理解度データがありません。")
    else:
        st.info("まだ学習記録がありません。AIによる課題提案にはデータが必要です。まずは記録を追加しましょう！")

st.markdown("---")

# --- データ初期化セクション ---
st.subheader("🗑️ 記録のリセット")
st.warning("この操作は、あなたの**全ての学習記録をデータベースから削除します**。元に戻すことはできませんので、注意してください。")

if st.button("🔴 全記録を完全にクリアする", key="clear_all_button"):
    if st.confirm("本当に全ての学習記録を削除してもよろしいですか？この操作は取り消せません。", key="confirm_delete"):
        conn = sqlite3.connect("learning_log.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM learning_log")  # データベースから全レコードを削除
        conn.commit()
        conn.close()
        st.session_state.df = load_data_from_db()  # session_stateのデータも更新
        st.success("✨ すべての学習記録が正常にクリアされました！")
        st.rerun()  # 画面を再描画して変更を反映
    else:
        st.info("記録の削除はキャンセルされました。")
