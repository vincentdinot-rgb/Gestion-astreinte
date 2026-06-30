import streamlit as st
import pandas as pd
import datetime
from moteur_repartition import generer_planning, MEDECINS

st.set_page_config(page_title="Gestionnaire d'Astreintes Médicales", layout="wide")

st.title("🏥 Pilotage du Centre : Astreintes, Congés & Secteurs")
st.markdown("Interface simplifiée à destination de l'administrateur unique du service.")

# Initialisation des variables globales de session
if 'absences' not in st.session_state:
    st.session_state['absences'] = []
if 'preferences' not in st.session_state:
    st.session_state['preferences'] = {'OA': [], 'PM': [], 'VD': [3], 'CJ': [], 'MS': []} # VD prépare le Jeudi (3) par défaut
if 'df_secteurs' not in st.session_state:
    st.session_state['df_secteurs'] = pd.DataFrame()
if 'df_compteurs' not in st.session_state:
    st.session_state['df_compteurs'] = pd.DataFrame()

# Traduction des jours pour l'affichage des préférences
JOURS_MAP = {"Lundi": 0, "Mardi": 1, "Mercredi": 2, "Jeudi": 3}
JOURS_INV_MAP = {v: k for k, v in JOURS_MAP.items()}

# ==========================================
# BARRE LATÉRALE : CONFIGURATION & ADMINISTRATION
# ==========================================
st.sidebar.header("⚙️ Saisie des Données")

# --- Module 1 : Congés ---
st.sidebar.subheader("1. Enregistrer un congé")
med_absent = st.sidebar.selectbox("Médecin concerné", MEDECINS, key="abs_med")
date_deb = st.sidebar.date_input("Date de début", datetime.date.today(), key="abs_deb")
date_fin = st.sidebar.date_input("Date de fin", datetime.date.today(), key="abs_fin")

if st.sidebar.button("Valider le congé", type="secondary"):
    delta = date_fin - date_deb
    for i in range(delta.days + 1):
        jour_abs = date_deb + datetime.timedelta(days=i)
        st.session_state['absences'].append({
            "medecin": med_absent,
            "date": jour_abs
        })
    st.sidebar.success(f"Absence enregistrée pour {med_absent}")

# --- Module 2 : Jours Préférentiels ---
st.sidebar.markdown("---")
st.sidebar.subheader("2. Jours préférentiels d'astreinte")
med_pref = st.sidebar.selectbox("Médecin", MEDECINS, key="pref_med")
jour_pref = st.sidebar.selectbox("Jour désiré (Semaine)", list(JOURS_MAP.keys()), index=3)

if st.sidebar.button("Enregistrer la préférence"):
    idx_j = JOURS_MAP[jour_pref]
    if idx_j not in st.session_state['preferences'][med_pref]:
        st.session_state['preferences'][med_pref] = [idx_j] # Remplace ou ajoute la préférence
        st.sidebar.success(f"Préférence enregistrée : {med_pref} -> {jour_pref}")

# --- Affichage des listes de contrôle ---
st.sidebar.markdown("---")
if st.sidebar.checkbox("Afficher le récapitulatif des saisies"):
    st.sidebar.write("**Préférences actuelles :**")
    for m, p in st.session_state['preferences'].items():
        if p:
            st.sidebar.write(f"- {m} préfère le : {', '.join([JOURS_INV_MAP[x] for x in p])}")
            
    if st.session_state['absences']:
        st.sidebar.write("**Congés enregistrés (points de repère) :**")
        df_abs_view = pd.DataFrame(st.session_state['absences'])
        st.sidebar.dataframe(df_abs_view, hide_index=True)

if st.sidebar.button("🗑️ Réinitialiser tous les congés/préférences"):
    st.session_state['absences'] = []
    st.session_state['preferences'] = {'OA': [], 'PM': [], 'VD': [3], 'CJ': [], 'MS': []}
    st.rerun()

# ==========================================
# CORPS PRINCIPAL : TABLEAU DE BORD DE GÉNÉRATION
# ==========================================
col1, col2 = st.columns([1, 2])

with col1:
    st.header("1. Paramètres & Équité")
    st.write("Choisissez la période cible pour le calcul automatique :")
    
    annee_cible = st.number_input("Année", min_value=2026, max_value=2030, value=2026)
    mois_cible = st.number_input("Mois (1-12)", min_value=1, max_value=12, value=11) # Novembre par défaut
    
    st.markdown("---")
    if st.button("🚀 Générer le planning du mois", type="primary", use_container_width=True):
        with st.spinner("Calcul mathématique de la meilleure configuration..."):
            df_sec, df_comp = generer_planning(
                annee_cible, 
                mois_cible, 
                st.session_state['absences'], 
                st.session_state['preferences']
            )
            st.session_state['df_secteurs'] = df_sec
            st.session_state['df_compteurs'] = df_comp
        st.success("Planning calculé et mis à jour !")

    if not st.session_state['df_compteurs'].empty:
        st.subheader("📊 Compteurs d'Équité Mensuels")
        st.write("Vérification des volumes réels distribués sur la période :")
        st.dataframe(st.session_state['df_compteurs'], hide_index=True, use_container_width=True)
        st.caption("ℹ️ *L'algorithme lisse la charge de travail pour minimiser les écarts entre confrères.*")

with col2:
    st.header("2. Affectation Finale des Secteurs")
    
    if not st.session_state['df_secteurs'].empty:
        st.write("Tableau de bord de l'activité clinique par demi-journée (du lundi au vendredi) :")
        
        # Application d'un style visuel propre pour le tableau de bord
        st.dataframe(
            st.session_state['df_secteurs'], 
            hide_index=True, 
            height=650, 
            use_container_width=True
        )
        st.caption("💡 *Note : Les internes suivent automatiquement leur secteur d'ancrage (Jaune, Bleu ou Gris).*")
    else:
        st.info("👈 Veuillez configurer vos paramètres à gauche puis cliquer sur 'Générer le planning'.")