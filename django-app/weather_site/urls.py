from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    # the forecast app is the home page
    path("", include("forecast.urls")),
]