import streamlit as st
import pandas as pd
# On importerait ici les fonctions des autres fichiers
# from moteur_repartition import generer_planning

# Configuration de la page
st.set_page_config(page_title="Gestion Astreintes", layout="wide")

st.title("🏥 Planning des Astreintes du Centre")

# Création de deux colonnes pour l'interface
col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("Génération")
    mois = st.selectbox("Sélectionnez le mois", ["Novembre 2026", "Décembre 2026"])
    
    if st.button("🚀 Générer le planning"):
        st.success(f"Planning de {mois} généré avec succès !")
        # Le code appellerait ici le moteur mathématique

with col2:
    st.subheader("Compteurs d'Équité")
    # Exemple d'affichage des compteurs réels
    data_compteurs = {
        "Médecin": ["OA", "PM", "VD", "CJ", "MS"],
        "Semaines": [32, 33, 32, 31, 33],
        "Week-ends": [8, 8, 9, 8, 8],
        "Fériés": [2, 1, 2, 2, 2]
    }
    df = pd.DataFrame(data_compteurs)
    st.dataframe(df, hide_index=True)
