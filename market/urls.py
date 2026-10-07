from django.urls import path
from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("products/add/", views.product_edit, name="product_add"),
    path("products/<int:pk>/", views.product_detail, name="product_detail"),
    path("products/<int:pk>/edit/", views.product_edit, name="product_edit"),
    path("products/<int:pk>/collect/", views.collect_product, name="collect_product"),
    path("products/<int:pk>/status/", views.job_status, name="job_status"),
    path("import/", views.csv_import, name="csv_import"),
    path("export/", views.csv_export, name="csv_export"),
    path("template/", views.csv_template, name="csv_template"),
    path("tools/profit/", views.profit, name="profit"),
]
