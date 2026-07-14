import streamlit as st
import pandas as pd
import datetime
import io
from moteur_repartition import generer_planning, MEDECINS

st.set_page_config(page_title="Gestionnaire d'Astreintes - OHS", layout="wide")
st.title("🏥 Pilotage du Centre Florentin : Astreintes & Secteurs")

# Initialisation des variables de session
if 'absences' not in st.session_state: st.session_state['absences'] = []
if 'preferences' not in st.session_state: st.session_state['preferences'] = {'OA': [], 'PM': [], 'VD': [3], 'CJ': [], 'MS': []}
if 'feries' not in st.session_state: st.session_state['feries'] = []
if 'df_secteurs' not in st.session_state: st.session_state['df_secteurs'] = pd.DataFrame()
if 'df_compteurs' not in st.session_state: st.session_state['df_compteurs'] = pd.DataFrame()
if 'planning_importe' not in st.session_state: st.session_state['planning_importe'] = {} 

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

df_hist_edit = st.sidebar.data_editor(st.session_state['df_historique'], hide_index=True)
st.session_state['df_historique'] = df_hist_edit

historique_dict = {}
for _, row in df_hist_edit.iterrows():
    historique_dict[row['Médecin']] = {
        'semaine': int(row['Semaines']),
        'weekend': int(row['Week-ends']),
        'ferie': int(row['Fériés'])
    }

st.sidebar.markdown("---")

# --- 5. Importation CSV ---
st.sidebar.subheader("5. Verrouiller un planning existant")
st.sidebar.caption("Uploadez un fichier CSV pour importer les gardes, les fériés et les congés.")
fichier_import = st.sidebar.file_uploader("Fichier CSV", type=['csv'])

if fichier_import is not None:
    try:
        # Lecture robuste pour gérer l'encodage Excel français et les points-virgules
        try:
            df_import = pd.read_csv(fichier_import, sep=None, engine='python', encoding='utf-8')
        except Exception:
            fichier_import.seek(0)
            df_import = pd.read_csv(fichier_import, sep=None, engine='python', encoding='latin-1')
        
        col_date = next((col for col in df_import.columns if 'Date' in str(col)), None)
        col_astr = next((col for col in df_import.columns if 'Astreinte' in str(col)), None)
        
        # Recherche souple d'une éventuelle colonne de congés
        col_conges = next((col for col in df_import.columns if str(col).lower() in ['congé', 'conge', 'congés', 'conges', 'absence', 'absences', 'vacances']), None)
        
        if col_date and col_astr:
            nb_jours_verrouilles = 0
            nb_feries_importes = 0
            nb_conges_importes = 0
            
            for index, row in df_import.iterrows():
                date_str = str(row[col_date])
                astr_val = str(row[col_astr])
                
                try:
                    date_obj = datetime.datetime.strptime(date_str, '%d/%m/%Y').date()
                    
                    # 1. Verrouillage des astreintes
                    for m in MEDECINS:
                        if m in astr_val:
                            st.session_state['planning_importe'][date_obj] = m
                            nb_jours_verrouilles += 1
                            break
                            
                    # 2. Lecture automatique des jours fériés
                    nom_ferie = None
                    if 'Férié' in df_import.columns and pd.notna(row['Férié']) and str(row['Férié']).strip() != "":
                        nom_ferie = str(row['Férié']).strip()
                    elif "Férié :" in astr_val:
                        nom_ferie = astr_val.split("Férié :")[1].replace(")", "").strip()
                        
                    if nom_ferie:
                        if not any(f['date'] == date_obj for f in st.session_state['feries']):
                            st.session_state['feries'].append({"date": date_obj, "nom": nom_ferie})
                            nb_feries_importes += 1
                            
                    # 3. Lecture automatique des congés/absences
                    if col_conges and pd.notna(row[col_conges]):
                        val_conges = str(row[col_conges]).upper()
                        for m in MEDECINS:
                            if m in val_conges:
                                # Vérifie si ce congé n'est pas déjà enregistré
                                absence_existe = any(a['medecin'] == m and a['date'] == date_obj for a in st.session_state['absences'])
                                if not absence_existe:
                                    st.session_state['absences'].append({"medecin": m, "date": date_obj})
                                    nb_conges_importes += 1
                                    
                except ValueError:
                    pass 
                    
            st.sidebar.success(f"✅ Fichier lu : {nb_jours_verrouilles} gardes, {nb_feries_importes} jours fériés et {nb_conges_importes} jours de congés importés.")
        else:
            st.sidebar.error("Format non reconnu. Les colonnes 'Date' et 'Astreinte' sont introuvables.")
    except Exception as e:
        st.sidebar.error(f"Erreur technique de lecture : {e}")

