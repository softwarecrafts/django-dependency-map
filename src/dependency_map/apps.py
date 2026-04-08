from django.apps import AppConfig


class DependencyMapConfig(AppConfig):
    name = "dependency_map"
    label = "dependency_map"
    verbose_name = "Dependency Map"
    default_auto_field = "django.db.models.BigAutoField"
    # Ensure the templates directory is discovered automatically via APP_DIRS
