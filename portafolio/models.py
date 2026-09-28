import re

from django.core.exceptions import ValidationError
from django.db import models


class ConsultaSQL(models.Model):
    class Visualizacion(models.TextChoices):
        TABLA = "tabla", "Tabla"
        DONA = "dona", "Dona"
        BARRAS = "barras", "Barras"

    slug = models.SlugField(unique=True)
    nombre = models.CharField(max_length=120)
    descripcion = models.TextField(blank=True)
    sql = models.TextField(
        help_text="Solo SELECT. Usa %(id_cliente)s como parametro si aplica."
    )
    visualizacion = models.CharField(
        max_length=10, choices=Visualizacion.choices, default=Visualizacion.TABLA
    )
    activa = models.BooleanField(default=True)
    actualizada = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "consulta SQL"
        verbose_name_plural = "consultas SQL"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre

    def clean(self):
        texto = self.sql.strip().rstrip(";").strip()
        if not re.match(r"(?is)^(select|with)\b", texto):
            raise ValidationError("La consulta debe empezar con SELECT o WITH.")
        if ";" in texto:
            raise ValidationError("Usa una sola sentencia, sin punto y coma intermedio.")
        prohibidas = r"\b(insert|update|delete|drop|alter|truncate|create|grant)\b"
        if re.search(prohibidas, texto, re.IGNORECASE):
            raise ValidationError("Solo se permiten consultas de lectura.")