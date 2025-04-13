import streamlit as st
import pandas as pd
import sqlite3
from io import BytesIO
import unicodedata
from rapidfuzz import process, fuzz

CSV_DATA = "catalogue_cartes_mis_a_jour_avec_categories.csv"
DB_PATH = "users_cards.db"

st.set_page_config(page_title="Catalogue Full Art Pokémon", layout="wide")

# ------------------ INIT DB ------------------
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

# ------------------ DB FONCTIONS ------------------
def get_users():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM users", conn)
    conn.close()
    return df

def add_user(prenom, nom, age, photo_bytes):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO users (prenom, nom, age, photo) VALUES (?, ?, ?, ?)", (prenom, nom, age, photo_bytes))
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

# ------------------ UTILISATEUR ------------------
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

# ------------------ DONNÉES UTILISATEUR ------------------
df_user_cards = get_user_cards(active_user_id)
df = df_cards.copy()
df["souhaite"] = df["nom_complet"].isin(df_user_cards[df_user_cards["souhaite"] == 1]["nom_complet"])
df["possede"] = df["nom_complet"].isin(df_user_cards[df_user_cards["possede"] == 1]["nom_complet"])

# ------------------ MENU & RECHERCHE ------------------
menu = st.sidebar.radio("Vue", ["Catalogue complet", "🧾 Liste d’achats", "📦 Ma Collection"])

def normalize(text):
    return unicodedata.normalize("NFKD", str(text)).encode("ASCII", "ignore").decode().lower()

search_space = df["nom"].dropna().tolist() + df["extension"].dropna().tolist() + df["numero"].astype(str).dropna().tolist()

search_input = st.selectbox("Recherche approximative", [""] + search_space, index=0)
search_query = ""
if search_input:
    match = process.extractOne(search_input, search_space, scorer=fuzz.WRatio)
    if match:
        search_query = match[0]

# ------------------ FILTRES SIDEBAR ------------------
extensions = sorted(df["extension_annee"].dropna().unique())
selected_extensions = st.sidebar.multiselect("Extensions", extensions)

illustrateurs = sorted(df["Illustrateur"].dropna().unique())
selected_illustrateurs = st.sidebar.multiselect("Illustrateurs", illustrateurs)

# ------------------ TRI DANS MA COLLECTION ------------------
sort_order = []
if menu == "📦 Ma Collection":
    st.sidebar.markdown("---")
    sort_order = st.sidebar.multiselect("🔀 Trier ma collection par", ["Scène", "Couleur d'ambiance"])
    sort_fields = []
    for val in sort_order:
        if val == "Scène":
            sort_fields.append("type_visuel")
        elif val == "Couleur d'ambiance":
            sort_fields.append("couleur_simplifiée")

# ------------------ FILTRAGE ------------------
def apply_filters(data):
    result = data.copy()
    if selected_extensions:
        result = result[result["extension_annee"].isin(selected_extensions)]
    if selected_illustrateurs:
        result = result[result["Illustrateur"].isin(selected_illustrateurs)]
    if search_query:
        norm_query = normalize(search_query)
        result = result[
            result["nom"].apply(normalize).str.contains(norm_query, na=False) |
            result["extension"].apply(normalize).str.contains(norm_query, na=False) |
            result["numero"].astype(str).str.contains(search_query)
        ]
    return result

df_filtered = apply_filters(df)

if menu == "🧾 Liste d’achats":
    df_filtered = df_filtered[(df_filtered["souhaite"]) & (~df_filtered["possede"])]
elif menu == "📦 Ma Collection":
    df_filtered = df_filtered[df_filtered["possede"]]
    if sort_fields:
        df_filtered = df_filtered.sort_values(by=sort_fields)

# ------------------ PAGINATION ------------------
CARDS_PER_PAGE = 12
total_pages = max(1, (len(df_filtered) - 1) // CARDS_PER_PAGE + 1)
page = st.number_input("Page", min_value=1, max_value=total_pages, value=1, step=1)
df_paginated = df_filtered.iloc[(page - 1) * CARDS_PER_PAGE : page * CARDS_PER_PAGE]

# ------------------ AFFICHAGE ------------------
col_left, col_right = st.columns([8, 2])
with col_left:
    st.subheader("📘 " + menu)
with col_right:
    view_mode = st.segmented_control("Mode d'affichage", options=["Liste", "Grille"], label_visibility="collapsed") == "Liste"

def show_card(row, idx, grille=False):
    if grille:
        with st.container():
            st.markdown(f"**{row['nom']}**", help=row["nom_complet"])
            st.image(row["image_url"], width=140)
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
            st.image(row["image_url"], width=130)
        with cols[1]:
            st.markdown(f"**{row['nom']}**")
            st.markdown(f"*{row['extension']}* — #{row['numero']}")
            st.markdown(f"🖌️ *{row['Illustrateur']}*")
            st.markdown(f"📅 {row['Date de sortie']}")
            if "couleur_simplifiée" in row and pd.notna(row["couleur_simplifiée"]):
                st.markdown(f"🎨 Couleur : **{row['couleur_simplifiée']}**")
            if "type_visuel" in row and pd.notna(row["type_visuel"]):
                st.markdown(f"🧩 Scène : *{row['type_visuel']}*")
        with cols[2]:
            st.toggle("🌟 Je la veux", value=row["souhaite"], key=f"souhaite_{idx}", on_change=update_user_card,
                      args=(active_user_id, row["nom_complet"], int(not row["souhaite"]), int(row["possede"])))
        with cols[3]:
            st.toggle("📦 Je l'ai", value=row["possede"], key=f"possede_{idx}", on_change=update_user_card,
                      args=(active_user_id, row["nom_complet"], int(row["souhaite"]), int(not row["possede"])))

if view_mode:
    for idx, row in df_paginated.iterrows():
        show_card(row, idx, grille=False)
else:
    import streamlit_javascript as st_js
    page_info = st_js.get_page_info()
    screen_width = page_info.get("clientWidth", 1200)
    num_cols = max(2, min(4, screen_width // 300))
    grid_cols = st.columns(num_cols)
    for i, (_, row) in enumerate(df_paginated.iterrows()):
        with grid_cols[i % num_cols]:
            show_card(row, i, grille=True)