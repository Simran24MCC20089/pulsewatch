from apscheduler.schedulers.background import BackgroundScheduler
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
scheduler = BackgroundScheduler(daemon=True)
