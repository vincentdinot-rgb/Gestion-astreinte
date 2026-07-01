import streamlit as st
import pandas as pd
import datetime
from moteur_repartition import generer_planning, MEDECINS

# Configuration de la page
st.set_page_config(page_title="Gestionnaire d'Astreintes - OHS", layout="wide")
st.title("🏥 Pilotage du Centre Florentin : Astreintes & Secteurs")

# Initialisation des variables globales en mémoire
if 'absences' not in st.session_state:
    st.session_state['absences'] = []
if 'preferences' not in st.session_state:
    st.session_state['preferences'] = {'OA': [], 'PM': [], 'VD': [3], 'CJ': [], 'MS': []}
if 'df_secteurs' not in st.session_state:
    st.session_state['df_secteurs'] = pd.DataFrame()
if 'df_compteurs' not in st.session_state:
    st.session_state['df_compteurs'] = pd.DataFrame()

JOURS_MAP = {"Lundi": 0, "Mardi": 1, "Mercredi": 2, "Jeudi": 3}

# ==========================================
# BARRE LATÉRALE : CONFIGURATION
# ==========================================
st.sidebar.header("⚙️ Saisie des Données")

# --- 1. Congés ---
st.sidebar.subheader("1. Enregistrer un congé")
med_absent = st.sidebar.selectbox("Médecin concerné", MEDECINS, key="abs_med")
date_deb = st.sidebar.date_input("Date de début", datetime.date.today(), key="abs_deb")
date_fin = st.sidebar.date_input("Date de fin", datetime.date.today(), key="abs_fin")

if st.sidebar.button("Valider le congé", type="secondary"):
    delta = date_fin - date_deb
    for i in range(delta.days + 1):
        jour_abs = date_deb + datetime.timedelta(days=i)
        st.session_state['absences'].append({"medecin": med_absent, "date": jour_abs})
    st.sidebar.success(f"Absence enregistrée pour {med_absent}")

st.sidebar.markdown("---")

# --- 2. Préférences ---
st.sidebar.subheader("2. Jours préférentiels (Semaine)")
med_pref = st.sidebar.selectbox("Médecin", MEDECINS, key="pref_med")
jour_pref = st.sidebar.selectbox("Jour désiré", list(JOURS_MAP.keys()), index=3)

if st.sidebar.button("Enregistrer la préférence"):
    idx_j = JOURS_MAP[jour_pref]
    st.session_state['preferences'][med_pref] = [idx_j]
    st.sidebar.success(f"Préférence enregistrée : {med_pref} -> {jour_pref}")

st.sidebar.markdown("---")

# --- 3. Historique Modifiable ---
st.sidebar.subheader("3. Historique Réalisé (Acquis)")
st.sidebar.caption("Saisissez les astreintes passées pour équilibrer le futur :")

if 'df_historique' not in st.session_state:
    st.session_state['df_historique'] = pd.DataFrame({
        "Médecin": MEDECINS,
        "Semaines": [0, 0, 0, 0, 0],
        "Week-ends": [0, 0, 0, 0, 0]
    })

# Tableau éditable directement dans l'interface
df_hist_edit = st.sidebar.data_editor(st.session_state['df_historique'], hide_index=True)
st.session_state['df_historique'] = df_hist_edit

# Conversion du tableau éditable en dictionnaire pour le moteur mathématique
historique_dict = {}
for index, row in df_hist_edit.iterrows():
    historique_dict[row['Médecin']] = {
        'semaine': int(row['Semaines']),
        'weekend': int(row['Week-ends']),
        'total': int(row['Semaines']) + int(row['Week-ends'])
    }

st.sidebar.markdown("---")
if st.sidebar.button("🗑️ Réinitialiser (Congés & Préf)"):
    st.session_state['absences'] = []
    st.session_state['preferences'] = {'OA': [], 'PM': [], 'VD': [3], 'CJ': [], 'MS': []}
    st.rerun()

