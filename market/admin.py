from django.contrib import admin
from .models import CollectionJob, Product, Snapshot

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("title", "platform", "shop", "created_at")
    search_fields = ("title", "shop", "url")

@admin.register(Snapshot)
class SnapshotAdmin(admin.ModelAdmin):
    list_display = ("product", "price", "currency", "sales", "source", "observed_at")
    list_filter = ("source", "currency")

@admin.register(CollectionJob)
class CollectionJobAdmin(admin.ModelAdmin):
    list_display = ("product", "status", "message", "created_at", "finished_at")
    readonly_fields = ("product", "status", "message", "created_at", "started_at", "finished_at")

    def has_add_permission(self, request):
        return False
