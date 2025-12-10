from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('core.urls')),  # يحتوي كل الواجهات
]

# 👇 أثناء التطوير (DEBUG=True) استعمل helper العادي
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    # 👇 في الإنتاج (DEBUG=False) نخدم /media/ يدويًا
    urlpatterns += [
        re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
    ]
