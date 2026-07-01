import pulp
import calendar
import datetime
import pandas as pd

MEDECINS = ['OA', 'PM', 'VD', 'CJ', 'MS']

JOURS_OFF_MATIN = {'OA': [], 'PM': [], 'VD': [2], 'CJ': [0], 'MS': [1]}
JOURS_OFF_APREM = {'OA': [], 'PM': [], 'VD': [2], 'CJ': [0, 2, 4], 'MS': [1, 3]}

def generer_planning(annee_debut, mois_debut, nb_mois, liste_absences, preferences_dict, historique_dict, liste_feries):
    # ==========================================
    # 0. INITIALISATION ET CATÉGORISATION
    # ==========================================
    jours_base = []
    annee_enc, mois_enc = annee_debut, mois_debut
    for _ in range(nb_mois):
        _, num_days = calendar.monthrange(annee_enc, mois_enc)
        for d in range(1, num_days + 1):
            jours_base.append(datetime.date(annee_enc, mois_enc, d))
        mois_enc += 1
        if mois_enc > 12:
            mois_enc, annee_enc = 1, annee_enc + 1

    dernier_jour = jours_base[-1]
    if dernier_jour.weekday() == 4:
        jours_base.extend([dernier_jour + datetime.timedelta(days=1), dernier_jour + datetime.timedelta(days=2)])
    elif dernier_jour.weekday() == 5:
        jours_base.append(dernier_jour + datetime.timedelta(days=1))

    feries_list = [f['date'] for f in liste_feries]
    categories = {}
    
    for j in jours_base:
        is_ferie = j in feries_list
        is_veille_ferie = (j + datetime.timedelta(days=1)) in feries_list and j.weekday() < 4
        
        if j.weekday() == 4: categories[j] = 'WE_Start'
        elif j.weekday() in [5, 6]: categories[j] = 'WE_End'
        elif is_ferie: categories[j] = 'Ferie'
        elif is_veille_ferie: categories[j] = 'Veille_Ferie'
        else: categories[j] = 'Semaine'

    jours_we_feries = [j for j in jours_base if categories[j] in ['WE_Start', 'Ferie', 'Veille_Ferie']]
    jours_semaine = [j for j in jours_base if categories[j] == 'Semaine']
    we_starts = sorted([j for j in jours_base if categories[j] == 'WE_Start'])
    absences_set = set((abs_['medecin'], abs_['date']) for abs_ in liste_absences)

    # ==========================================
    # TEMPS 1 : RÉPARTITION DES WEEK-ENDS ET FÉRIÉS
    # ==========================================
    prob1 = pulp.LpProblem("Step1_WE_Feries", pulp.LpMinimize)
    astr_1 = pulp.LpVariable.dicts("G1", (MEDECINS, jours_we_feries), cat='Binary')

    # Couverture obligatoire
    for j in jours_we_feries:
        prob1 += pulp.lpSum(astr_1[m][j] for m in MEDECINS) == 1

    # Absences
    for m in MEDECINS:
        for j in jours_we_feries:
            if (m, j) in absences_set:
                prob1 += astr_1[m][j] == 0

    # Chaînage des jours fériés
    for j in jours_we_feries:
        if categories[j] == 'Veille_Ferie':
            j_fer = j + datetime.timedelta(days=1)
            if j_fer in jours_we_feries:
                for m in MEDECINS:
                    prob1 += astr_1[m][j] == astr_1[m][j_fer]

    # ESPACEMENT DES WEEK-ENDS (Pénalité forte si 2 WE consécutifs)
    depassements_we = []
    for m in MEDECINS:
        for i in range(len(we_starts) - 1):
            dep_we = pulp.LpVariable(f"DepWE_{m}_{i}", lowBound=0, cat='Integer')
            depassements_we.append(dep_we)
            # On interdit d'enchaîner 2 WE, SAUF si le solveur y est forcé par des congés
            prob1 += astr_1[m][we_starts[i]] + astr_1[m][we_starts[i+1]] <= 1 + dep_we

    # Équité WE et Fériés
    max_we, min_we = pulp.LpVariable("MaxWE", 0), pulp.LpVariable("MinWE", 0)
    max_fer, min_fer = pulp.LpVariable("MaxFer", 0), pulp.LpVariable("MinFer", 0)

    for m in MEDECINS:
        tot_we = historique_dict[m].get('weekend', 0) + pulp.lpSum(astr_1[m][j] for j in jours_we_feries if categories[j] == 'WE_Start')
        prob1 += tot_we <= max_we
        prob1 += tot_we >= min_we

        tot_fer = historique_dict[m].get('ferie', 0) + pulp.lpSum(astr_1[m][j] for j in jours_we_feries if categories[j] == 'Ferie')
        prob1 += tot_fer <= max_fer
        prob1 += tot_fer >= min_fer

    # Résolution Temps 1
    prob1 += 10*(max_we - min_we) + 10*(max_fer - min_fer) + 100 * pulp.lpSum(depassements_we)
    prob1.solve(pulp.PULP_CBC_CMD(msg=False))

    # Récupération des résultats du Temps 1
    planning_we_feries = {}
    for j in jours_we_feries:
        for m in MEDECINS:
            if pulp.value(astr_1[m][j]) == 1:
                planning_we_feries[j] = m

    # ==========================================
    # TEMPS 2 : RÉPARTITION DES SEMAINES (En fonction du Temps 1)
    # ==========================================
    prob2 = pulp.LpProblem("Step2_Semaines", pulp.LpMinimize)
    astr_2 = pulp.LpVariable.dicts("G2", (MEDECINS, jours_semaine), cat='Binary')

    # Couverture obligatoire
    for j in jours_semaine:
        prob2 += pulp.lpSum(astr_2[m][j] for m in MEDECINS) == 1

    # Absences et Jours Off de Semaine
    for m in MEDECINS:
        for j in jours_semaine:
            if (m, j) in absences_set:
                prob2 += astr_2[m][j] == 0
            elif j.weekday() in JOURS_OFF_MATIN[m] or j.weekday() in JOURS_OFF_APREM[m]:
                prob2 += astr_2[m][j] == 0

    # RÈGLE D'OR : 1 ASTREINTE MAX PAR SEMAINE ISO (incluant le WE calculé au Temps 1)
    semaines_iso = {}
    for j in jours_semaine:
        iso_year, iso_week, _ = j.isocalendar()
        cle = (iso_year, iso_week)
        if cle not in semaines_iso: semaines_iso[cle] = []
        semaines_iso[cle].append(j)
        
    depassements_hebdo = []
    for cle, jours_de_la_semaine in semaines_iso.items():
        # Trouver le vendredi de cette semaine précise
        lundi = jours_de_la_semaine[0] - datetime.timedelta(days=jours_de_la_semaine[0].weekday())
        vendredi = lundi + datetime.timedelta(days=4)
        
        for m in MEDECINS:
            # Le médecin a-t-il été assigné au WE de cette semaine au Temps 1 ? (1 = Oui, 0 = Non)
            a_le_we = 1 if planning_we_feries.get(vendredi) == m else 0
            
            dep_hebdo = pulp.LpVariable(f"DepHebdo_{m}_{cle[0]}_{cle[1]}", lowBound=0, cat='Integer')
            depassements_hebdo.append(dep_hebdo)
            
            # Somme des jours de semaine + le WE = max 1 (sauf extrême nécessité liée aux congés)
            prob2 += pulp.lpSum(astr_2[m][j] for j in jours_de_la_semaine) + a_le_we <= 1 + dep_hebdo

    # Équité des Semaines
    max_sem, min_sem = pulp.LpVariable("MaxSem", 0), pulp.LpVariable("MinSem", 0)
    for m in MEDECINS:
        tot_sem = historique_dict[m].get('semaine', 0) + pulp.lpSum(astr_2[m][j] for j in jours_semaine)
        prob2 += tot_sem <= max_sem
        prob2 += tot_sem >= min_sem

    bonus = pulp.lpSum(0.01 * astr_2[m][j] for m in MEDECINS for j in jours_semaine if j.weekday() in preferences_dict.get(m, []))

    # Résolution Temps 2
    prob2 += (max_sem - min_sem) + 100 * pulp.lpSum(depassements_hebdo) - bonus
    prob2.solve(pulp.PULP_CBC_CMD(msg=False))

    # ==========================================
    # TEMPS 3 : FUSION ET SECTEURS
    # ==========================================
    planning_astreintes = planning_we_feries.copy()
    for j in jours_semaine:
        for m in MEDECINS:
            if pulp.value(astr_2[m][j]) == 1:
                planning_astreintes[j] = m

    for j in we_starts:
        med = planning_astreintes.get(j)
        if med:
            planning_astreintes[j + datetime.timedelta(days=1)] = med
            planning_astreintes[j + datetime.timedelta(days=2)] = med

    # Construction du tableau visuel
    donnees_secteurs = []
    jours_a_afficher = [j for j in jours_base if (annee_debut <= j.year and mois_debut <= j.month) or j.year > annee_debut][:sum(calendar.monthrange(annee_debut + (mois_debut + i - 1)//12, (mois_debut + i - 1)%12 + 1)[1] for i in range(nb_mois))]
    dict_noms_feries = {f['date']: f['nom'] for f in liste_feries}

    for jour in jours_a_afficher:
        cat = categories[jour]
        medecin_garde = planning_astreintes.get(jour, "Aucun")
        is_working_day = (jour.weekday() < 5) and (cat != 'Ferie')

        if not is_working_day:
            if jour.weekday() >= 5: label = "Bloc WE"
            else: label = f"Férié : {dict_noms_feries.get(jour, 'Férié')}"
                
            donnees_secteurs.append({
                "Date": jour.strftime('%d/%m/%Y'),
                "Jour": jour.strftime('%A'),
                "Demi-journée": "Journée Entière",
                "Astreinte 📞": f"{medecin_garde} ({label})",
                "🟡 Secteur Jaune": "Repos / Fermé",
                "🔵 Secteur Bleu": "Repos / Fermé",
                "⚫ Secteur Gris": "Repos / Fermé"
            })
            continue

        label_astreinte = medecin_garde
        if cat == 'WE_Start': label_astreinte += " (Début WE)"
        if cat == 'Veille_Ferie': label_astreinte += f" (Veille de {dict_noms_feries.get(jour + datetime.timedelta(days=1), 'Férié')})"

        for demi_journee in ['Matin', 'Après-midi']:
            presents = []
            for m in MEDECINS:
                if (m, jour) in absences_set: continue
                if demi_journee == 'Matin' and jour.weekday() in JOURS_OFF_MATIN[m]: continue
                if demi_journee == 'Après-midi':
                    if m == 'CJ' and jour.weekday() == 4 and medecin_garde == 'CJ':
                        presents.append(m)
                        continue
                    if jour.weekday() in JOURS_OFF_APREM[m]: continue
                presents.append(m)

            sec_jaune = "OA" if "OA" in presents else "VIDE"
            if "VD" in presents: sec_bleu = "VD"
            elif "PM" in presents: sec_bleu = "PM"
            else: sec_bleu = "VIDE"
                
            gris_actifs = [m for m in ["CJ", "MS"] if m in presents]
            if len(gris_actifs) == 2: sec_gris = "CJ & MS"
            elif len(gris_actifs) == 1: sec_gris = gris_actifs[0]
            else: sec_gris = "VIDE"

            if sec_jaune == "VIDE": sec_jaune = f"{medecin_garde} (Astreinte)"
            if sec_bleu == "VIDE": sec_bleu = f"{medecin_garde} (Astreinte)"
            if sec_gris == "VIDE": sec_gris = f"{medecin_garde} (Astreinte)"

            donnees_secteurs.append({
                "Date": jour.strftime('%d/%m/%Y'),
                "Jour": jour.strftime('%A'),
                "Demi-journée": demi_journee,
                "Astreinte 📞": label_astreinte,
                "🟡 Secteur Jaune": sec_jaune,
                "🔵 Secteur Bleu": sec_bleu,
                "⚫ Secteur Gris": sec_gris
            })

    # Compteurs globaux
    compteurs = []
    for m in MEDECINS:
        sem = sum(1 for j in jours_base if planning_astreintes.get(j) == m and categories[j] == 'Semaine')
        we = sum(1 for j in jours_base if planning_astreintes.get(j) == m and categories[j] == 'WE_Start')
        fer = sum(1 for j in jours_base if planning_astreintes.get(j) == m and categories[j] == 'Ferie')
        
        compteurs.append({
            "Médecin": m,
            "Semaines (Total)": historique_dict[m]['semaine'] + sem,
            "Week-ends (Total)": historique_dict[m]['weekend'] + we,
            "Fériés (Total)": historique_dict[m]['ferie'] + fer
        })

    return pd.DataFrame(donnees_secteurs), pd.DataFrame(compteurs)
