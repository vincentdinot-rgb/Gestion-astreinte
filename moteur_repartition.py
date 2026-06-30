import pulp
import calendar
import datetime
import pandas as pd

# Liste des médecins de l'équipe
MEDECINS = ['OA', 'PM', 'VD', 'CJ', 'MS']

# Définition précise des indisponibilités structurelles par demi-journée
# 0=Lundi, 1=Mardi, 2=Mercredi, 3=Jeudi, 4=Vendredi
JOURS_OFF_MATIN = {
    'OA': [],
    'PM': [],
    'VD': [2],       # Absent le mercredi matin
    'CJ': [0],       # Absente le lundi matin
    'MS': [1]        # Absente le mardi matin
}

JOURS_OFF_APREM = {
    'OA': [],
    'PM': [],
    'VD': [2],       # Absent le mercredi après-midi
    'CJ': [0, 2, 4], # Absente lundi, mercredi et vendredi après-midi (hors astreinte WE)
    'MS': [1, 3]     # Absente mardi et jeudi après-midi
}

def generer_planning(annee, mois, liste_absences, preferences_dict=None):
    """
    Génère le planning des astreintes et la répartition des secteurs par demi-journée.
    """
    if preferences_dict is None:
        preferences_dict = {'OA': [], 'PM': [], 'VD': [3], 'CJ': [], 'MS': []} # Par défaut VD aime le jeudi (3)

    # 1. Initialisation des dates du mois
    num_days = calendar.monthrange(annee, mois)[1]
    jours_du_mois = [datetime.date(annee, mois, d) for d in range(1, num_days + 1)]
    
    # Séparation en blocs d'astreinte (Semaine: Lun-Jeu / Weekend: Ven)
    jours_semaine = [j for j in jours_du_mois if j.weekday() < 4]
    jours_weekends = [j for j in jours_du_mois if j.weekday() == 4]
    tous_les_blocs = jours_semaine + jours_weekends

    # Indexation des absences pour recherche rapide
    absences_set = set((abs_['medecin'], abs_['date']) for abs_ in liste_absences)

    # ==========================================
    # TEMPS 1 : OPTIMISATION DES ASTREINTES (PuLP)
    # ==========================================
    prob = pulp.LpProblem("Planning_Astreintes", pulp.LpMinimize)
    
    # Variables binaires : 1 si le médecin est de garde sur le bloc, 0 sinon
    astreintes = pulp.LpVariable.dicts("Garde", (MEDECINS, tous_les_blocs), cat='Binary')
    max_gardes = pulp.LpVariable("MaxGardes", lowBound=0, cat='Integer')

    # Contrainte : 1 seul médecin par bloc d'astreinte
    for j in tous_les_blocs:
        prob += pulp.lpSum(astreintes[m][j] for m in MEDECINS) == 1

    # Contraintes d'absences et de jours OFF de semaine
    for m in MEDECINS:
        for j in tous_les_blocs:
            # Vérification des congés sur l'ensemble du bloc
            en_conge = (m, j) in absences_set
            if j.weekday() == 4: # Si c'est un bloc week-end, on vérifie Samedi et Dimanche aussi
                en_conge = en_conge or ((m, j + datetime.timedelta(days=1)) in absences_set)
                en_conge = en_conge or ((m, j + datetime.timedelta(days=2)) in absences_set)
            
            if en_conge:
                prob += astreintes[m][j] == 0
            # Si c'est un jour de semaine, l'astreinte de nuit nécessite de travailler la journée
            elif j.weekday() < 4 and (j.weekday() in JOURS_OFF_MATIN[m] or j.weekday() in JOURS_OFF_APREM[m]):
                prob += astreintes[m][j] == 0

    # Contrainte d'équité sur le volume global des astreintes
    for m in MEDECINS:
        prob += pulp.lpSum(astreintes[m][j] for j in tous_les_blocs) <= max_gardes

    # Gestion des préférences (Soft Constraints / Contraintes souples)
    # On ajoute un très léger bonus (0.01) quand une préférence est respectée
    bonus_preferences = pulp.lpSum(
        0.01 * astreintes[m][j]
        for m in MEDECINS
        for j in tous_les_blocs
        if j.weekday() < 4 and j.weekday() in preferences_dict.get(m, [])
    )

    # Objectif : Minimiser les inégalités tout en maximisant les préférences
    prob += max_gardes - bonus_preferences
    prob.solve(pulp.PULP_CBC_CMD(msg=False))
    
    # Extraction du résultat des astreintes
    planning_astreintes = {}
    for j in tous_les_blocs:
        for m in MEDECINS:
            if pulp.value(astreintes[m][j]) == 1:
                planning_astreintes[j] = m
                if j.weekday() == 4: # Duplication du médecin sur le samedi et le dimanche
                    planning_astreintes[j + datetime.timedelta(days=1)] = m
                    planning_astreintes[j + datetime.timedelta(days=2)] = m

    # ==========================================
    # TEMPS 2 : REPARTITION DES SECTEURS PAR DEMI-JOURNÉE
    # ==========================================
    donnees_secteurs = []

    for jour in jours_du_mois:
        if jour.weekday() >= 5: # Pas de gestion de secteurs les Samedi et Dimanche
            continue
            
        medecin_garde = planning_astreintes.get(jour, "Aucun")

        for demi_journee in ['Matin', 'Après-midi']:
            # Détermination des médecins présents
            presents = []
            for m in MEDECINS:
                if (m, jour) in absences_set:
                    continue # En congé
                
                # Gestion des règles spécifiques de jours OFF
                if demi_journee == 'Matin':
                    if jour.weekday() in JOURS_OFF_MATIN[m]:
                        continue
                else:
                    # Cas particulier pour CJ : travaille le vendredi aprem si elle est d'astreinte le WE
                    if m == 'CJ' and jour.weekday() == 4:
                        vendredi_coords = jour
                        if planning_astreintes.get(vendredi_coords) == 'CJ':
                            presents.append(m)
                            continue
                    if jour.weekday() in JOURS_OFF_APREM[m]:
                        continue
                
                presents.append(m)

            # --- APPLICATION DES RÈGLES DE SECTEURS ---
            
            # 1. Secteur Jaune (Dr OA)
            sec_jaune = "OA" if "OA" in presents else "VIDE"
            
            # 2. Secteur Bleu (Exclusivité VD / PM)
            if "VD" in presents:
                sec_bleu = "VD"
            elif "PM" in presents:
                sec_bleu = "PM"
            else:
                sec_bleu = "VIDE"
                
            # 3. Secteur Gris (Co-gestion CJ / MS)
            gris_actifs = [m for m in ["CJ", "MS"] if m in presents]
            if len(gris_actifs) == 2:
                sec_gris = "CJ & MS"
            elif len(gris_actifs) == 1:
                sec_gris = gris_actifs[0]
            else:
                sec_gris = "VIDE"

            # 4. Règle de secours : Le médecin d'astreinte gère les secteurs vides
            if sec_jaune == "VIDE":
                sec_jaune = f"{medecin_garde} (Astreinte)"
            if sec_bleu == "VIDE":
                sec_bleu = f"{medecin_garde} (Astreinte)"
            if sec_gris == "VIDE":
                sec_gris = f"{medecin_garde} (Astreinte)"

            # Ajout de la ligne au planning de la journée
            donnees_secteurs.append({
                "Date": jour.strftime('%d/%m/%Y'),
                "Jour": jour.strftime('%A'),
                "Demi-journée": demi_journee,
                "Astreinte 📞": medecin_garde,
                "🟡 Secteur Jaune (+ Interne)": sec_jaune,
                "🔵 Secteur Bleu (+ Interne)": sec_bleu,
                "⚫ Secteur Gris (+ Interne)": sec_gris
            })

    df_secteurs = pd.DataFrame(donnees_secteurs)
    
    # Calcul des compteurs d'équité mensuels
    compteurs = []
    for m in MEDECINS:
        semaines = sum(1 for j, med in planning_astreintes.items() if med == m and j.weekday() < 4)
        weekends = sum(1 for j, med in planning_astreintes.items() if med == m and j.weekday() == 4)
        compteurs.append({
            "Medecin": m,
            "Astreintes Semaine (Lun-Jeu)": semaines,
            "Blocs Week-end (Ven-Dim)": weekends
        })
    df_compteurs = pd.DataFrame(compteurs)

    return df_secteurs, df_compteurs