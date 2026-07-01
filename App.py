import streamlit as st
import pandas as pd
import datetime
from moteur_repartition import generer_planning, MEDECINS

st.set_page_config(page_title="Gestionnaire d'Astreintes - OHS", layout="wide")
st.title("🏥 Pilotage du Centre de Réeducation Florentin : Astreintes & Secteurs")

# Initialisation des variables de session
if 'absences' not in st.session_state: 
    st.session_state['absences'] = []
if 'preferences' not in st.session_state: 
    st.session_state['preferences'] = {'OA': [], 'PM': [], 'VD': [3], 'CJ': [], 'MS': []}
if 'feries' not in st.session_state: 
    st.session_state['feries'] = []
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
date_deb = st.sidebar.date_input("Du", datetime.date.today(), key="abs_deb")
date_fin = st.sidebar.date_input("Au", datetime.date.today(), key="abs_fin")

if st.sidebar.button("Valider le congé", type="secondary"):
    for i in range((date_fin - date_deb).days + 1):
        st.session_state['absences'].append({
            "medecin": med_absent, 
            "date": date_deb + datetime.timedelta(days=i)
        })
    st.sidebar.success("Absence enregistrée")

st.sidebar.markdown("---")

# --- 2. Préférences ---
st.sidebar.subheader("2. Jours préférentiels (Semaine)")
med_pref = st.sidebar.selectbox("Médecin", MEDECINS, key="pref_med")
jour_pref = st.sidebar.selectbox("Jour désiré", list(JOURS_MAP.keys()), index=3)

if st.sidebar.button("Enregistrer la préférence"):
    st.session_state['preferences'][med_pref] = [JOURS_MAP[jour_pref]]
    st.sidebar.success("Préférence enregistrée")

st.sidebar.markdown("---")

# --- 3. Jours Fériés ---
st.sidebar.subheader("3. Jours Fériés (Manuel)")
date_ferie = st.sidebar.date_input("Date du férié", datetime.date.today(), key="fer_date")
nom_ferie = st.sidebar.text_input("Nom (ex: Ascension)", "Férié", key="fer_nom")

if st.sidebar.button("Ajouter ce jour férié"):
    if date_ferie.weekday() >= 4:
        st.sidebar.warning("Note : Ce jour tombe un vendredi ou un week-end. L'algorithme l'intégrera directement au Bloc Week-end de ce médecin.")
    st.session_state['feries'].append({"date": date_ferie, "nom": nom_ferie})
    st.sidebar.success(f"{nom_ferie} ajouté")

st.sidebar.markdown("---")

# --- 4. Historique ---
st.sidebar.subheader("4. Historique Acquis")
st.sidebar.caption("Saisissez les compteurs du passé :")

if 'df_historique' not in st.session_state:
    st.session_state['df_historique'] = pd.DataFrame({
        "Médecin": MEDECINS,
        "Semaines": [0, 0, 0, 0, 0],
        "Week-ends": [0, 0, 0, 0, 0],
        "Fériés": [0, 0, 0, 0, 0]
    })

# Tableau éditable pour modifier l'historique à la volée
df_hist_edit = st.sidebar.data_editor(st.session_state['df_historique'], hide_index=True)
st.session_state['df_historique'] = df_hist_edit

historique_dict = {}
for _, row in df_hist_edit.iterrows():
    historique_dict[row['Médecin']] = {
        'semaine': int(row['Semaines']),
        'weekend': int(row['Week-ends']),
        'ferie': int(row['Fériés'])
    }

if st.sidebar.button("🗑️ Tout réinitialiser"):
    st.session_state['absences'] = []
    st.session_state['preferences'] = {'OA': [], 'PM': [], 'VD': [3], 'CJ': [], 'MS': []}
    st.session_state['feries'] = []
    st.rerun()


# ==========================================
# CORPS PRINCIPAL
# ==========================================
col1, col2 = st.columns([1, 2.5])

with col1:
    st.header("1. Paramètres & Équité")
    col_a, col_b = st.columns(2)
    with col_a:
        annee_cible = st.number_input("Année", min_value=2024, max_value=2030, value=datetime.date.today().year)
        mois_cible = st.number_input("Mois de départ", min_value=1, max_value=12, value=datetime.date.today().month)
    with col_b:
        nb_mois = st.number_input("Durée (mois)", min_value=1, max_value=12, value=6)
    
    st.markdown("---")
    
    # Bouton de génération avec protection anti-boucle (try / except)
    if st.button("🚀 Générer le planning", type="primary", use_container_width=True):
        with st.spinner("Calcul des équilibres en cours (Temps d'attente max : ~30 secondes)..."):
            try:
                df_sec, df_comp = generer_planning(
                    annee_cible, 
                    mois_cible, 
                    nb_mois, 
                    st.session_state['absences'], 
                    st.session_state['preferences'], 
                    historique_dict,
                    st.session_state['feries']
                )
                st
