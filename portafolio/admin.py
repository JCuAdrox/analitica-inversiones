from django.contrib import admin

from .models import ConsultaSQL


@admin.register(ConsultaSQL)
class ConsultaSQLAdmin(admin.ModelAdmin):
    list_display = ("nombre", "slug", "visualizacion", "activa", "actualizada")
    list_filter = ("visualizacion", "activa")
    search_fields = ("nombre", "slug", "descripcion")