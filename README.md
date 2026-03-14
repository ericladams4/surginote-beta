# SurgiNote Beta

Password-protected beta web app for shorthand-to-operative-note generation.

## MVP scope
- Laparoscopic cholecystectomy
- Robotic cholecystectomy
- Open inguinal hernia repair
- Robotic inguinal hernia repair
- Open ventral/umbilical hernia repair

## Local setup
```bash
cd surginote_beta
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# add your values to .env
python app.py
```

Open:
- Beta app: http://127.0.0.1:5001
- Admin login: http://127.0.0.1:5001/admin-login

## Deployment
This repo is ready for a simple Render deployment.

Build command:
```bash
pip install -r requirements.txt
```

Start command:
```bash
gunicorn app:app
```

Environment variables:
- OPENAI_API_KEY
- BETA_PASSWORD
- ADMIN_PASSWORD
- FLASK_SECRET_KEY

## Important beta rule
Do not use PHI. Use synthetic or de-identified shorthand only.
