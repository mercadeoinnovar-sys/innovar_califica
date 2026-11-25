# main/forms.py
"""Django forms for INNOVAR SERVICE."""
import re
import html
from django import forms
from django.utils import timezone
from .models import Evaluation, Advisor, Location


def clean_colombian_phone(phone_raw):
    """
    Valida y formatea estrictamente un número celular de Colombia:
    - No permite letras, símbolos ni combinaciones erróneas.
    - Debe contener exactamente 10 dígitos numéricos.
    - Debe comenzar por el dígito 3 (rango oficial de telefonía móvil en Colombia).
    """
    if not phone_raw:
        raise forms.ValidationError("El número de teléfono celular es obligatorio.")

    # Remover cualquier caracter que no sea dígito
    digits = re.sub(r"\D", "", str(phone_raw).strip())

    # Si incluyó el prefijo de país colombiano +57 o 57 al inicio
    if digits.startswith("57") and len(digits) == 12:
        digits = digits[2:]

    if not digits:
        raise forms.ValidationError("Por favor ingresa un número celular válido (solo números, sin letras ni símbolos).")

    if len(digits) != 10:
        raise forms.ValidationError(
            f"El número celular en Colombia debe tener exactamente 10 dígitos numéricos. Has ingresado {len(digits)} dígitos."
        )

    if not digits.startswith("3"):
        raise forms.ValidationError(
            "Los números celulares en Colombia deben comenzar por el dígito 3 (ejemplo: 3101234567, 3209876543)."
        )

    return digits


def clean_colombian_cedula(cedula_raw, required=True):
    """
    Valida un número de cédula / documento colombiano para verificación en caja.
    Permite 5 a 12 dígitos numéricos y rechaza secuencias repetidas falsas.
    """
    digits = re.sub(r"\D", "", str(cedula_raw or "").strip())
    if not digits:
        if required:
            raise forms.ValidationError("El número de cédula es obligatorio para generar boletas y verificar en caja.")
        return ""

    if len(digits) < 5 or len(digits) > 12:
        raise forms.ValidationError(
            f"La cédula debe tener entre 5 y 12 dígitos numéricos (ingresaste {len(digits)})."
        )

    if len(set(digits)) == 1:
        raise forms.ValidationError("Por favor ingresa un número de cédula real y válido.")

    return digits


def clean_uppercase_name(name_raw):
    """Convierte el nombre completo a mayúsculas limpias sin etiquetas HTML."""
    if not name_raw:
        raise forms.ValidationError("El nombre completo es obligatorio.")
    clean = html.escape(str(name_raw).strip().upper())
    if len(clean) < 3:
        raise forms.ValidationError("Por favor ingresa tu nombre completo real.")
    return clean


