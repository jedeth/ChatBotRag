import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'chatbot_rag.settings')

app = Celery('chatbot_rag')

# Charge la config depuis Django settings (préfixe CELERY_)
app.config_from_object('django.conf:settings', namespace='CELERY')

# Découvre automatiquement les tasks.py dans chaque app
app.autodiscover_tasks()
