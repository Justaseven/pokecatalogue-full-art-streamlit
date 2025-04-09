import streamlit as st
import pandas as pd
import sqlite3
from io import BytesIO
import unicodedata
from rapidfuzz import process

CSV_DATA = "catalogue_cartes_mis_a_jour.csv"
DB_PATH = "users_cards.db"

st.set_page_config(page_title="Catalogue Full Art Pokémon", layout="wide")

# ------------------ INITIALISATION DB ------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prenom TEXT,
            nom TEXT,
            age INTEGER,
            photo BLOB
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_cards (
            user_id INTEGER,
            nom_complet TEXT,
            souhaite INTEGER DEFAULT 0,
            possede INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, nom_complet)
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ------------------ FONCTIONS DB ------------------
def get_users():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM users", conn)
    conn.close()
    return df

def add_user(prenom, nom, age, photo_bytes):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO users (prenom, nom, age, photo) VALUES (?, ?, ?, ?)",
              (prenom, nom, age, photo_bytes))
    conn.commit()
    conn.close()

def delete_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id = ?", (user_id,))
    c.execute("DELETE FROM user_cards WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_user_cards(user_id):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM user_cards WHERE user_id = ?", conn, params=(user_id,))
    conn.close()
    return df

def update_user_card(user_id, nom_complet, souhaite, possede):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO user_cards (user_id, nom_complet, souhaite, possede)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id, nom_complet) DO UPDATE SET
            souhaite = excluded.souhaite,
            possede = excluded.possede
    """, (user_id, nom_complet, souhaite, possede))
    conn.commit()
    conn.close()

@st.cache_data
def load_cards():
    df = pd.read_csv(CSV_DATA)
    df["extension_annee"] = df["extension"]
    df["année"] = df["Date de sortie"].str.extract(r"(\d{4})", expand=False)
    df["extension_annee"] = df["année"].fillna("") + " - " + df["extension"]
    return df

df_cards = load_cards()

# ------------------ UTILISATEUR ACTIF ------------------
st.sidebar.subheader("👤 Utilisateur actif")
users = get_users()

with st.sidebar.expander("➕ Créer un utilisateur"):
    prenom = st.text_input("Prénom")
    nom = st.text_input("Nom")
    age = st.number_input("Âge", min_value=3, max_value=99)
    photo = st.file_uploader("📷 Photo", type=["jpg", "jpeg", "png"])
    if st.button("Créer l'utilisateur"):
        if prenom and nom:
            photo_bytes = photo.read() if photo else None
            add_user(prenom, nom, age, photo_bytes)
            st.rerun()
        else:
            st.warning("Prénom et nom requis")

if users.empty:
    st.warning("Aucun utilisateur disponible. Créez un utilisateur.")
    st.stop()

user_options = [f"{row['prenom']} {row['nom']}" for _, row in users.iterrows()]
selected_name = st.sidebar.selectbox("Choisir un utilisateur", user_options)
selected_index = user_options.index(selected_name)
active_user = users.iloc[selected_index]
active_user_id = int(active_user["id"])

if active_user["photo"]:
    st.sidebar.image(BytesIO(active_user["photo"]), width=120)

with st.sidebar.expander("⚙️ Gérer utilisateur"):
    if st.button("❌ Supprimer cet utilisateur"):
        delete_user(active_user_id)
        st.rerun()

# ------------------ CHARGEMENT DES DONNÉES ------------------
df_user_cards = get_user_cards(active_user_id)
df = df_cards.copy()
df["souhaite"] = df["nom_complet"].isin(df_user_cards[df_user_cards["souhaite"] == 1]["nom_complet"])
df["possede"] = df["nom_complet"].isin(df_user_cards[df_user_cards["possede"] == 1]["nom_complet"])

# ------------------ FILTRES ------------------
menu = st.sidebar.radio("Vue", ["Catalogue complet", "🧾 Liste d’achats", "📦 Ma Collection"])

def normalize(text):
    return unicodedata.normalize("NFKD", str(text)).encode("ASCII", "ignore").decode().lower()

if "search_input" not in st.session_state:
    st.session_state.search_input = ""

search_input = st.sidebar.text_input("Recherche 🔎", value=st.session_state.search_input, key="search_box")
all_options = df["nom"].dropna().unique().tolist() + df["extension"].dropna().unique().tolist()
suggestions = [s[0] for s in process.extract(search_input, all_options, limit=10)] if search_input else []

selected_suggestion = st.sidebar.selectbox("Suggestions", suggestions) if suggestions else None

if selected_suggestion and selected_suggestion != st.session_state.search_input:
    st.session_state.search_input = selected_suggestion
    st.rerun()

# Filtres dynamiques
st.sidebar.markdown("---")
with st.sidebar.expander("🎨 Filtrer par extension"):
    extensions = sorted(df["extension_annee"].dropna().unique())
    selected_extensions = st.multiselect("Extensions", extensions, default=[], key="ext_filter")
    if st.button("Réinitialiser extensions"):
        st.session_state.ext_filter = []

with st.sidebar.expander("🖌️ Filtrer par illustrateur"):
    illustrateurs = sorted(df["Illustrateur"].dropna().unique())
    selected_illustrateurs = st.multiselect("Illustrateurs", illustrateurs, default=[], key="illu_filter")
    if st.button("Réinitialiser illustrateurs"):
        st.session_state.illu_filter = []

def apply_filters(data):
    result = data.copy()
    if st.session_state.ext_filter:
        result = result[result["extension_annee"].isin(st.session_state.ext_filter)]
    if st.session_state.illu_filter:
        result = result[result["Illustrateur"].isin(st.session_state.illu_filter)]
    if st.session_state.search_input:
        norm_search = normalize(st.session_state.search_input)
        result = result[
            result["nom"].apply(normalize).str.contains(norm_search, na=False) |
            result["extension"].apply(normalize).str.contains(norm_search, na=False) |
            result["numero"].astype(str).str.contains(st.session_state.search_input)
        ]
    return result

df_filtered = apply_filters(df)

# ------------------ VUE + PAGINATION ------------------
col_left, col_right = st.columns([8, 2])
with col_left:
    st.subheader("📘 Catalogue complet")
with col_right:
    selected_view = st.segmented_control(
        label="Mode d'affichage",
        options=["Liste", "Grille"],
        default="Liste",
        label_visibility="collapsed",
    )
    view_mode = selected_view == "Liste"

CARDS_PER_PAGE = 12
total_pages = max(1, (len(df_filtered) - 1) // CARDS_PER_PAGE + 1)
page = st.number_input("Page", min_value=1, max_value=total_pages, value=1, step=1)
df_paginated = df_filtered.iloc[(page - 1) * CARDS_PER_PAGE : page * CARDS_PER_PAGE]

# ------------------ AFFICHAGE DES CARTES ------------------
def show_card(row, idx, grille=False):
    if grille:
        with st.container():
            st.markdown(f"**{row['nom']}**", help=row["nom_complet"])
            st.image(row["image_url"] if isinstance(row["image_url"], str) and row["image_url"].startswith("http") else "https://via.placeholder.com/130x180?text=Aucune+image", width=140)
            b1, b2 = st.columns([1, 1])
            with b1:
                st.toggle("🌟", value=row["souhaite"], key=f"souhaite_{idx}", on_change=update_user_card,
                          args=(active_user_id, row["nom_complet"], int(not row["souhaite"]), int(row["possede"])))
            with b2:
                st.toggle("📦", value=row["possede"], key=f"possede_{idx}", on_change=update_user_card,
                          args=(active_user_id, row["nom_complet"], int(row["souhaite"]), int(not row["possede"])))
    else:
        cols = st.columns([2, 3, 2, 2])
        with cols[0]:
            st.image(row["image_url"] if isinstance(row["image_url"], str) and row["image_url"].startswith("http") else "https://via.placeholder.com/130x180?text=Aucune+image", width=130)
        with cols[1]:
            st.markdown(f"**{row['nom']}**")
            st.markdown(f"*{row['extension']}* — #{row['numero']}")
            st.markdown(f"🖌️ *{row['Illustrateur']}*")
            st.markdown(f"📅 {row['Date de sortie']}")
        with cols[2]:
            st.toggle("🌟 Je la veux", value=row["souhaite"], key=f"souhaite_{idx}", on_change=update_user_card,
                      args=(active_user_id, row["nom_complet"], int(not row["souhaite"]), int(row["possede"])))
        with cols[3]:
            st.toggle("📦 Je l'ai", value=row["possede"], key=f"possede_{idx}", on_change=update_user_card,
                      args=(active_user_id, row["nom_complet"], int(row["souhaite"]), int(not row["possede"])))

# ------------------ AFFICHAGE PAR VUE ------------------
if menu == "Catalogue complet":
    if view_mode:
        for idx, row in df_paginated.iterrows():
            show_card(row, idx, grille=False)
    else:
        grid_cols = st.columns(4)
        for i, (_, row) in enumerate(df_paginated.iterrows()):
            with grid_cols[i % 4]:
                show_card(row, i, grille=True)

elif menu == "🧾 Liste d’achats":
    st.subheader("🧾 Liste de souhaits")
    wishlist_df = df_filtered[(df_filtered["souhaite"]) & (~df_filtered["possede"])]
    for i, row in wishlist_df.iterrows():
        show_card(row, i, grille=not view_mode)

elif menu == "📦 Ma Collection":
    st.subheader("📦 Ma Collection")
    owned_df = df_filtered[df_filtered["possede"]]
    for i, row in owned_df.iterrows():
        show_card(row, i, grille=not view_mode)
