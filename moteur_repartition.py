import pulp
import calendar
import datetime
import pandas as pd

MEDECINS = ['OA', 'PM', 'VD', 'CJ', 'MS']

JOURS_OFF_MATIN = {'OA': [], 'PM': [], 'VD': [2], 'CJ': [0], 'MS': [1]}
JOURS_OFF_APREM = {'OA': [], 'PM': [], 'VD': [2], 'CJ': [0, 2, 4], 'MS': [1, 3]}

def generer_planning(annee_debut, mois_debut, nb_mois, liste_absences, preferences_dict, historique_dict, liste_feries):
    # 1. GÉNÉRATION DES DATES
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

    # 2. CATÉGORISATION DES JOURS (Basée sur vos saisies manuelles)
    feries_list = [f['date'] for f in liste_feries]
    categories = {}
    
    for j in jours_base:
        is_ferie = j in feries_list
        is_veille_ferie = (j + datetime.timedelta(days=1)) in feries_list and j.weekday() < 4
        
        if j.weekday() == 4:
            categories[j] = 'WE_Start' # Le vendredi reste le point d'ancrage du WE, même si c'est un jour férié
        elif j.weekday() in [5, 6]:
            categories[j] = 'WE_End'
        elif is_ferie:
            categories[j] = 'Ferie'
        elif is_veille_ferie:
            categories[j] = 'Veille_Ferie'
        else:
            categories[j] = 'Semaine'

    # 3. MOTEUR MATHÉMATIQUE
    prob = pulp.LpProblem("Astreintes_Multiobjectifs", pulp.LpMinimize)
    astreintes = pulp.LpVariable.dicts("G", (MEDECINS, jours_base), cat='Binary')

    for j in jours_base:
        prob += pulp.lpSum(astreintes[m][j] for m in MEDECINS) == 1

    absences_set = set((abs_['medecin'], abs_['date']) for abs_ in liste_absences)
    for m in MEDECINS:
        for j in jours_base:
            if (m, j) in absences_set:
                prob += astreintes[m][j] == 0
            elif j.weekday() < 4 and (j.weekday() in JOURS_OFF_MATIN[m] or j.weekday() in JOURS_OFF_APREM[m]):
                prob += astreintes[m][j] == 0

    for j in jours_base:
        if categories[j] == 'WE_Start':
            j_sat, j_sun = j + datetime.timedelta(days=1), j + datetime.timedelta(days=2)
            for m in MEDECINS:
                if j_sat in jours_base: prob += astreintes[m][j] == astreintes[m][j_sat]
                if j_sun in jours_base: prob += astreintes[m][j] == astreintes[m][j_sun]
        if categories[j] == 'Veille_Ferie':
            j_fer = j + datetime.timedelta(days=1)
            for m in MEDECINS:
                if j_fer in jours_base: prob += astreintes[m][j] == astreintes[m][j_fer]

    # 4. ÉQUITÉ SÉPARÉE
    max_we, min_we = pulp.LpVariable("MaxWE", 0), pulp.LpVariable("MinWE", 0)
    max_sem, min_sem = pulp.LpVariable("MaxSem", 0), pulp.LpVariable("MinSem", 0)
    max_fer, min_fer = pulp.LpVariable("MaxFer", 0), pulp.LpVariable("MinFer", 0)

    for m in MEDECINS:
        tot_we = historique_dict[m].get('weekend', 0) + pulp.lpSum(astreintes[m][j] for j in jours_base if categories[j] == 'WE_Start')
        prob += tot_we <= max_we
        prob += tot_we >= min_we

        tot_sem = historique_dict[m].get('semaine', 0) + pulp.lpSum(astreintes[m][j] for j in jours_base if categories[j] == 'Semaine')
        prob += tot_sem <= max_sem
        prob += tot_sem >= min_sem

        tot_fer = historique_dict[m].get('ferie', 0) + pulp.lpSum(astreintes[m][j] for j in jours_base if categories[j] == 'Ferie')
        prob += tot_fer <= max_fer
        prob += tot_fer >= min_fer

    bonus = pulp.lpSum(0.01 * astreintes[m][j] for m in MEDECINS for j in jours_base if categories[j] == 'Semaine' and j.weekday() in preferences_dict.get(m, []))

    prob += 10*(max_we - min_we) + 10*(max_fer - min_fer) + (max_sem - min_sem) - bonus
    prob.solve(pulp.PULP_CBC_CMD(msg=False))

    # 5. CONSTRUCTION DU PLANNING VISUEL
    donnees_secteurs = []
    jours_a_afficher = [j for j in jours_base if (annee_debut <= j.year and mois_debut <= j.month) or j.year > annee_debut][:sum(calendar.monthrange(annee_debut + (mois_debut + i - 1)//12, (mois_debut + i - 1)%12 + 1)[1] for i in range(nb_mois))]

    # Dictionnaire inversé pour récupérer le nom du férié
    dict_noms_feries = {f['date']: f['nom'] for f in liste_feries}

    for jour in jours_a_afficher:
        cat = categories[jour]
        medecin_garde = next((m for m in MEDECINS if pulp.value(astreintes[m][jour]) == 1), "Aucun")

        is_working_day = (jour.weekday() < 5) and (cat != 'Ferie')

        if not is_working_day:
            if jour.weekday() >= 5:
                label = "Bloc WE"
            else:
                nom_ferie = dict_noms_feries.get(jour, "Jour Férié")
                label = f"Férié : {nom_ferie}"
                
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
        if cat == 'Veille_Ferie': 
            nom_ferie = dict_noms_feries.get(jour + datetime.timedelta(days=1), "Férié")
            label_astreinte += f" (Veille de {nom_ferie})"

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

    # 6. COMPTEURS GLOBAUX
    compteurs = []
    for m in MEDECINS:
        sem = sum(1 for j in jours_base if pulp.value(astreintes[m][j]) == 1 and categories[j] == 'Semaine')
        we = sum(1 for j in jours_base if pulp.value(astreintes[m][j]) == 1 and categories[j] == 'WE_Start')
        fer = sum(1 for j in jours_base if pulp.value(astreintes[m][j]) == 1 and categories[j] == 'Ferie')
        
        compteurs.append({
            "Médecin": m,
            "Semaines (Total)": historique_dict[m]['semaine'] + sem,
            "Week-ends (Total)": historique_dict[m]['weekend'] + we,
            "Fériés (Total)": historique_dict[m]['ferie'] + fer
        })

    return pd.DataFrame(donnees_secteurs), pd.DataFrame(compteurs)
