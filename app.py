import streamlit as st
import pandas as pd
import sqlite3
from io import BytesIO
import unicodedata
from rapidfuzz import process, fuzz

CSV_DATA = "catalogue_cartes_mis_a_jour.csv"
DB_PATH = "users_cards.db"

st.set_page_config(page_title="Catalogue Full Art Pokémon", layout="wide")

# ---------- INITIALISATION DB ----------
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

# ---------- FONCTIONS DB ----------
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
    df["extension_annee"] = df["Date de sortie"].str.extract(r"(\d{4})", expand=False).fillna("") + " - " + df["extension"]
    return df

df_cards = load_cards()

# ---------- UTILISATEUR ACTIF ----------
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

# ---------- DONNÉES CARTES ----------
df_user_cards = get_user_cards(active_user_id)
df = df_cards.copy()
df["souhaite"] = df["nom_complet"].isin(df_user_cards[df_user_cards["souhaite"] == 1]["nom_complet"])
df["possede"] = df["nom_complet"].isin(df_user_cards[df_user_cards["possede"] == 1]["nom_complet"])

# ---------- RECHERCHE APPROXIMATIVE ----------
st.sidebar.markdown("## Recherche")
all_search_options = df["nom"].dropna().tolist() + df["extension"].dropna().tolist() + df["numero"].astype(str).tolist()
query = st.sidebar.text_input("🔍 Nom, extension ou n° de carte", value="")

filtered_name = ""
if query.strip():
    best_match, score = process.extractOne(query, all_search_options, scorer=fuzz.token_sort_ratio)
    if best_match and score > 65:
        query = best_match
        filtered_name = query

# ---------- FILTRES EXTENSION/ILLUSTRATEUR ----------
st.sidebar.markdown("## Filtres")
extensions = sorted(df["extension_annee"].dropna().unique())
illustrateurs = sorted(df["Illustrateur"].dropna().unique())

selected_extensions = st.sidebar.multiselect("🎨 Extensions", extensions)
selected_illustrateurs = st.sidebar.multiselect("🖌️ Illustrateurs", illustrateurs)

# ---------- MENU ET VUE ----------
menu = st.sidebar.radio("Vue", ["Catalogue complet", "🧾 Liste d’achats", "📦 Ma Collection"])

# ---------- TRI MA COLLECTION ----------
tri_fields = []
if menu == "📦 Ma Collection":
    options = ["Scène", "Couleur d'ambiance"]
    selected_sort = st.multiselect("🔃 Trier par", options, help="L’ordre sélectionné sera respecté.")

    if "Scène" in selected_sort:
        tri_fields.append("type_visuel")
    if "Couleur d'ambiance" in selected_sort:
        tri_fields.append("couleur_simplifiée")

# ---------- FILTRAGE ----------
def normalize(text):
    return unicodedata.normalize("NFKD", str(text)).encode("ASCII", "ignore").decode().lower()

def apply_filters(df):
    if filtered_name:
        df = df[
            df["nom"].apply(normalize).str.contains(normalize(filtered_name)) |
            df["extension"].apply(normalize).str.contains(normalize(filtered_name)) |
            df["numero"].astype(str).str.contains(filtered_name)
        ]
    if selected_extensions:
        df = df[df["extension_annee"].isin(selected_extensions)]
    if selected_illustrateurs:
        df = df[df["Illustrateur"].isin(selected_illustrateurs)]
    return df

df_filtered = df.copy()
if menu == "🧾 Liste d’achats":
    df_filtered = df_filtered[(df_filtered["souhaite"]) & (~df_filtered["possede"])]
elif menu == "📦 Ma Collection":
    df_filtered = df_filtered[df_filtered["possede"]]

df_filtered = apply_filters(df_filtered)

if menu == "📦 Ma Collection" and tri_fields:
    df_filtered = df_filtered.sort_values(by=tri_fields)

# ---------- PAGINATION ----------
CARDS_PER_PAGE = 12
total_pages = max(1, (len(df_filtered) - 1) // CARDS_PER_PAGE + 1)
page = st.number_input("Page", min_value=1, max_value=total_pages, value=1, step=1)
df_paginated = df_filtered.iloc[(page - 1) * CARDS_PER_PAGE : page * CARDS_PER_PAGE]

# ---------- RESPONSIVE GRILLE ----------
viewport_width = st.query_params.get("viewport", ["1024"])[0]
try:
    viewport_width = int(viewport_width)
except:
    viewport_width = 1024

if viewport_width < 576:
    num_cols = 1
elif viewport_width < 768:
    num_cols = 2
elif viewport_width < 1024:
    num_cols = 3
else:
    num_cols = 4

# ---------- AFFICHAGE DES CARTES ----------
def show_card(row, idx, grille=False):
    if grille:
        with st.container():
            st.markdown(f"**{row['nom']}**", help=row["nom_complet"])
            st.image(row["image_url"] if isinstance(row["image_url"], str) and row["image_url"].startswith("http") else "https://via.placeholder.com/130x180?text=Aucune+image", width=140)
            b1, b2 = st.columns(2)
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

# ---------- RENDU FINAL ----------
if st.radio("Mode d'affichage", ["Liste", "Grille"], horizontal=True, index=0) == "Liste":
    for idx, row in df_paginated.iterrows():
        show_card(row, idx, grille=False)
else:
    cols = st.columns(num_cols)
    for i, (_, row) in enumerate(df_paginated.iterrows()):
        with cols[i % num_cols]:
            show_card(row, i, grille=True)