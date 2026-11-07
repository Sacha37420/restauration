# Feuille de route — restauration

Ce fichier est lu par une machine : `validate-app.sh` refuse de déployer s'il manque ou s'il ne
contient aucun lot au format ci-dessous, et `app-test.sh` lit la commande de test. Garder les titres
tels quels.

App livrée avant l'obligation de feuille de route : le Lot 1 résume l'existant. Les lots suivants
viennent de l'analyse du 2026-10-31 ; la vue d'ensemble est dans `to_do_global.md`, à la racine du
dépôt du lab. Légende : [C] constaté, [D] déduit.

## Commande de test
python manage.py test

## Lot 1 — Existant : cuisine, salle, commande publique, analyses   ·   statut : livré
**Objectif :** gestion d'un restaurant :
- fournisseurs, ingrédients, recettes, plats, commandes ;
- plan de tables avec QR codes ;
- commande publique anonyme avec paiement Stripe ;
- analyses (ventes, météo, régression) ;
- gestion des utilisateurs par les managers.

Accès : `manager,cuisinier,serveur`.
**Tâches :**
- [x] Fonctionnalités en service ; photos des plats dans `storage`, republiées par un proxy public
**Tests à passer avant de clore le lot :**
- [x] 127 tests backend (`backend/api/tests.py`) ; `cloisonnement.spec.ts` présent
**Vérifié le :** 2026-10-31 — relevé par lecture (version en service = `827d4fc`), tests non rejoués.
L'app n'était pas couverte par le chantier tests.

## Lot 2 — Gestion des utilisateurs limitée aux comptes de l'app   ·   statut : livré
**Objectif :** un manager n'agit que sur les membres de `manager`, `cuisinier` ou `serveur`.
**Constat [C] :**
- `UtilisateurRolesView`, `UtilisateurInvitationView` et `UtilisateurEtatView`
  (`backend/api/views_users.py:103-148`) prennent un `user_id` arbitraire.
- Le compte de service `restauration-admin` a `manage-users`.
- Un manager peut donc désactiver n'importe quel compte du realm, ou en réinitialiser le mot de passe
  par « inviter » (`set_temporary_password`) — superutilisateur compris.

**P1, urgence U4.**
**Tâches :**
- [x] Refuser (404) tout `user_id` absent de `list_app_users()` ; un manager ne se désactive pas lui-même
  et ne se retire pas le rôle `manager` (403) — `_cible`, `_est_soi_meme` dans `views_users.py`.
  L'invitation pose le mot de passe sur l'`id` vérifié (plus de relecture par email).
