import streamlit as st
import pandas as pd
import sqlite3
from io import BytesIO
import unicodedata
from rapidfuzz import process, fuzz
import streamlit.components.v1 as components
import time

CSV_DATA = "catalogue_cartes_mis_a_jour.csv"
DB_PATH = "users_cards.db"

st.set_page_config(page_title="Catalogue Full Art Pokémon", layout="wide")

# -------- DB INIT
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

def get_users():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM users", conn)
    conn.close()
    return df

def add_user(prenom, nom, age, photo_bytes):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO users (prenom, nom, age, photo) VALUES (?, ?, ?, ?)",
                 (prenom, nom, age, photo_bytes))
    conn.commit()
    conn.close()

def delete_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.execute("DELETE FROM user_cards WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_user_cards(user_id):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM user_cards WHERE user_id = ?", conn, params=(user_id,))
    conn.close()
    return df

def update_user_card(user_id, nom_complet, souhaite, possede):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
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
    df["année"] = df["Date de sortie"].str.extract(r"(\d{4})", expand=False)
    df["extension_annee"] = df["année"].fillna("") + " - " + df["extension"]
    return df

df_cards = load_cards()

# -------- Utilisateur
st.sidebar.subheader("👤 Utilisateur actif")
users = get_users()

with st.sidebar.expander("➕ Créer un utilisateur"):
    prenom = st.text_input("Prénom")
    nom = st.text_input("Nom")
    age = st.number_input("Âge", min_value=3, max_value=99)
    photo = st.file_uploader("📷 Photo", type=["jpg", "jpeg", "png"])
    if st.button("Créer l'utilisateur"):
        if prenom and nom:
            add_user(prenom, nom, age, photo.read() if photo else None)
            st.rerun()
        else:
            st.warning("Prénom et nom requis")

if users.empty:
    st.warning("Aucun utilisateur. Créez-en un.")
    st.stop()

user_options = [f"{row['prenom']} {row['nom']}" for _, row in users.iterrows()]
selected_name = st.sidebar.selectbox("Choisir un utilisateur", user_options)
active_user = users.iloc[user_options.index(selected_name)]
active_user_id = int(active_user["id"])
if active_user["photo"]:
    st.sidebar.image(BytesIO(active_user["photo"]), width=120)

with st.sidebar.expander("⚙️ Gérer utilisateur"):
    if st.button("❌ Supprimer cet utilisateur"):
        delete_user(active_user_id)
        st.rerun()

# -------- Données utilisateur
df_user_cards = get_user_cards(active_user_id)
df = df_cards.copy()
df["souhaite"] = df["nom_complet"].isin(df_user_cards[df_user_cards["souhaite"] == 1]["nom_complet"])
df["possede"] = df["nom_complet"].isin(df_user_cards[df_user_cards["possede"] == 1]["nom_complet"])

# -------- Détection viewport (JS hack)
if "viewport_width" not in st.session_state:
    components.html("""
        <script>
        const width = window.innerWidth;
        const streamlitDoc = window.parent.document;
        const input = streamlitDoc.querySelector('input[data-testid="stTextInput"]');
        if (input) {
            input.value = width;
            input.dispatchEvent(new Event('input', { bubbles: true }));
        }
        </script>
        <input style="display:none" />
    """, height=0)
    time.sleep(0.5)
    st.session_state.viewport_width = 1200  # fallback

viewport = st.text_input("viewport", value=str(st.session_state.viewport_width), key="vp")
try:
    st.session_state.viewport_width = int(viewport)
except:
    st.session_state.viewport_width = 1200

# -------- Recherche approximative avec autocomplétion
search_base = df["nom"].fillna("").tolist() + df["extension"].fillna("").tolist() + df["numero"].fillna("").astype(str).tolist()
search_input = st.selectbox("Recherche approximative", [""] + search_base, key="search_box")

search_query = ""
if search_input:
    best_match = process.extractOne(search_input, search_base, scorer=fuzz.WRatio)
    if best_match and best_match[1] > 60:
        search_query = best_match[0]

# -------- Vue
menu = st.sidebar.radio("Vue", ["Catalogue complet", "🧾 Liste d’achats", "📦 Ma Collection"])

# -------- Filtres
exts = sorted(df["extension_annee"].dropna().unique())
ills = sorted(df["Illustrateur"].dropna().unique())
st.sidebar.markdown("---")
selected_extensions = st.sidebar.multiselect("Extensions", exts)
selected_illustrateurs = st.sidebar.multiselect("Illustrateurs", ills)

