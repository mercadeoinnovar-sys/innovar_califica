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
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["advisor"].queryset = Advisor.objects.filter(is_active=True).select_related('location')
        self.fields["location"].queryset = Location.objects.all()
        self.fields["client_name"].required = False
        self.fields["client_phone"].required = False
        self.fields["client_city"].required = False
        self.fields["comments"].required = False
        self.fields["overall_star"].initial = 5

    def clean(self):
        cleaned = super().clean()
        phone = cleaned.get("client_phone")
        advisor = cleaned.get("advisor")
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