- [ ] Revoir si `manage-users` peut être restreint (rôles plus fins, ou un groupe dédié) — hors du
  chantier « urgences » (contrat v1 § 7 : le rôle du compte de service n'est pas modifié)
**Tests à passer avant de clore le lot :**
- [x] Keycloak simulé : désactiver, inviter ou changer les rôles d'un compte hors app → 404, et aucun appel d'administration émis
  (`GestionUtilisateursPerimetreTest.test_hors_app_*`, `test_liste_illisible_502_sans_appel`, `test_non_manager_refuse_avant_toute_lecture`)
- [x] Un compte de l'app reste géré normalement (`test_membre_*`, `test_manager_peut_*`) ;
  le manager contre lui-même → 403 (`test_manager_ne_se_*`)
**Vérifié le :** 2026-10-31 — `bash chantiers/tests/essai.sh restauration` : 140 tests verts (127 + 13). **Mis en service le 2026-10-31** (chantier « urgences ») : image construite pendant que l'ancienne tournait, `scripts/app-test.sh` vert sur cette image, puis `up -d --no-build` ; test de cloisonnement par `lab-runner` vert après déploiement.
Contre-épreuve : les 13 nouveaux tests joués sur l'ancien `views_users.py` → 8 échecs, comme attendu.
(« Pas encore en service », écrit avant la mise en service ci-dessus, retiré le 2026-11-08.)

## Lot 3 — Le code en service vient de l'image, pas du dossier   ·   statut : livré
**Objectif :** un redémarrage ne met plus en service le contenu du dossier sans tests.
**Constat [C] :** `docker-compose.yml:23-24` monte `./backend:/app`. **P1.**
**Tâches :**
- [x] Retirer le montage (fait dans `docker-compose.yml` ; le Dockerfile copie déjà le code, `COPY . .` ;
  `frontend` ne monte que sa configuration nginx ; aucun code n'écrit sous `/app` à l'exécution)
- [x] Reconstruire, tester, puis `up -d --no-build` (déploiement, par l'architecte) — fait le 2026-10-31 (« Mis en service » ci-dessous)
**Tests à passer avant de clore le lot :**
- [x] `docker inspect restauration-backend` ne montre aucun montage sur `/app` ; suite verte (2026-10-31 : `Mounts=[]`)
  (suite verte par `essai.sh` ; `docker compose config` ne contient plus aucun `/app` ; le
  `docker inspect` reste à faire après déploiement — aujourd'hui il montre encore le bind)
**Vérifié le :** 2026-10-31 — `docker compose config -q` valide, sans montage `/app`. **Mis en service le 2026-10-31** (chantier « urgences ») : image construite pendant que l'ancienne tournait, `scripts/app-test.sh` vert sur cette image, puis `up -d --no-build` ; test de cloisonnement par `lab-runner` vert après déploiement.
2026-11-08 : `docker inspect restauration-backend` ne montre toujours aucun montage (conteneur du 2026-11-01).

## Lot 4 — Envoi de la photo d'un plat depuis l'interface   ·   statut : à faire
**Objectif :** un manager ajoute la photo d'un plat sans passer par l'API.
**Constat [C] :** le backend accepte `photo_file` (`serializers.py:250`), mais
`frontend/src/app/core/api.service.ts:90` ne connaît que `photo` (toujours vrai le 2026-11-08).
**Tâches :**
- [ ] Champ fichier dans la page Plats : `POST`/`PATCH /api/plats/` en multipart
**Tests à passer avant de clore le lot :**
- [ ] En navigateur réel : la photo envoyée s'affiche sur `/commander` sans connexion
**Vérifié le :**

## Lot 5 — Socle de caisse (NF525 / auto-attestation)   ·   statut : à faire
**Objectif :** Ⓟ à décider. L'app est de fait un logiciel de caisse ; deux voies existent : un POS
certifié comme source de vérité, ou les quatre conditions ILAS (mémoire `restauration_caisse_compliance`).
**Constat [C] :**
- `CommandeViewSet` et `PaiementViewSet` sont des `ModelViewSet` libres (`views.py:576,745`).
- Les ventes sont recalculées par suppression puis reconstruction (`ventes.py:61,149`).
- Il n'y a ni clôture ni chaînage.
**Tâches :**
- [ ] Ⓟ Choix de la voie
- [ ] Si socle interne : une commande ou un paiement validé devient immuable (annulation par écriture inverse) ; clôtures journalières chaînées par empreinte ; export d'archive sur 6 ans
**Tests à passer avant de clore le lot :**
- [ ] `PUT`/`DELETE` d'un paiement clos → 405 ou 409 ; une altération en base est détectée par la vérification de chaîne
**Vérifié le :**

## Lot 6 — Gabarit front, documentation et chemin à portes   ·   statut : en cours
**Objectif :** même comportement que le gabarit corrigé (T3), un README, un déploiement par le moteur (T1).
**Tâches :**
- [x] Polices en chemin relatif ; `redirectUri` sur la page courante (`core/redirect-uri.ts`, copie de lab-admin ; sauf `/commander`, en `check-sso`, qui garde `appUrl`) ; `tokenBases()` (`core/env.ts` : la seule API de l'app ; `core/token-scope.ts`, copie de lab-admin) ; `pkceMethod: 'S256'` (front) — `--pkce` sur le client reste à poser par l'architecte après déploiement
- [x] Ports publiés liés à `${LAB_BIND_ADDR:-127.0.0.1}` (chantier « failles », I1)
- [ ] Couleurs du bouton Stripe en tokens (`commande-publique.component.scss:403-413`) — Ⓟ 2026-11-08 : un commentaire du fichier (l. 399-400) dit ces couleurs « de marque Stripe conservées telles quelles » à dessein ; à trancher (garder et rayer la tâche, ou passer en tokens)
- [ ] `README.md` : rôles, parcours de commande publique, Stripe, gestion des comptes
- [ ] Le chemin à portes refuse un `.keycloak-service-account-roles` non vide : pour cette app du
  superutilisateur, la règle ne s'applique qu'à un autre propriétaire. Le dire dans le README.
**Tests à passer avant de clore le lot :**
- [x] Lien direct conservé ; WOFF2 en 200 ; `validate-app.sh restauration --quality-only` vert — *2026-11-01 : lien direct et WOFF2 vérifiés ; 2026-11-08 : `validate-app.sh --quality-only` (copie jetable, `valq.sh`) code 0*
**Vérifié le :** 2026-11-01 — non déployé. Chantier « failles » (secteur E) : image candidate
`restauration-frontend:candidat` construite (`npm install` + `ng build` OK ; le bundle porte
`pkceMethod:"S256"`, les WOFF2 sont référencés en `./media/…`) ; `docker compose config` rend
`host_ip: 127.0.0.1` pour les deux ports. Les tests du lot demandent le déploiement. Restent les
couleurs du bouton Stripe, le README et la règle du chemin à portes (hors chantier).

## Lot 7 — Coffre des secrets sous une clé propre (`VAULT_ENCRYPTION_KEY`)   ·   statut : livré
**Objectif :** les secrets chiffrés de l'app (Stripe, SMTP, Mistral, Météo, portails fournisseurs) ne dépendent plus de `SECRET_KEY` (chantier « failles », F7 → I3).
**Constat [C] :** `EncryptedTextField` dérivait sa clé Fernet de `SECRET_KEY` et rendait **le texte chiffré** quand le
déchiffrement échouait : faire tourner `SECRET_KEY` détruisait en silence les secrets, une fuite de `SECRET_KEY` les livrait.
**Tâches :**
- [x] `backend/api/fields.py` : chiffrement sous `VAULT_ENCRYPTION_KEY` (`config/settings.py`, sans valeur par défaut) ;
  lecture de l'ancien chiffrement par `MultiFernet` ; valeur indéchiffrable traitée comme absente (journalisée sans sa
  valeur), sauf valeur historique en clair (pas de forme `gAAAAA…`)
- [x] Migration de données `backend/api/migrations/0025_rechiffrer_coffre.py` : rechiffre chaque valeur lisible (ancienne clé ou clair) en SQL brut ; laisse en base
  l'indéchiffrable ; rejouable ; retour arrière = remise sous l'ancienne clé
**Tests à passer avant de clore le lot :**
- [x] `backend/api/test_coffre.py` : chiffré sous la nouvelle clé et pas sous l'ancienne ; ancienne valeur relue puis rechiffrée ; clair
  historique relu puis rechiffré ; valeur corrompue ou d'une autre clé → absente, journal sans la valeur ; rotation de
  `SECRET_KEY` sans perte ; clé absente des réponses de l'API
**Vérifié le :** 2026-11-01 — non déployé. `bash chantiers/tests/essai.sh restauration` : 151 tests OK (11 dans `api/test_coffre.py`, joués aussi seuls) ; `makemigrations --check` : aucun changement. Les réponses gardaient alors le masque `••••••••` + 4 derniers caractères (8 pour Stripe) ; depuis `cc3268e` (en service le 2026-11-01), le masque seul ; une valeur indéchiffrable y donne désormais `''` au lieu d'un suffixe de texte chiffré.

## Mise en service — chantier « failles » (2026-11-01)
Les mentions « non déployé » ci-dessus datent d'avant cette mise en service. Image construite pendant
que l'ancienne tournait, `scripts/app-test.sh` : 151 tests OK, puis `up -d --no-build` ; ports
publiés sur `127.0.0.1` ; client Keycloak passé en PKCE S256 exigé, URI de retour réduites à celles de
l'app (`create-app-client.sh --pkce --prune-uris`) ; cloisonnement `lab-runner` 3/3 avant et après le durcissement du client, puis de nouveau 3/3 sur Keycloak 26.8.1.
Restent les vérifications en navigateur réel notées dans les lots (images, coffres de clés, envois).