# -------- Filtres supplémentaires pour collection
selected_sort_fields = []
if menu == "📦 Ma Collection":
    with st.sidebar.expander("🔠 Tri Ma Collection"):
        selected_sort_fields = st.multiselect("Trier par…", ["Scène", "Couleur d’ambiance"])

# -------- Application des filtres
def normalize(text):
    return unicodedata.normalize("NFKD", str(text)).encode("ASCII", "ignore").decode().lower()

def apply_filters(data):
    df_filtered = data.copy()
    if selected_extensions:
        df_filtered = df_filtered[df_filtered["extension_annee"].isin(selected_extensions)]
    if selected_illustrateurs:
        df_filtered = df_filtered[df_filtered["Illustrateur"].isin(selected_illustrateurs)]
    if search_query:
        norm = normalize(search_query)
        df_filtered = df_filtered[
            df_filtered["nom"].apply(normalize).str.contains(norm, na=False) |
            df_filtered["extension"].apply(normalize).str.contains(norm, na=False) |
            df_filtered["numero"].astype(str).str.contains(search_query)
        ]
    return df_filtered

df_filtered = apply_filters(df)

if menu == "🧾 Liste d’achats":
    df_filtered = df_filtered[df_filtered["souhaite"] & (~df_filtered["possede"])]
elif menu == "📦 Ma Collection":
    df_filtered = df_filtered[df_filtered["possede"]]
    sort_map = {
        "Scène": "type_visuel",
        "Couleur d’ambiance": "couleur_simplifiée"
    }
    if selected_sort_fields:
        df_filtered = df_filtered.sort_values(by=[sort_map[field] for field in selected_sort_fields])

# -------- Pagination
CARDS_PER_PAGE = 12
total_pages = max(1, (len(df_filtered) - 1) // CARDS_PER_PAGE + 1)
page = st.number_input("Page", min_value=1, max_value=total_pages, value=1, step=1)
df_paginated = df_filtered.iloc[(page - 1) * CARDS_PER_PAGE : page * CARDS_PER_PAGE]

# -------- Affichage
col_left, col_right = st.columns([8, 2])
with col_left:
    st.subheader("📘 " + menu)
with col_right:
    selected_view = st.segmented_control("Mode", ["Liste", "Grille"], label_visibility="collapsed")
    view_mode = selected_view == "Liste"

def show_card(row, idx, grille=False):
    if grille:
        st.markdown(f"**{row['nom']}**", help=row["nom_complet"])
        st.image(row["image_url"], width=140)
        c1, c2 = st.columns(2)
        with c1:
            st.toggle("🌟", row["souhaite"], key=f"souhaite_{idx}", on_change=update_user_card,
                      args=(active_user_id, row["nom_complet"], int(not row["souhaite"]), int(row["possede"])))
        with c2:
            st.toggle("📦", row["possede"], key=f"possede_{idx}", on_change=update_user_card,
                      args=(active_user_id, row["nom_complet"], int(row["souhaite"]), int(not row["possede"])))
    else:
        c = st.columns([2, 3, 2, 2])
        with c[0]:
            st.image(row["image_url"], width=130)
        with c[1]:
            st.markdown(f"**{row['nom']}**")
            st.markdown(f"*{row['extension']}* — #{row['numero']}")
            st.markdown(f"🖌️ *{row['Illustrateur']}*")
            st.markdown(f"📅 {row['Date de sortie']}")
            if menu == "📦 Ma Collection":
                st.markdown(f"🎨 {row.get('couleur_simplifiée', '')}")
                st.markdown(f"🧩 {row.get('type_visuel', '')}")
        with c[2]:
            st.toggle("🌟 Je la veux", row["souhaite"], key=f"souhaite_{idx}", on_change=update_user_card,
                      args=(active_user_id, row["nom_complet"], int(not row["souhaite"]), int(row["possede"])))
        with c[3]:
            st.toggle("📦 Je l'ai", row["possede"], key=f"possede_{idx}", on_change=update_user_card,
                      args=(active_user_id, row["nom_complet"], int(row["souhaite"]), int(not row["possede"])))

# -------- Affichage Grille/Liste
if view_mode:
    for idx, row in df_paginated.iterrows():
        show_card(row, idx, grille=False)
else:
    width = st.session_state.viewport_width
    if width < 600:
        cols = st.columns(2)
    elif width < 1000:
        cols = st.columns(3)
    else:
        cols = st.columns(4)
    for i, (_, row) in enumerate(df_paginated.iterrows()):
        with cols[i % len(cols)]:
            show_card(row, i, grille=True)