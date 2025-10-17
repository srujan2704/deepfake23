# """project_settings URL Configuration
# """
# from django.contrib import admin
# from django.urls import path, include
# from . import views
# from .views import about, index, predict_page,cuda_full

# app_name = 'ml_app'
# handler404 = views.handler404

# urlpatterns = [
#     path('', index, name='home'),
#     path('about/', about, name='about'),
#     # path('predict/', predict_page, name='predict'),
#     path("predict2/", views.predict_api, name="predict_api"),

#     path('cuda_full/',cuda_full,name='cuda_full'),
# ]

# """project_settings URL Configuration
# """
# from django.contrib import admin
# from django.urls import path, include
# from django.conf import settings
# from django.conf.urls.static import static
# import os
# from . import views
# from .views import about, index, predict_page, cuda_full, predict_api

# app_name = 'ml_app'
# handler404 = views.handler404

# urlpatterns = [
#     path('', index, name='home'),
#     path('about/', about, name='about'),
#     # path('predict/', predict_page, name='predict'),
#     path("predict2/", predict_api, name="predict_api"),
#     path('cuda_full/', cuda_full, name='cuda_full'),
# ]

# # Serve media files (uploaded videos)
# if settings.DEBUG:
#     urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
#     urlpatterns += static('/uploaded_images/', document_root=os.path.join(settings.BASE_DIR, 'uploaded_images'))

"""project_settings URL Configuration
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
import os
from . import views
from .views import about, index, predict_page, cuda_full, predict_api , find_video_sources_api

app_name = 'ml_app'
handler404 = views.handler404

urlpatterns = [
    path('', index, name='home'),
    path('about/', about, name='about'),
    path("predict2/", predict_api, name="predict_api"),
    path('cuda_full/', cuda_full, name='cuda_full'),
    path('find-sources/', find_video_sources_api, name='find_sources'), 
    # path('api/videos/<int:video_id>/reverse-search/', views.video_reverse_search, name='video_reverse_search'),
    # path('api/test-reverse-search/', views.test_reverse_search, name='test_reverse_search'),
]

# Serve media files (uploaded videos)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static('/uploaded_images/', document_root=os.path.join(settings.PROJECT_DIR, 'uploaded_images'))