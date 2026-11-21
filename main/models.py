# main/models.py
"""Data models for Innovar Service MVP - Grupo Innovar."""
from django.db import models
from django.utils import timezone
from io import BytesIO
from django.core.files.base import ContentFile
import qrcode


class Location(models.Model):
    """Sede o ubicación donde opera el asesor."""
    name = models.CharField(max_length=120)
    city = models.CharField(max_length=100)
    address = models.CharField(max_length=255, blank=True, default="", help_text="Dirección física de la sala de ventas")

    class Meta:
        verbose_name = "Sede"
        verbose_name_plural = "Sedes"
        ordering = ["city", "name"]

    def __str__(self):
        return f"{self.name} - {self.city}"


class Advisor(models.Model):
    """Representa a un asesor comercial de Grupo Innovar."""
    full_name = models.CharField(max_length=150)
    identifier = models.CharField(max_length=50, unique=True)
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name="advisors")
    position = models.CharField(max_length=100, default="Asesor Comercial")
    is_active = models.BooleanField(default=True)
    photo = models.ImageField(upload_to="advisors/", blank=True, null=True)

    class Meta:
        verbose_name = "Asesor"
        verbose_name_plural = "Asesores"
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name

    @property
    def average_rating(self):
        """Promedio de estrellas (1-5) basado en evaluaciones válidas."""
        qs = self.evaluations.filter(is_valid=True)
        if not qs.exists():
            return None
        avg = qs.aggregate(models.Avg("overall_star"))['overall_star__avg']
        return round(avg, 2) if avg is not None else None

    @property
    def satisfaction_percentage(self):
        """Porcentaje de satisfacción basado en estrellas (5 estrellas = 100%)."""
        avg = self.average_rating
        if avg is None:
            return 0
        return int(round((avg / 5.0) * 100))

    @property
    def evaluation_count(self):
        return self.evaluations.filter(is_valid=True).count()


class Evaluation(models.Model):
    """Calificación enviada por un cliente al evaluar a un asesor."""
    client_name = models.CharField(max_length=150, blank=True)
    client_phone = models.CharField(max_length=30, blank=True)
    client_city = models.CharField(max_length=100, blank=True)
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="evaluations")
    advisor = models.ForeignKey(Advisor, on_delete=models.PROTECT, related_name="evaluations")

    # Preguntas de evaluación
    attention_quality = models.CharField(
        max_length=30,
        choices=[
            ("Excelente", "Excelente"),
            ("Buena", "Buena"),
            ("Regular", "Regular"),
            ("Mala", "Mala"),
        ],
        default="Excelente"
    )
    info_clarity = models.CharField(
        max_length=30,
        choices=[
            ("Sí, completamente", "Sí, completamente"),
            ("Parcialmente", "Parcialmente"),
            ("No", "No"),
        ],
        default="Sí, completamente"
    )
    product_knowledge = models.CharField(
        max_length=30,
        choices=[
            ("Sí", "Sí"),
            ("Más o menos", "Más o menos"),
            ("No", "No"),
        ],
        default="Sí"
    )
    disposition = models.CharField(
        max_length=30,
        choices=[
            ("Siempre", "Siempre"),
            ("Algunas veces", "Algunas veces"),
            ("No", "No"),
        ],
        default="Siempre"
    )
    recommendation = models.CharField(
        max_length=30,
        choices=[
            ("Definitivamente sí", "Definitivamente sí"),
            ("Tal vez", "Tal vez"),
            ("No", "No"),
        ],
        default="Definitivamente sí"
    )

    overall_star = models.PositiveSmallIntegerField(default=5)
    comments = models.TextField(blank=True)
    data_authorization = models.BooleanField(default=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    session_key = models.CharField(max_length=64, blank=True, null=True)

    # Módulo de Sorteos Comerciales de Grupo Innovar (1 Boleta x cada $1.000.000 COP)
    invoice_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text="Total pagado en factura")
    invoice_number = models.CharField(max_length=60, blank=True, help_text="Número o consecutivo de factura")
    invoice_image = models.ImageField(upload_to="invoices/", blank=True, null=True, help_text="Foto o escaneo de la factura física")
    tickets_count = models.PositiveIntegerField(default=0, help_text="Boletas asignadas (1 por cada millón)")
    ticket_codes = models.CharField(max_length=255, blank=True, help_text="Números de boleta asignados (ej: BOL-1001, BOL-1002)")

    created_at = models.DateTimeField(default=timezone.now)
    is_valid = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Evaluación"
        verbose_name_plural = "Evaluaciones"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["advisor", "created_at"]),
        ]

    def __str__(self):
        return f"Evaluación #{self.id} - {self.advisor.full_name} ({self.overall_star}★)"


class QRCode(models.Model):
    """Enlace QR único individual (por asesor) o general (por sede)."""
    code = models.CharField(max_length=100, unique=True)
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name="qr_codes")
    advisor = models.ForeignKey(Advisor, on_delete=models.CASCADE, null=True, blank=True, related_name="qr_codes")
    created_at = models.DateTimeField(auto_now_add=True)
    image = models.ImageField(upload_to="qr_codes/", blank=True, null=True)

    class Meta:
        verbose_name = "Código QR"
        verbose_name_plural = "Códigos QR"
        ordering = ["-created_at"]

    def __str__(self):
        return self.code

    @property
    def evaluation_path(self):
        if self.advisor:
            return f"/evaluar/{self.advisor.identifier}/"
        return f"/evaluar/sede/{self.location.id}/"

    @property
    def evaluation_url(self):
        return self.evaluation_path

    def generate_qr_image(self):
        """Genera y guarda la imagen PNG del código QR sin doble save."""
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=3
        )
        # La URL que el QR contendrá
        target_url = self.evaluation_path
        qr.add_data(target_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#121212", back_color="#FFFFFF")
        
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        file_name = f"qr_{self.code}.png"
        self.image.save(file_name, ContentFile(buffer.getvalue()), save=False)


class Badge(models.Model):
    """Insignias y reconocimientos automáticos al buen desempeño."""
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, help_text="Clase de icono de Bootstrap o Lucide, ej: bi-star-fill")
    color = models.CharField(max_length=20, default="#FF0000")
    advisors = models.ManyToManyField(Advisor, related_name="badges", blank=True)

    class Meta:
        verbose_name = "Insignia"
        verbose_name_plural = "Insignias"
        ordering = ["name"]

    def __str__(self):
        return self.name