class EvaluationForm(forms.ModelForm):
    """Formulario exclusivo para Calificación y Evaluación de Asesores Comerciales."""
    wants_raffle = forms.BooleanField(
        required=False,
        initial=False,
        label="¿Realizaste una compra >= $1'000.000 hoy y vas a registrar tu factura para boletas del sorteo?"
    )
    data_authorization = forms.BooleanField(
        required=True,
        initial=True,
        label="Autorizo el tratamiento de mis datos personales de acuerdo con la política de privacidad de Grupo Innovar."
    )

    class Meta:
        model = Evaluation
        fields = [
            "client_name",
            "client_phone",
            "client_cedula",
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
                "class": "form-control form-control-lg text-uppercase",
                "placeholder": "Tu nombre completo (Obligatorio)",
                "required": "required",
                "style": "text-transform: uppercase;"
            }),
            "client_phone": forms.TextInput(attrs={
                "class": "form-control form-control-lg",
                "placeholder": "Celular (10 dígitos, ej: 3101234567)",
                "required": "required",
                "type": "tel",
                "inputmode": "numeric",
                "maxlength": "10",
                "pattern": "3[0-9]{9}"
            }),
            "client_cedula": forms.TextInput(attrs={
                "class": "form-control form-control-lg font-monospace",
                "placeholder": "Ej: 1110456789 (solo números)",
                "inputmode": "numeric",
                "maxlength": "12",
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
        self.fields["advisor"].required = True
        self.fields["location"].required = True
        self.fields["client_name"].required = True
        self.fields["client_phone"].required = True
        self.fields["client_cedula"].required = False
        self.fields["data_authorization"].required = True
        self.fields["client_city"].required = False
        self.fields["comments"].required = False
        self.fields["overall_star"].initial = 5

    def clean_client_name(self):
        return clean_uppercase_name(self.cleaned_data.get("client_name"))

    def clean_client_phone(self):
        return clean_colombian_phone(self.cleaned_data.get("client_phone"))

    def clean(self):
        cleaned = super().clean()
        phone = cleaned.get("client_phone")
        advisor = cleaned.get("advisor")
        comments = cleaned.get("comments")
        wants_raffle = bool(cleaned.get("wants_raffle"))

        try:
            cleaned["client_cedula"] = clean_colombian_cedula(
                cleaned.get("client_cedula"),
                required=wants_raffle,
            )
        except forms.ValidationError as exc:
            self.add_error("client_cedula", exc)

        if comments:
            cleaned["comments"] = html.escape(comments.strip())

        # Anti-spam: una evaluación por asesor al día por el mismo número
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


class RaffleRegistrationForm(forms.ModelForm):
    """Formulario exclusivo para Registro de Facturas y Participación en Sorteos de Boletas."""
    data_authorization = forms.BooleanField(
        required=True,
        initial=True,
        label="Autorizo expresamente a Grupo Innovar Colombia para el tratamiento de mis datos personales conforme a la Ley 1581 de 2012 (Habeas Data)."
    )

    class Meta:
        model = Evaluation
        fields = [
            "client_name",
            "client_phone",
            "client_cedula",
            "location",
            "advisor",
            "invoice_amount",
            "invoice_number",
            "data_authorization",
        ]
        widgets = {
            "client_name": forms.TextInput(attrs={
                "class": "form-control form-control-lg text-uppercase",
                "placeholder": "NOMBRE COMPLETO DEL TITULAR (OBLIGATORIO)",
                "required": "required",
                "style": "text-transform: uppercase;"
            }),
            "client_phone": forms.TextInput(attrs={
                "class": "form-control form-control-lg",
                "placeholder": "CELULAR DE CONTACTO (10 DÍGITOS, EJ: 3101234567)",
                "required": "required",
                "type": "tel",
                "inputmode": "numeric",
                "maxlength": "10",
                "pattern": "3[0-9]{9}"
            }),
            "client_cedula": forms.TextInput(attrs={
                "class": "form-control form-control-lg font-monospace",
                "placeholder": "NÚMERO DE CÉDULA (OBLIGATORIO PARA CAJA)",
                "required": "required",
                "inputmode": "numeric",
                "maxlength": "12",
            }),
            "location": forms.Select(attrs={
                "class": "form-select form-select-lg fw-semibold",
                "required": "required"
            }),
            "advisor": forms.Select(attrs={
                "class": "form-select",
            }),
            "invoice_amount": forms.NumberInput(attrs={
                "class": "form-control form-control-lg fw-bold text-dark font-monospace",
                "placeholder": "Monto total de compra (ej: 1250000)",
                "min": "1000000",
                "step": "1000",
                "id": "id_invoice_amount",
                "required": "required"
            }),
            "invoice_number": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Número o consecutivo de factura física (ej: FE-10492)",
                "id": "id_invoice_number"
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["location"].queryset = Location.objects.all()
        self.fields["advisor"].queryset = Advisor.objects.filter(is_active=True).select_related('location')
        self.fields["client_name"].required = True
        self.fields["client_phone"].required = True
        self.fields["client_cedula"].required = True
        self.fields["location"].required = True
        self.fields["invoice_amount"].required = True
        self.fields["advisor"].required = False
        self.fields["invoice_number"].required = False
        self.fields["data_authorization"].required = True

    def clean_client_name(self):
        return clean_uppercase_name(self.cleaned_data.get("client_name"))

    def clean_client_phone(self):
        return clean_colombian_phone(self.cleaned_data.get("client_phone"))

    def clean_client_cedula(self):
        return clean_colombian_cedula(self.cleaned_data.get("client_cedula"), required=True)

    def clean_invoice_amount(self):
        amount = self.cleaned_data.get("invoice_amount")
        if not amount or amount <= 0:
            raise forms.ValidationError("Por favor ingresa o escanea el valor total de tu factura.")
        if amount < 1000000:
            raise forms.ValidationError(
                f"El monto mínimo de compra para participar en los sorteos es de $1'000.000 COP (tu factura registra ${amount:,.0f} COP)."
            )
        return amount


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