# ==========================================
# CORPS PRINCIPAL
# ==========================================
col1, col2 = st.columns([1, 2.5]) # J'ai élargi un peu la colonne 2 pour le grand tableau

with col1:
    st.header("1. Paramètres & Équité")
    st.write("Choisissez la période cible :")
    
    col_a, col_b = st.columns(2)
    with col_a:
        annee_cible = st.number_input("Année", min_value=2024, max_value=2030, value=datetime.date.today().year)
        mois_cible = st.number_input("Mois (1-12)", min_value=1, max_value=12, value=datetime.date.today().month)
    with col_b:
        nb_mois = st.number_input("Nombre de mois", min_value=1, max_value=12, value=6)
    
    st.markdown("---")
    if st.button("🚀 Générer le planning", type="primary", use_container_width=True):
        with st.spinner(f"Calcul mathématique sous contraintes en cours..."):
            df_sec, df_comp = generer_planning(
                annee_cible, 
                mois_cible,
                nb_mois,
                st.session_state['absences'], 
                st.session_state['preferences'],
                historique_dict
            )
            st.session_state['df_secteurs'] = df_sec
            st.session_state['df_compteurs'] = df_comp
        st.success("Planning généré avec succès !")

    if not st.session_state['df_compteurs'].empty:
        st.subheader("📊 Compteurs Cumulés")
        st.dataframe(st.session_state['df_compteurs'], hide_index=True, use_container_width=True)

with col2:
    st.header("2. Affectation Secteurs & Week-ends")
    
    if not st.session_state['df_secteurs'].empty:
        df_visuel = st.session_state['df_secteurs'].copy()
        
        # --- FILTRE PERSONNEL ---
        st.write("Filtrez le planning pour ne voir que vos présences :")
        filtre_medecin = st.selectbox("Voir le planning de :", ["Vue globale"] + MEDECINS)
        
        if filtre_medecin != "Vue globale":
            # Ne garde que les lignes où le trigramme du médecin apparaît
            masque = df_visuel.apply(lambda row: row.astype(str).str.contains(filtre_medecin).any(), axis=1)
            df_visuel = df_visuel[masque]
            st.info(f"Affichage filtré : Uniquement les présences de {filtre_medecin}.")

        # --- FONCTION DE COLORATION ---
        def appliquer_couleurs(row):
            styles = [''] * len(row)
            for i, col in enumerate(row.index):
                val = str(row[col])
                # Mettre l'astreinte en évidence (fond rouge clair, texte rouge foncé)
                if "Astreinte" in col and val not in ["Aucun", "VIDE"]:
                    styles[i] = 'background-color: #ffe6e6; color: #cc0000; font-weight: bold;'
                
                # Couleurs douces pour les secteurs
                elif "Jaune" in col and val not in ["VIDE", "Repos / Fermé"]:
                    styles[i] = 'background-color: #fff9db; color: #8a7a00;' 
                elif "Bleu" in col and val not in ["VIDE", "Repos / Fermé"]:
                    styles[i] = 'background-color: #e7f5ff; color: #00509e;' 
                elif "Gris" in col and val not in ["VIDE", "Repos / Fermé"]:
                    styles[i] = 'background-color: #f1f3f5; color: #343a40;' 
                
                # Jours de repos ou cases vides en texte effacé
                elif "Repos" in val or val == "Aucun" or val == "VIDE":
                    styles[i] = 'color: #ced4da; font-style: italic;'
            return styles

        # Application du style au tableau
        df_style = df_visuel.style.apply(appliquer_couleurs, axis=1)
        
        # Affichage du tableau coloré
        st.dataframe(df_style, hide_index=True, height=650, use_container_width=True)
        
        # --- EXPORT EXCEL/CSV ---
        csv = st.session_state['df_secteurs'].to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Télécharger le planning complet (Format Excel / CSV)",
            data=csv,
            file_name=f"Planning_Secteurs_OHS.csv",
            mime="text/csv",
            use_container_width=True
        )
        
    else:
        st.info("👈 Configurez vos paramètres à gauche et cliquez sur 'Générer le planning'.")