if st.sidebar.button("🗑️ Tout réinitialiser"):
    st.session_state['absences'] = []
    st.session_state['preferences'] = {'OA': [], 'PM': [], 'VD': [3], 'CJ': [], 'MS': []}
    st.session_state['feries'] = []
    st.session_state['planning_importe'] = {}
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
                    st.session_state['feries'],
                    st.session_state['planning_importe']
                )
                st.session_state['df_secteurs'] = df_sec
                st.session_state['df_compteurs'] = df_comp
                st.success("Planning généré et équilibré !")
            except ValueError as e:
                st.error(str(e))

    if not st.session_state['df_compteurs'].empty:
        st.subheader("📊 Compteurs Cumulés")
        st.dataframe(st.session_state['df_compteurs'], hide_index=True, use_container_width=True)

with col2:
    st.header("2. Affectation Secteurs & Astreintes")
    
    if not st.session_state['df_secteurs'].empty:
        df_visuel = st.session_state['df_secteurs'].copy()
        
        filtre_medecin = st.selectbox("Voir le planning de :", ["Vue globale"] + MEDECINS)
        if filtre_medecin != "Vue globale":
            masque = df_visuel.apply(lambda row: row.astype(str).str.contains(filtre_medecin).any(), axis=1)
            df_visuel = df_visuel[masque]

        def appliquer_couleurs(row):
            styles = [''] * len(row)
            for i, col in enumerate(row.index):
                val = str(row[col])
                if "Astreinte" in col and val not in ["Aucun", "VIDE"]:
                    styles[i] = 'background-color: #ffe6e6; color: #cc0000; font-weight: bold;'
                elif "Jaune" in col and val not in ["VIDE", "Repos / Fermé"]:
                    styles[i] = 'background-color: #fff9db; color: #8a7a00;' 
                elif "Bleu" in col and val not in ["VIDE", "Repos / Fermé"]:
                    styles[i] = 'background-color: #e7f5ff; color: #00509e;' 
                elif "Gris" in col and val not in ["VIDE", "Repos / Fermé"]:
                    styles[i] = 'background-color: #f1f3f5; color: #343a40;' 
                elif "Repos" in val or "Férié" in val or val in ["Aucun", "VIDE"]:
                    styles[i] = 'color: #ced4da; font-style: italic;'
            return styles

        df_style = df_visuel.style.apply(appliquer_couleurs, axis=1)
        st.dataframe(df_style, hide_index=True, height=650, use_container_width=True)
        
        st.markdown("---")
        st.write("📥 **Options de téléchargement :**")
        col_btn1, col_btn2 = st.columns(2)
        
        with col_btn1:
            # 1. Export CSV (Base de données pure pour réimportation, adaptée au Excel français)
            csv = st.session_state['df_secteurs'].to_csv(index=False, sep=';').encode('utf-8-sig')
            st.download_button(
                label="⚙️ Télécharger le CSV (Pour l'outil d'importation)", 
                data=csv, 
                file_name="Planning_Secteurs_OHS.csv", 
                mime="text/csv",
                use_container_width=True
            )
            
        with col_btn2:
            # 2. Export Excel (Mise en page conservée pour l'humain)
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_style.to_excel(writer, index=False, sheet_name='Planning')
            
            st.download_button(
                label="🎨 Télécharger l'Excel (Avec les couleurs)",
                data=buffer.getvalue(),
                file_name="Planning_Secteurs_OHS.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
            
    else:
        st.info("👈 Configurez vos paramètres à gauche et cliquez sur 'Générer le planning'.")
