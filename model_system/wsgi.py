import os
from django.core.wsgi import get_wsgi_application
from whitenoise import WhiteNoise

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'model_system.settings')

application = get_wsgi_application()

# المسار الصحيح الذي يستخدمه Render بعد collectstatic
STATIC_ROOT = '/opt/render/project/src/staticfiles'

# إضافة ملفات static
application = WhiteNoise(application)
application.add_files(STATIC_ROOT, prefix='static/')
