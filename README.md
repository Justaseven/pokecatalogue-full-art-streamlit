# Catalogue Full Art Pokémon

Cette application est une interface Streamlit permettant de gérer une collection de cartes Pokémon Full Art. Elle offre une visualisation interactive, des filtres dynamiques et un suivi utilisateur personnalisé.

---

## Fonctionnalités

- 🔒 Gestion multi-utilisateurs avec photo de profil
- 🌟 Suivi des cartes souhaitées et possédées
- 📘 Affichage des cartes en mode liste ou grille
- 🔎 Recherche avec suggestions intelligentes (autocomplétion via RapidFuzz)
- 🧩 Filtres dynamiques par extension (avec année) et par illustrateur
- 🖼️ Affichage détaillé : nom, extension, numéro, image, illustrateur, date de sortie

---

## Installation

### Prérequis

- Python ≥ 3.9
- pip

### Étapes

1. Cloner le dépôt :
   ```bash
   git clone https://github.com/votre-utilisateur/catalogue-full-art-pokemon.git
   cd catalogue-full-art-pokemon
   ```
   
2. Installer les dépendances :
   ```bash
   pip install -R requirements.txt
   ```
   
3. Lancer l'application :
   ```bash
   streamlit run app.py
   ```

## Structure du projet
```bash
.
├── app.py                            # Code principal de l'application Streamlit
├── catalogue_cartes_mis_a_jour.csv   # Données des cartes enrichies (image, date, illustrateur, etc.)
├── users_cards.db                    # Base SQLite (créée automatiquement au premier lancement)
├── requirements.txt                  # Fichier listant les dépendances Python
└── README.md                         # Ce fichier de documentation
```

## Données incluses

Le fichier CSV contient les colonnes suivantes :
   - nom_complet
   - url
   - nom
   - extension
   - numero
   - image_url
   - image_status
   - souhaitée
   - possédée
   - Illustrateur
   - Date de sortie

## Déploiement

Cette application peut être déployée localement ou sur Streamlit Community Cloud. Pour cela :

   1. Connectez votre dépôt GitHub sur Streamlit Cloud
   2. Spécifiez app.py comme fichier principal
   3. Ajoutez requirements.txt dans les fichiers sources

Déployez !

## Licence

Ce projet est sous licence MIT.
