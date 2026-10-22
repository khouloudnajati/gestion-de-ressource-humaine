# PeopleFlow RH

Plateforme Django de gestion intelligente du personnel pour une entreprise laitière : employés, départements, congés, tableaux de bord par rôle, assistant RH et rapports PDF.

## Installation

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Ouvrez ensuite `http://127.0.0.1:8000/`.

## Rôles et fonctionnalités

- **Employé** : profil personnel, photo, changement de mot de passe, demandes de congé, historique et chatbot RH.
- **Responsable RH** : gestion des employés et départements, traitement des congés, statistiques, rapports PDF.
- **Administrateur** : accès Django Admin, comptes, documents RH et conversations enregistrées.

## Gemini, OpenAI et RAG

Copiez `.env.example` vers `.env`, puis définissez une clé API et le fournisseur souhaité. L’assistant peut utiliser Gemini ou OpenAI, avec un repli automatique vers le mode local si aucune clé n’est disponible. Déposez les documents internes `.pdf` ou `.txt` dans `documents_rh/`, ou importez-les dans **Documents RH** depuis l’administration. Le chatbot recherche d’abord les extraits utiles puis interroge le fournisseur IA si un contexte RAG est pertinent.

Les migrations sont incluses : aucune commande `makemigrations` n’est nécessaire pour le premier lancement.
