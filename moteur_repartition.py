import pulp

# 1. Initialisation du problème (on cherche à équilibrer, donc "minimiser" les écarts)
prob = pulp.LpProblem("Repartition_Astreintes", pulp.LpMinimize)

# 2. Nos variables : Les 5 médecins et les blocs de la semaine
medecins = ['OA', 'PM', 'VD', 'CJ', 'MS']
jours_semaine = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi']

# Création d'une variable binaire (1 = de garde, 0 = repos) pour chaque combinaison possible
# Ex: assignation['OA']['Mardi'] vaudra 1 si OA est de garde mardi.
assignation = pulp.LpVariable.dicts("Garde", (medecins, jours_semaine), cat='Binary')

# 3. Ajout des contraintes dures (Exemple : VD ne travaille pas le mercredi)
prob += assignation['VD']['Mercredi'] == 0, "Contrainte_Temps_Partiel_VD"

# 4. Ajout de la contrainte de couverture (1 médecin par jour exactement)
for jour in jours_semaine:
    prob += pulp.lpSum([assignation[m][jour] for m in medecins]) == 1, f"Couverture_{jour}"

# (L'algorithme va ensuite résoudre ce puzzle en respectant ces règles)
