# main/forms.py
"""Django forms for INNOVAR SERVICE."""
from django import forms
from django.utils import timezone
from .models import Evaluation, Advisor, Location


class EvaluationForm(forms.ModelForm):
    data_authorization = forms.BooleanField(
        required=False,
        initial=True,
        label="Autorizo el tratamiento de mis datos personales de acuerdo con la política de privacidad de Grupo Innovar."
    )

    class Meta:
        model = Evaluation
        fields = [
            "client_name",
            "client_phone",
            "client_city",
            "location",
            "advisor",
            "attention_quality",
            "info_clarity",
            "product_knowledge",
            "disposition",
            "recommendation",
            "overall_star",
            "comments",
            "data_authorization",
            "invoice_amount",
            "invoice_number",
            "invoice_image",
        ]
        widgets = {
            "client_name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Tu nombre (opcional)"
            }),
            "client_phone": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Tu celular / WhatsApp (opcional)"
            }),
            "client_city": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ciudad (opcional)"
            }),
            "location": forms.Select(attrs={
                "class": "form-select"
            }),
            "advisor": forms.Select(attrs={
                "class": "form-select"
            }),
            "attention_quality": forms.RadioSelect(),
            "info_clarity": forms.RadioSelect(),
            "product_knowledge": forms.RadioSelect(),
            "disposition": forms.RadioSelect(),
            "recommendation": forms.RadioSelect(),
            "overall_star": forms.HiddenInput(),
            "comments": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "¿Quieres dejarle un mensaje, felicitación o sugerencia al asesor? (Opcional)"
            }),
            "invoice_amount": forms.NumberInput(attrs={
                "class": "form-control form-control-lg fw-bold text-dark",
                "placeholder": "Monto total pagado (ej: 1250000)",
                "min": "0",
                "step": "1000",
                "id": "id_invoice_amount"
            }),
            "invoice_number": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Número o consecutivo de factura (ej: FE-10492)",
                "id": "id_invoice_number"
            }),
            "invoice_image": forms.FileInput(attrs={
                "class": "form-control",
                "accept": "image/*",
                "capture": "environment",
                "id": "id_invoice_image"
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["advisor"].queryset = Advisor.objects.filter(is_active=True).select_related('location')
        self.fields["location"].queryset = Location.objects.all()
        self.fields["client_name"].required = False
        self.fields["client_phone"].required = False
        self.fields["client_city"].required = False
        self.fields["comments"].required = False
        self.fields["invoice_amount"].required = False
        self.fields["invoice_number"].required = False
        self.fields["invoice_image"].required = False
        self.fields["overall_star"].initial = 5

    def clean(self):
        cleaned = super().clean()
        phone = cleaned.get("client_phone")
        name = cleaned.get("client_name")
        advisor = cleaned.get("advisor")
        data_auth = cleaned.get("data_authorization")
        comments = cleaned.get("comments")

        # Cumplimiento Ley 1581 de 2012 (Habeas Data) & ISO 27001:
        # Si el cliente deja datos personales de contacto, la autorización explícita es obligatoria por ley
        if (phone or name) and not data_auth:
            self.add_error("data_authorization", "De conformidad con la Ley 1581 de 2012 (Habeas Data), debes autorizar el tratamiento de datos personales para registrar tu nombre o celular.")

        # Sanitización estricta de seguridad contra inyecciones XSS / HTML (ISO 27001)
        import html
        if comments:
            cleaned["comments"] = html.escape(comments.strip())
        if name:
            cleaned["client_name"] = html.escape(name.strip())

        # Regla de Negocio: Sorteos Comerciales de Grupo Innovar
        # 1 boleta por cada $1.000.000 COP en compras. Compras menores a 1 millón se ignoran en el registro del sorteo.
        inv_amount = cleaned.get("invoice_amount")
        if inv_amount and inv_amount >= 1000000:
            tickets = int(inv_amount // 1000000)
            cleaned["tickets_count"] = tickets
            # Se requiere nombre y celular para que el cliente pueda ser notificado si resulta ganador
            if not phone:
                self.add_error("client_phone", "Para asignar tus boletas del sorteo, por favor indica tu celular / WhatsApp de contacto.")
            if not name:
                self.add_error("client_name", "Para asignar tus boletas del sorteo, por favor indica tu nombre completo.")
        else:
            cleaned["tickets_count"] = 0

        if phone and advisor:
            today = timezone.now().date()
            already_evaluated = Evaluation.objects.filter(
                client_phone=phone,
                advisor=advisor,
                created_at__date=today,
            ).exists()
            if already_evaluated:
                raise forms.ValidationError("Ya has enviado una calificación para este asesor el día de hoy. ¡Agradecemos mucho tu valiosa opinión!")
        return cleaned


class AdvisorForm(forms.ModelForm):
    """Formulario administrativo para crear y editar asesores."""
    class Meta:
        model = Advisor
        fields = ["full_name", "identifier", "location", "position", "is_active", "photo"]
        widgets = {
            "full_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Nombre completo"}),
            "identifier": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: ASESOR-016"}),
            "location": forms.Select(attrs={"class": "form-select"}),
            "position": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: Asesor Comercial"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "photo": forms.FileInput(attrs={"class": "form-control"}),
        }
