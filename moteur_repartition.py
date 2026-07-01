import pulp
import calendar
import datetime
import pandas as pd

MEDECINS = ['OA', 'PM', 'VD', 'CJ', 'MS']

JOURS_OFF_MATIN = {
    'OA': [], 'PM': [], 'VD': [2], 'CJ': [0], 'MS': [1]
}
JOURS_OFF_APREM = {
    'OA': [], 'PM': [], 'VD': [2], 'CJ': [0, 2, 4], 'MS': [1, 3]
}

def generer_planning(annee_debut, mois_debut, nb_mois, liste_absences, preferences_dict=None, historique_dict=None):
    if preferences_dict is None:
        preferences_dict = {'OA': [], 'PM': [], 'VD': [3], 'CJ': [], 'MS': []}
    if historique_dict is None:
        historique_dict = {m: {'semaine': 0, 'weekend': 0, 'total': 0} for m in MEDECINS}

    jours_a_planifier = []
    annee_en_cours = annee_debut
    mois_en_cours = mois_debut
    
    for _ in range(nb_mois):
        num_days = calendar.monthrange(annee_en_cours, mois_en_cours)[1]
        for d in range(1, num_days + 1):
            jours_a_planifier.append(datetime.date(annee_en_cours, mois_en_cours, d))
        
        mois_en_cours += 1
        if mois_en_cours > 12:
            mois_en_cours = 1
            annee_en_cours += 1
    
    jours_semaine = [j for j in jours_a_planifier if j.weekday() < 4]
    jours_weekends = [j for j in jours_a_planifier if j.weekday() == 4]
    tous_les_blocs = jours_semaine + jours_weekends

    absences_set = set((abs_['medecin'], abs_['date']) for abs_ in liste_absences)

    # ==========================================
    # TEMPS 1 : OPTIMISATION
    # ==========================================
    prob = pulp.LpProblem("Planning_Astreintes", pulp.LpMinimize)
    astreintes = pulp.LpVariable.dicts("Garde", (MEDECINS, tous_les_blocs), cat='Binary')
    max_gardes = pulp.LpVariable("MaxGardes", lowBound=0, cat='Integer')

    for j in tous_les_blocs:
        prob += pulp.lpSum(astreintes[m][j] for m in MEDECINS) == 1

    for m in MEDECINS:
        for j in tous_les_blocs:
            en_conge = (m, j) in absences_set
            if j.weekday() == 4:
                en_conge = en_conge or ((m, j + datetime.timedelta(days=1)) in absences_set)
                en_conge = en_conge or ((m, j + datetime.timedelta(days=2)) in absences_set)
            
            if en_conge:
                prob += astreintes[m][j] == 0
            elif j.weekday() < 4 and (j.weekday() in JOURS_OFF_MATIN[m] or j.weekday() in JOURS_OFF_APREM[m]):
                prob += astreintes[m][j] == 0

    # INTÉGRATION DE L'HISTORIQUE : On ajoute les gardes passées aux gardes futures
    for m in MEDECINS:
        poids_passe = historique_dict[m]['total']
        prob += poids_passe + pulp.lpSum(astreintes[m][j] for j in tous_les_blocs) <= max_gardes

    bonus_preferences = pulp.lpSum(
        0.01 * astreintes[m][j]
        for m in MEDECINS
        for j in tous_les_blocs
        if j.weekday() < 4 and j.weekday() in preferences_dict.get(m, [])
    )

    prob += max_gardes - bonus_preferences
    prob.solve(pulp.PULP_CBC_CMD(msg=False))
    
    planning_astreintes = {}
    for j in tous_les_blocs:
        for m in MEDECINS:
            if pulp.value(astreintes[m][j]) == 1:
                planning_astreintes[j] = m
                if j.weekday() == 4:
                    planning_astreintes[j + datetime.timedelta(days=1)] = m
                    planning_astreintes[j + datetime.timedelta(days=2)] = m

    # ==========================================
    # TEMPS 2 : REPARTITION DES SECTEURS
    # ==========================================
    donnees_secteurs = []

    for jour in jours_a_planifier:
        medecin_garde = planning_astreintes.get(jour, "Aucun")

        # NOUVEAU : Affichage visuel du bloc week-end complet
        if jour.weekday() >= 5: # Samedi (5) et Dimanche (6)
            donnees_secteurs.append({
                "Date": jour.strftime('%d/%m/%Y'),
                "Jour": jour.strftime('%A'),
                "Demi-journée": "Journée Entière",
                "Astreinte 📞": medecin_garde,
                "🟡 Secteur Jaune (+ Interne)": "Repos / Fermé",
                "🔵 Secteur Bleu (+ Interne)": "Repos / Fermé",
                "⚫ Secteur Gris (+ Interne)": "Repos / Fermé"
            })
            continue # On passe directement au jour suivant

        # S'il s'agit du vendredi, on le signale dans la case astreinte
        label_astreinte = f"{medecin_garde} (Début WE)" if jour.weekday() == 4 else medecin_garde

        for demi_journee in ['Matin', 'Après-midi']:
            presents = []
            for m in MEDECINS:
                if (m, jour) in absences_set:
                    continue
                if demi_journee == 'Matin':
                    if jour.weekday() in JOURS_OFF_MATIN[m]:
                        continue
                else:
                    if m == 'CJ' and jour.weekday() == 4:
                        if planning_astreintes.get(jour) == 'CJ':
                            presents.append(m)
                            continue
                    if jour.weekday() in JOURS_OFF_APREM[m]:
                        continue
                presents.append(m)

            sec_jaune = "OA" if "OA" in presents else "VIDE"
            
            if "VD" in presents:
                sec_bleu = "VD"
            elif "PM" in presents:
                sec_bleu = "PM"
            else:
                sec_bleu = "VIDE"
                
            gris_actifs = [m for m in ["CJ", "MS"] if m in presents]
            if len(gris_actifs) == 2:
                sec_gris = "CJ & MS"
            elif len(gris_actifs) == 1:
                sec_gris = gris_actifs[0]
            else:
                sec_gris = "VIDE"

            if sec_jaune == "VIDE":
                sec_jaune = f"{label_astreinte} (Astreinte)"
            if sec_bleu == "VIDE":
                sec_bleu = f"{label_astreinte} (Astreinte)"
            if sec_gris == "VIDE":
                sec_gris = f"{label_astreinte} (Astreinte)"

            donnees_secteurs.append({
                "Date": jour.strftime('%d/%m/%Y'),
                "Jour": jour.strftime('%A'),
                "Demi-journée": demi_journee,
                "Astreinte 📞": label_astreinte,
                "🟡 Secteur Jaune (+ Interne)": sec_jaune,
                "🔵 Secteur Bleu (+ Interne)": sec_bleu,
                "⚫ Secteur Gris (+ Interne)": sec_gris
            })

    df_secteurs = pd.DataFrame(donnees_secteurs)
    
    # NOUVEAU : Compteurs globaux (Passé + Futur)
    compteurs = []
    for m in MEDECINS:
        semaines = sum(1 for j, med in planning_astreintes.items() if med == m and j.weekday() < 4)
        weekends = sum(1 for j, med in planning_astreintes.items() if med == m and j.weekday() == 4)
        
        hist_sem = historique_dict[m]['semaine']
        hist_we = historique_dict[m]['weekend']
        
        compteurs.append({
            "Médecin": m,
            "Historique Semaines": hist_sem,
            "Nouvelles Semaines": semaines,
            "TOTAL Semaines": hist_sem + semaines,
            "Historique Week-ends": hist_we,
            "Nouveaux Week-ends": weekends,
            "TOTAL Week-ends": hist_we + weekends
        })
    df_compteurs = pd.DataFrame(compteurs)

    return df_secteurs, df_compteurs
