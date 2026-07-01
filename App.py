import streamlit as st
import pandas as pd
import datetime
from moteur_repartition import generer_planning, MEDECINS

st.set_page_config(page_title="Gestionnaire d'Astreintes Médicales", layout="wide")
st.title("🏥 Pilotage du Centre : Astreintes, Congés & Secteurs")

if 'absences' not in st.session_state:
    st.session_state['absences'] = []
if 'preferences' not in st.session_state:
    st.session_state['preferences'] = {'OA': [], 'PM': [], 'VD': [3], 'CJ': [], 'MS': []}
if 'df_secteurs' not in st.session_state:
    st.session_state['df_secteurs'] = pd.DataFrame()
if 'df_compteurs' not in st.session_state:
    st.session_state['df_compteurs'] = pd.DataFrame()

JOURS_MAP = {"Lundi": 0, "Mardi": 1, "Mercredi": 2, "Jeudi": 3}
JOURS_INV_MAP = {v: k for k, v in JOURS_MAP.items()}

# ==========================================
# BARRE LATÉRALE : CONFIGURATION
# ==========================================
st.sidebar.header("⚙️ Saisie des Données")

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
st.sidebar.subheader("2. Jours préférentiels (Semaine)")
med_pref = st.sidebar.selectbox("Médecin", MEDECINS, key="pref_med")
jour_pref = st.sidebar.selectbox("Jour désiré", list(JOURS_MAP.keys()), index=3)

if st.sidebar.button("Enregistrer la préférence"):
    idx_j = JOURS_MAP[jour_pref]
    st.session_state['preferences'][med_pref] = [idx_j]
    st.sidebar.success(f"Préférence enregistrée : {med_pref} -> {jour_pref}")

# NOUVEAU : Historique modifiable directement à l'écran
st.sidebar.markdown("---")
st.sidebar.subheader("3. Historique Réalisé (Acquis)")
st.sidebar.caption("Saisissez les astreintes passées pour équilibrer le futur :")

if 'df_historique' not in st.session_state:
    st.session_state['df_historique'] = pd.DataFrame({
        "Médecin": MEDECINS,
        "Semaines": [0, 0, 0, 0, 0],
        "Week-ends": [0, 0, 0, 0, 0]
    })

# Tableau éditable (Mini Excel)
df_hist_edit = st.sidebar.data_editor(st.session_state['df_historique'], hide_index=True)
st.session_state['df_historique'] = df_hist_edit

# Conversion du tableau éditable pour le moteur
historique_dict = {}
for index, row in df_hist_edit.iterrows():
    historique_dict[row['Médecin']] = {
        'semaine': int(row['Semaines']),
        'weekend': int(row['Week-ends']),
        'total': int(row['Semaines']) + int(row['Week-ends'])
    }

if st.sidebar.button("🗑️ Réinitialiser (Congés & Préf)"):
    st.session_state['absences'] = []
    st.session_state['preferences'] = {'OA': [], 'PM': [], 'VD': [3], 'CJ': [], 'MS': []}
    st.rerun()

# ==========================================
# CORPS PRINCIPAL
# ==========================================
col1, col2 = st.columns([1, 2])

with col1:
    st.header("1. Paramètres & Équité")
    st.write("Choisissez la période cible :")
    
    col_a, col_b = st.columns(2)
    with col_a:
        annee_cible = st.number_input("Année de départ", min_value=2026, max_value=2030, value=2026)
        mois_cible = st.number_input("Mois de départ (1-12)", min_value=1, max_value=12, value=7) # Juillet
    with col_b:
        nb_mois = st.number_input("Nombre de mois", min_value=1, max_value=12, value=6) # 6 mois
    
    st.markdown("---")
    if st.button("🚀 Générer le planning", type="primary", use_container_width=True):
        with st.spinner(f"Calcul en cours (historique pris en compte)..."):
            df_sec, df_comp = generer_planning(
                annee_cible, 
                mois_cible,
                nb_mois,
                st.session_state['absences'], 
                st.session_state['preferences'],
                historique_dict # On envoie le passé au cerveau mathématique
            )
            st.session_state['df_secteurs'] = df_sec
            st.session_state['df_compteurs'] = df_comp
        st.success("Planning calculé avec l'historique !")

    if not st.session_state['df_compteurs'].empty:
        st.subheader("📊 Compteurs Cumulés (Passé + Futur)")
        st.dataframe(st.session_state['df_compteurs'], hide_index=True, use_container_width=True)

with col2:
    st.header("2. Affectation Secteurs & Week-ends")
    
    if not st.session_state['df_secteurs'].empty:
        st.dataframe(
            st.session_state['df_secteurs'], 
            hide_index=True, 
            height=700, 
            use_container_width=True
        )
    else:
        st.info("👈 Cliquez sur 'Générer le planning'.")
