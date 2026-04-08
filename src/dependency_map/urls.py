"""
dependency_map.urls
~~~~~~~~~~~~~~~~~~~
Include this in your project's URLconf::

    # myproject/urls.py
    from django.urls import include, path

    urlpatterns = [
        ...
        path("__depmap__/", include("dependency_map.urls")),
    ]

Registered URLs
---------------
GET  /                  → full interactive HTML page
GET  /refresh/          → JSON endpoint (called by the Refresh button)
"""
from django.urls import path

from . import views

app_name = "dependency_map"

urlpatterns = [
    path("",         views.DependencyMapView.as_view(),        name="index"),
    path("refresh/", views.DependencyMapRefreshView.as_view(), name="refresh"),
    path("version/", views.DependencyMapVersionView.as_view(), name="version"),
]
