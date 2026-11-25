# main/views.py
"""Views for INNOVAR SERVICE - Grupo Innovar."""
import csv
import re
import json
import base64
from io import BytesIO
from decimal import Decimal
from datetime import datetime
import qrcode
from PIL import Image, ImageEnhance, ImageOps
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from .models import Advisor, Evaluation, Location, Badge, QRCode
from .forms import EvaluationForm, RaffleRegistrationForm, AdvisorForm


def home(request):
    """Página de inicio institucional de INNOVAR SERVICE."""
    top_advisors = Advisor.objects.filter(is_active=True).annotate(
        eval_count=Count('evaluations', filter=Q(evaluations__is_valid=True)),
        avg_star=Avg('evaluations__overall_star', filter=Q(evaluations__is_valid=True))
    ).filter(eval_count__gte=5).order_by('-avg_star', '-eval_count')[:3]

    total_evals = Evaluation.objects.filter(is_valid=True).count()
    total_advisors = Advisor.objects.filter(is_active=True).count()
    avg_global = Evaluation.objects.filter(is_valid=True).aggregate(Avg('overall_star'))['overall_star__avg'] or 5.0

    return render(request, "main/home.html", {
        "top_advisors": top_advisors,
        "total_evals": total_evals,
        "total_advisors": total_advisors,
        "avg_global": round(avg_global, 1),
    })


def evaluate_advisor_direct(request, advisor_code):
    """Acceso QR directo por código o ID de asesor (Ej: /evaluar/ASESOR-001/). Selecciona al compañero automáticamente sin errores."""
    clean_code = str(advisor_code).strip()
    advisor = None
    if clean_code.isdigit():
        advisor = Advisor.objects.filter(id=int(clean_code), is_active=True).select_related('location').first()
    if not advisor:
        advisor = Advisor.objects.filter(identifier__iexact=clean_code, is_active=True).select_related('location').first()
    if not advisor:
        qr = QRCode.objects.filter(code__iexact=clean_code, advisor__isnull=False).select_related('advisor__location').first()
        if qr:
            advisor = qr.advisor
    if not advisor:
        return redirect("evaluate_es")
    return _process_evaluation(request, selected_advisor=advisor, selected_location=advisor.location)


def evaluate_location_direct(request, location_id):
    """Acceso QR directo por sede (Ej: /evaluar/sede/1/)."""
    location = get_object_or_404(Location, pk=location_id)
    return _process_evaluation(request, selected_advisor=None, selected_location=location)


def evaluate(request):
    """Formulario interactivo de evaluación con detección y bloqueo automático de asesor por QR."""
    advisor_param = (
        request.GET.get("advisor") or
        request.GET.get("asesor") or
        request.GET.get("code") or
        request.GET.get("qr") or
        request.GET.get("id") or
        request.GET.get("c")
    )
    location_id = request.GET.get("location") or request.GET.get("sede")

    selected_advisor = None
    selected_location = None

    if advisor_param:
        clean_adv = str(advisor_param).strip()
        if clean_adv.isdigit():
            selected_advisor = Advisor.objects.filter(id=int(clean_adv), is_active=True).select_related('location').first()
        if not selected_advisor:
            selected_advisor = Advisor.objects.filter(identifier__iexact=clean_adv, is_active=True).select_related('location').first()
        if not selected_advisor:
            qr = QRCode.objects.filter(code__iexact=clean_adv, advisor__isnull=False).select_related('advisor__location').first()
            if qr:
                selected_advisor = qr.advisor
        if selected_advisor:
            selected_location = selected_advisor.location

    elif location_id:
        if str(location_id).isdigit():
            selected_location = Location.objects.filter(id=int(location_id)).first()

    return _process_evaluation(request, selected_advisor=selected_advisor, selected_location=selected_location)


def get_client_ip(request):
    """Extrae la dirección IP real del cliente."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def _process_evaluation(request, selected_advisor=None, selected_location=None):
    """Lógica central para procesar y renderizar la calificación de clientes con control anti-fraude."""
    if not request.session.session_key:
        request.session.save()
    session_key = request.session.session_key
    client_ip = get_client_ip(request)

    # Control Anti-Fraude: verificar si ya votó por este asesor en las últimas 24 horas
    already_voted = False
    if selected_advisor:
        twenty_four_hours_ago = timezone.now() - timezone.timedelta(hours=24)
        fraud_filter = Q(advisor=selected_advisor, created_at__gte=twenty_four_hours_ago, is_valid=True)
        device_filter = Q(ip_address=client_ip)
        if session_key:
            device_filter |= Q(session_key=session_key)

        already_voted = Evaluation.objects.filter(fraud_filter & device_filter).exists()

    if request.method == "POST":
        post_data = request.POST.copy()
        
        # Si el asesor ya estaba identificado, forzar asesor y sede automáticamente
        if selected_advisor:
            post_data["advisor"] = str(selected_advisor.id)
            post_data["location"] = str(selected_advisor.location.id)
            post_data["client_city"] = selected_advisor.location.city

        form = EvaluationForm(post_data, request.FILES)
        if form.is_valid():
            if already_voted:
                form.add_error(None, "Ya has registrado una calificación para este asesor en las últimas 24 horas. ¡Agradecemos mucho tu valiosa opinión!")
            else:
                phone = form.cleaned_data.get("client_phone")
                now = timezone.now()

                # Control anti-redundancia: si el cliente califica varias veces en el mes, consolidar en 1 solo registro
                existing_monthly = Evaluation.objects.filter(
                    client_phone=phone,
                    created_at__year=now.year,
                    created_at__month=now.month,
                    is_valid=True
                ).first()

                if existing_monthly:
                    evaluation = existing_monthly
                    evaluation.advisor = form.cleaned_data["advisor"]
                    evaluation.location = form.cleaned_data["advisor"].location
                    evaluation.client_name = form.cleaned_data["client_name"]
                    evaluation.client_city = form.cleaned_data.get("client_city") or evaluation.location.city
                    evaluation.attention_quality = form.cleaned_data["attention_quality"]
                    evaluation.info_clarity = form.cleaned_data["info_clarity"]
                    evaluation.product_knowledge = form.cleaned_data["product_knowledge"]
                    evaluation.disposition = form.cleaned_data["disposition"]
                    evaluation.recommendation = form.cleaned_data["recommendation"]
                    evaluation.overall_star = form.cleaned_data["overall_star"]
                    if form.cleaned_data.get("comments"):
                        evaluation.comments = form.cleaned_data["comments"]
                    evaluation.data_authorization = form.cleaned_data["data_authorization"]
                    evaluation.ip_address = client_ip
                    evaluation.session_key = session_key
                    evaluation.created_at = now
                    evaluation.save()
                else:
                    evaluation = form.save(commit=False)
                    evaluation.location = evaluation.advisor.location
                    if not evaluation.client_city:
                        evaluation.client_city = evaluation.advisor.location.city
                    evaluation.ip_address = client_ip
                    evaluation.session_key = session_key
                    evaluation.invoice_amount = None
                    evaluation.invoice_number = ""
                    evaluation.invoice_image = None
                    evaluation.tickets_count = 0
                    evaluation.ticket_codes = ""
                    evaluation.save()

                return render(request, "main/thank_you.html", {
                    "evaluation": evaluation,
                    "advisor": evaluation.advisor,
                    "is_advisor_evaluation": True
                })
    else:
        initial = {}
        if selected_advisor:
            initial["advisor"] = selected_advisor.id
            initial["location"] = selected_advisor.location.id
            initial["client_city"] = selected_advisor.location.city
        elif selected_location:
            initial["location"] = selected_location.id
            initial["client_city"] = selected_location.city

        form = EvaluationForm(initial=initial)

    advisors_list = Advisor.objects.filter(is_active=True).select_related('location')
    locations_list = Location.objects.all()

    return render(request, "main/evaluate.html", {
        "form": form,
        "selected_advisor": selected_advisor,
        "selected_location": selected_location,
        "advisors_list": advisors_list,
        "locations_list": locations_list,
        "already_voted": already_voted,
    })


def add_invoice_to_evaluation(request, evaluation_id):
    """
    Asocia la factura escaneada o ingresada directamente a la evaluación recién completada.
    No solicita ni sala ni asesor (se heredan automáticamente del asesor evaluado).
    Asigna 1 boleta oficial por cada $1'000.000 COP facturados.
    """
    evaluation = get_object_or_404(Evaluation, id=evaluation_id)

    if request.method == "POST":
        raw_amount = request.POST.get("invoice_amount", "").strip()
        raw_number = request.POST.get("invoice_number", "").strip()

        # Limpiar cualquier caracter que no sea dígito
        clean_amount = re.sub(r"[^\d]", "", raw_amount)
        try:
            amount = Decimal(clean_amount) if clean_amount else Decimal("0")
        except Exception:
            amount = Decimal("0")

        if amount >= Decimal("1000000"):
            evaluation.invoice_amount = amount
            if raw_number:
                evaluation.invoice_number = raw_number
            evaluation.tickets_count = int(amount // Decimal("1000000"))
            codes = [f"INV-{evaluation.id:04d}-{i+1}" for i in range(evaluation.tickets_count)]
            evaluation.ticket_codes = ", ".join(codes)
            evaluation.save(update_fields=["invoice_amount", "invoice_number", "tickets_count", "ticket_codes"])
            messages.success(request, f"¡Felicitaciones! Se han generado {evaluation.tickets_count} boletas oficiales a tu nombre.")
        elif amount > 0:
            evaluation.invoice_amount = amount
            if raw_number:
                evaluation.invoice_number = raw_number
            evaluation.tickets_count = 0
            evaluation.ticket_codes = ""
            evaluation.save(update_fields=["invoice_amount", "invoice_number", "tickets_count", "ticket_codes"])
            messages.warning(request, "El monto de la factura no alcanza el mínimo de $1'000.000 COP para obtener boletas del sorteo.")

        return render(request, "main/thank_you.html", {
            "evaluation": evaluation,
            "advisor": evaluation.advisor,
            "is_advisor_evaluation": True,
            "tickets_generated": evaluation.tickets_count > 0,
        })

    return render(request, "main/thank_you.html", {
        "evaluation": evaluation,
        "advisor": evaluation.advisor,
        "is_advisor_evaluation": True,
    })


def raffle_register(request):
    """
    Las boletas de sorteo se generan exclusivamente tras calificar al asesor comercial.
    Si se accede a esta ruta directamente, se redirige a calificar al asesor.
    """
    messages.info(request, "Para obtener tus boletas del sorteo, califica primero la atención de tu asesor comercial.")
    return redirect("evaluate_es")


def ranking(request):
    """Módulo de Ranking con podio, filtros por ciudad, sede y ponderación."""
    city_filter = request.GET.get("city", "")
    location_filter = request.GET.get("location", "")
    time_filter = request.GET.get("period", "all")

    eval_filter = Q(evaluations__is_valid=True)
    if time_filter == "month":
        first_day_month = timezone.now().replace(day=1, hour=0, minute=0, second=0)
        eval_filter &= Q(evaluations__created_at__gte=first_day_month)

    qs = Advisor.objects.filter(is_active=True).select_related('location').prefetch_related('badges')

    if city_filter:
        qs = qs.filter(location__city=city_filter)
    if location_filter:
        qs = qs.filter(location_id=location_filter)

    advisors_annotated = qs.annotate(
        eval_count=Count('evaluations', filter=eval_filter),
        avg_star=Avg('evaluations__overall_star', filter=eval_filter)
    )

    official_ranking = advisors_annotated.filter(eval_count__gte=5).order_by('-avg_star', '-eval_count')
    pending_advisors = advisors_annotated.filter(eval_count__lt=5).order_by('-eval_count', '-avg_star')

    # Lista única y ordenada de ciudades oficiales (sin redundancias)
    cities = sorted(list({c.strip() for c in Location.objects.values_list('city', flat=True) if c}))
    
    # Sedes filtradas según la ciudad seleccionada
    if city_filter:
        locations = Location.objects.filter(city=city_filter)
    else:
        locations = Location.objects.all()

    podium = list(official_ranking[:3])
    rest_of_ranking = list(official_ranking[3:])

    return render(request, "main/ranking.html", {
        "podium": podium,
        "rest_of_ranking": rest_of_ranking,
        "pending_advisors": pending_advisors,
        "cities": cities,
        "locations": locations,
        "selected_city": city_filter,
        "selected_location": location_filter,
        "selected_period": time_filter,
    })


def advisor_detail(request, advisor_id):
    """Perfil motivacional y resultados individuales del asesor."""
    advisor = get_object_or_404(Advisor.objects.select_related('location').prefetch_related('badges'), pk=advisor_id)
    evaluations = advisor.evaluations.filter(is_valid=True).order_by('-created_at')

    all_ranked = list(Advisor.objects.filter(is_active=True).annotate(
        eval_count=Count('evaluations', filter=Q(evaluations__is_valid=True)),
        avg_star=Avg('evaluations__overall_star', filter=Q(evaluations__is_valid=True))
    ).filter(eval_count__gte=5).order_by('-avg_star', '-eval_count').values_list('id', flat=True))

    rank_position = None
    if advisor.id in all_ranked:
        rank_position = all_ranked.index(advisor.id) + 1

    stars_breakdown = {
        5: evaluations.filter(overall_star=5).count(),
        4: evaluations.filter(overall_star=4).count(),
        3: evaluations.filter(overall_star=3).count(),
        2: evaluations.filter(overall_star=2).count(),
        1: evaluations.filter(overall_star=1).count(),
    }

    qr = QRCode.objects.filter(advisor=advisor).first()

    return render(request, "main/advisor_detail.html", {
        "advisor": advisor,
        "evaluations": evaluations,
        "rank_position": rank_position,
        "stars_breakdown": stars_breakdown,
        "qr": qr,
    })


# ==============================================================================
# SUITE ADMINISTRATIVA CON MENÚ LATERAL (SIDEBAR) & CONTROL DE ACCESO
# ==============================================================================

def admin_login(request):
    """Inicio de sesión administrativo seguro para el equipo de Grupo Innovar."""
    if request.user.is_authenticated:
        return redirect("admin_dashboard")

    error = None
    if request.method == "POST":
        u = request.POST.get("username", "").strip()
        p = request.POST.get("password", "").strip()
        user = authenticate(request, username=u, password=p)
        if user is not None:
            login(request, user)
            return redirect("admin_dashboard")
        else:
            error = "Credenciales incorrectas. Verifica tu usuario y contraseña de Grupo Innovar."

    return render(request, "admin_login.html", {"error": error})


def admin_logout(request):
    """Cierre de sesión administrativo seguro."""
    logout(request)
    messages.info(request, "Has cerrado sesión correctamente.")
    return redirect("home")


@login_required(login_url='admin_login')
def admin_dashboard(request):
    """Dashboard empresarial con métricas ejecutivas y gráficos."""
    total_advisors = Advisor.objects.count()
    active_advisors = Advisor.objects.filter(is_active=True).count()
    total_evals = Evaluation.objects.filter(is_valid=True).count()
    avg_rating = Evaluation.objects.filter(is_valid=True).aggregate(Avg('overall_star'))['overall_star__avg'] or 0.0

    now = timezone.now()
    first_day_month = now.replace(day=1, hour=0, minute=0, second=0)
    month_evals = Evaluation.objects.filter(is_valid=True, created_at__gte=first_day_month).count()
    satisfaction_rate = int(round((avg_rating / 5.0) * 100)) if avg_rating else 0

    # Casos críticos y semáforo de riesgo (1 y 2 estrellas)
    critical_evals = Evaluation.objects.filter(is_valid=True, overall_star__lte=2).select_related('advisor', 'location').order_by('-created_at')[:6]
    critical_count = Evaluation.objects.filter(is_valid=True, overall_star__lte=2).count()

    # Boletas de sorteo acumuladas (compras >= 1 millón)
    raffle_tickets_count = Evaluation.objects.filter(is_valid=True, tickets_count__gt=0).aggregate(Sum('tickets_count'))['tickets_count__sum'] or 0

    # Gráficos
    star_distribution = [
        Evaluation.objects.filter(is_valid=True, overall_star=s).count()
        for s in [5, 4, 3, 2, 1]
    ]

    cities_stats = Evaluation.objects.filter(is_valid=True).values('location__city').annotate(total=Count('id')).order_by('-total')
    city_labels = [c['location__city'] for c in cities_stats]
    city_counts = [c['total'] for c in cities_stats]

    recent_evals = Evaluation.objects.filter(is_valid=True).select_related('advisor', 'location').order_by('-created_at')[:10]

    return render(request, "main/admin_dashboard.html", {
        "total_advisors": total_advisors,
        "active_advisors": active_advisors,
        "total_evals": total_evals,
        "avg_rating": round(avg_rating, 2),
        "month_evals": month_evals,
        "satisfaction_rate": satisfaction_rate,
        "critical_evals": critical_evals,
        "critical_count": critical_count,
        "raffle_tickets_count": raffle_tickets_count,
        "recent_evals": recent_evals,
        "star_distribution": star_distribution,
        "city_labels": city_labels,
        "city_counts": city_counts,
        "active_tab": "dashboard",
    })


@login_required(login_url='admin_login')
def admin_advisors(request):
    """Módulo de Gestión de Asesores (Listado, creación y edición)."""
    if request.method == "POST":
        form = AdvisorForm(request.POST, request.FILES)
        if form.is_valid():
            advisor = form.save(commit=False)
            if "photo" in request.FILES:
                try:
                    p_file = request.FILES["photo"]
                    p_img = Image.open(p_file)
                    if p_img.mode in ("RGBA", "P"):
                        p_img = p_img.convert("RGB")
                    p_img.thumbnail((300, 300), Image.Resampling.LANCZOS)
                    p_buf = BytesIO()
                    p_img.save(p_buf, format="JPEG", quality=85, optimize=True)
                    advisor.photo_base64 = f"data:image/jpeg;base64,{base64.b64encode(p_buf.getvalue()).decode('utf-8')}"
                except Exception as err:
                    print("Error procesando foto:", err)
            advisor.save()

            # Generar QR para el nuevo asesor automáticamente
            code_adv = f"QR-{advisor.identifier}"
            qr_obj, _ = QRCode.objects.get_or_create(code=code_adv, defaults={"location": advisor.location, "advisor": advisor})
            qr_obj.location = advisor.location
            qr_obj.advisor = advisor
            qr_obj.generate_qr_image()
            qr_obj.save()
            messages.success(request, f"¡Asesor {advisor.full_name} registrado y código QR generado exitosamente!")
            return redirect("admin_advisors")
    else:
        form = AdvisorForm()

    advisors_list = Advisor.objects.select_related('location').annotate(
        eval_count=Count('evaluations', filter=Q(evaluations__is_valid=True)),
        avg_star=Avg('evaluations__overall_star', filter=Q(evaluations__is_valid=True))
    ).order_by('full_name')

    locations = Location.objects.all()

    return render(request, "main/admin_advisors.html", {
        "advisors_list": advisors_list,
        "locations": locations,
        "form": form,
        "active_tab": "advisors",
    })


@login_required(login_url='admin_login')
def admin_advisor_edit(request, advisor_id):
    """Edición completa de un asesor: datos, sede y actualización de fotografía."""
    advisor = get_object_or_404(Advisor, pk=advisor_id)
    if request.method == "POST":
        full_name = request.POST.get("full_name", "").strip()
        identifier = request.POST.get("identifier", "").strip()
        position = request.POST.get("position", "").strip()
        location_id = request.POST.get("location")
        is_active = request.POST.get("is_active") == "on"

        if full_name:
            advisor.full_name = full_name
        if identifier:
            advisor.identifier = identifier
        if position:
            advisor.position = position
        if location_id:
            advisor.location_id = int(location_id)
        advisor.is_active = is_active

        if "photo" in request.FILES:
            try:
                p_file = request.FILES["photo"]
                p_img = Image.open(p_file)
                if p_img.mode in ("RGBA", "P"):
                    p_img = p_img.convert("RGB")
                p_img.thumbnail((300, 300), Image.Resampling.LANCZOS)
                p_buf = BytesIO()
                p_img.save(p_buf, format="JPEG", quality=85, optimize=True)
                advisor.photo_base64 = f"data:image/jpeg;base64,{base64.b64encode(p_buf.getvalue()).decode('utf-8')}"
            except Exception as err:
                print("Error procesando foto:", err)

        advisor.save()
        messages.success(request, f"¡Información y fotografía de {advisor.full_name} actualizadas exitosamente!")
        return redirect("admin_advisors")

    return redirect("admin_advisors")


@login_required(login_url='admin_login')
def admin_locations(request):
    """Módulo de Gestión de Sedes (Las 9 sedes oficiales de Grupo Innovar)."""
    locations_list = Location.objects.annotate(
        advisor_count=Count('advisors', distinct=True),
        eval_count=Count('evaluations', distinct=True)
    ).order_by('city', 'name')

    return render(request, "main/admin_locations.html", {
        "locations_list": locations_list,
        "active_tab": "locations",
    })


@login_required(login_url='admin_login')
def admin_evaluations(request):
    """Módulo de Consulta de Evaluaciones con búsqueda y filtros."""
    search_query = request.GET.get("q", "")
    star_query = request.GET.get("star", "")
    city_query = request.GET.get("city", "")

    evals = Evaluation.objects.filter(is_valid=True).select_related('advisor', 'location')

    if search_query:
        evals = evals.filter(
            Q(advisor__full_name__icontains=search_query) |
            Q(comments__icontains=search_query) |
            Q(client_name__icontains=search_query) |
            Q(location__name__icontains=search_query)
        )
    if star_query == "critical":
        evals = evals.filter(overall_star__lte=2)
    elif star_query and star_query.isdigit():
        evals = evals.filter(overall_star=int(star_query))
    if city_query:
        evals = evals.filter(location__city=city_query)

    evaluations_list = evals.order_by('-created_at')[:50]
    cities = sorted(list({c.strip() for c in Location.objects.values_list('city', flat=True) if c}))

    return render(request, "main/admin_evaluations.html", {
        "evaluations_list": evaluations_list,
        "cities": cities,
        "search_query": search_query,
        "selected_star": star_query,
        "selected_city": city_query,
        "active_tab": "evaluations",
    })


@login_required(login_url='admin_login')
def admin_raffle(request):
    """Módulo exclusivo para Administradores: Registro de Facturas y Sorteos de Productos (Grupo Innovar)."""
    city_filter = request.GET.get("city", "")
    search_query = request.GET.get("q", "")

    qs = Evaluation.objects.filter(is_valid=True, tickets_count__gt=0).select_related('advisor', 'location')

    if city_filter:
        qs = qs.filter(location__city=city_filter)
    if search_query:
        qs = qs.filter(
            Q(client_name__icontains=search_query) |
            Q(client_phone__icontains=search_query) |
            Q(invoice_number__icontains=search_query) |
            Q(ticket_codes__icontains=search_query) |
            Q(advisor__full_name__icontains=search_query)
        )

    raffle_entries = qs.order_by('-created_at')

    # Métricas consolidadas del sorteo
    total_tickets = Evaluation.objects.filter(is_valid=True, tickets_count__gt=0).aggregate(Sum('tickets_count'))['tickets_count__sum'] or 0
    total_participants = Evaluation.objects.filter(is_valid=True, tickets_count__gt=0).count()
    total_sales_amount = Evaluation.objects.filter(is_valid=True, tickets_count__gt=0).aggregate(Sum('invoice_amount'))['invoice_amount__sum'] or 0

    cities = sorted(list({c.strip() for c in Location.objects.values_list('city', flat=True) if c}))

    # Listado plano de todas las boletas individuales para la ruleta
    tickets_list = []
    for ev in raffle_entries:
        if ev.ticket_codes:
            codes = [c.strip() for c in ev.ticket_codes.split(',') if c.strip()]
            client_name = (ev.client_name or "Cliente Anónimo").strip()
            client_phone = (ev.client_phone or "").strip()
            client_key = (client_phone or client_name).lower()
            for c in codes:
                tickets_list.append({
                    "eval_id": ev.id,
                    "client_key": client_key,
                    "ticket": c,
                    "client": client_name,
                    "phone": client_phone,
                    "location": f"{ev.location.name} ({ev.location.city})" if ev.location else "General",
                    "amount": f"${ev.invoice_amount:,.0f} COP" if ev.invoice_amount else "$0 COP",
                    "advisor": ev.advisor.full_name if ev.advisor else "Sin asesor",
                    "invoice_url": ev.invoice_image.url if ev.invoice_image else "",
                    "invoice_number": ev.invoice_number or "N/A"
                })

    return render(request, "main/admin_raffle.html", {
        "raffle_entries": raffle_entries,
        "total_tickets": total_tickets,
        "total_participants": total_participants,
        "total_sales_amount": total_sales_amount,
        "cities": cities,
        "selected_city": city_filter,
        "search_query": search_query,
        "active_tab": "raffle",
        "tickets_list_json": json.dumps(tickets_list),
    })


@login_required(login_url='admin_login')
def admin_reports(request):
    """Módulo de Reportes y Analítica con exportación e informe ejecutivo."""
    total_evals = Evaluation.objects.filter(is_valid=True).count()
    avg_rating = Evaluation.objects.filter(is_valid=True).aggregate(Avg('overall_star'))['overall_star__avg'] or 5.0
    
    # Distribución por sede oficial
    sede_stats = Location.objects.annotate(
        total_evals=Count('evaluations', filter=Q(evaluations__is_valid=True)),
        avg_stars=Avg('evaluations__overall_star', filter=Q(evaluations__is_valid=True))
    ).order_by('-total_evals')

    # Desempeño regional por Ciudad (Ibagué, Girardot y Neiva)
    city_stats = Location.objects.values('city').annotate(
        total_evals=Count('evaluations', filter=Q(evaluations__is_valid=True)),
        avg_stars=Avg('evaluations__overall_star', filter=Q(evaluations__is_valid=True)),
        advisor_count=Count('advisors', distinct=True)
    ).order_by('-total_evals')

    return render(request, "main/admin_reports.html", {
        "total_evals": total_evals,
        "avg_rating": round(avg_rating, 2),
        "sede_stats": sede_stats,
        "city_stats": city_stats,
        "active_tab": "reports",
    })


@login_required(login_url='admin_login')
def admin_settings(request):
    """Módulo de Configuración general del sistema."""
    return render(request, "main/admin_settings.html", {
        "active_tab": "settings",
    })


@login_required(login_url='admin_login')
def qr_management(request):
    """Gestión de códigos QR: individuales por asesor y generales por sede."""
    advisor_qrs = QRCode.objects.filter(advisor__isnull=False).select_related('advisor', 'location')
    location_qrs = QRCode.objects.filter(advisor__isnull=True).select_related('location')

    return render(request, "main/qr_management.html", {
        "advisor_qrs": advisor_qrs,
        "location_qrs": location_qrs,
        "active_tab": "qrcodes",
    })


def print_counter_display(request, advisor_id=None, location_id=None):
    """Hablador de mostrador listo para imprimir en tamaño carta/acrílico."""
    advisor = None
    location = None
    qr = None
    target_path = "/evaluar/"

    if advisor_id:
        advisor = get_object_or_404(Advisor.objects.select_related('location'), pk=advisor_id)
        location = advisor.location
        qr = QRCode.objects.filter(advisor=advisor).first()
        target_path = f"/evaluar/{advisor.identifier}/"
    elif location_id:
        location = get_object_or_404(Location, pk=location_id)
        qr = QRCode.objects.filter(location=location, advisor__isnull=True).first()
        target_path = f"/evaluar/sede/{location.id}/"

    full_evaluation_url = request.build_absolute_uri(target_path)

    return render(request, "main/print_display.html", {
        "advisor": advisor,
        "location": location,
        "qr": qr,
        "target_path": target_path,
        "full_evaluation_url": full_evaluation_url,
    })


def sitemap_xml(request):
    """Genera dinámicamente el Sitemap para indexación en Google Search Console."""
    advisors = Advisor.objects.filter(is_active=True)
    domain = request.build_absolute_uri('/')[:-1]
    return render(request, "seo/sitemap.xml", {
        "advisors": advisors,
        "domain": domain,
    }, content_type="application/xml")


def robots_txt(request):
    """Archivo robots.txt optimizado para motores de búsqueda."""
    content = """User-agent: *
Allow: /
Allow: /ranking/
Allow: /evaluar/
Disallow: /admin-dashboard/
Disallow: /admin/
Disallow: /export-csv/

Sitemap: {}/sitemap.xml
""".format(request.build_absolute_uri('/')[:-1])
    return HttpResponse(content, content_type="text/plain")


@login_required(login_url='admin_login')
def export_evaluations_csv(request):
    """Exportar listado de calificaciones a CSV compatible con Excel."""
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = 'attachment; filename="evaluaciones_innovar_service.csv"'

    writer = csv.writer(response)
    writer.writerow([
        "ID", "Fecha y Hora", "Asesor", "Documento", "Sede", "Ciudad",
        "Estrellas", "Atención", "Claridad Info", "Conocimiento",
        "Disposición", "Recomienda", "Cliente", "Celular", "Autorización Habeas Data",
        "Monto Factura (COP)", "N° Factura", "Boletas Sorteo", "Códigos Boletas",
        "Comentarios", "IP Auditoría"
    ])

    evaluations = Evaluation.objects.filter(is_valid=True).select_related('advisor', 'location').order_by('-created_at')
    for ev in evaluations:
        writer.writerow([
            ev.id,
            ev.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            ev.advisor.full_name,
            ev.advisor.identifier,
            ev.location.name,
            ev.location.city,
            ev.overall_star,
            ev.attention_quality,
            ev.info_clarity,
            ev.product_knowledge,
            ev.disposition,
            ev.recommendation,
            ev.client_name or "Anónimo",
            ev.client_phone or "No registrado",
            "SÍ (Aceptada)" if ev.data_authorization else "NO",
            float(ev.invoice_amount) if ev.invoice_amount else 0,
            ev.invoice_number or "N/D",
            ev.tickets_count,
            ev.ticket_codes or "N/D",
            ev.comments or "",
            ev.ip_address or "N/D"
        ])

    return response


def _get_consolidated_clients_dict(qs=None):
    """Consolida las evaluaciones por número celular único de cliente."""
    if qs is None:
        qs = Evaluation.objects.filter(is_valid=True).exclude(client_phone="").select_related('advisor', 'location').order_by('-created_at')

    clients_dict = {}
    for ev in qs:
        phone = ev.client_phone.strip()
        if not phone:
            continue
        if phone not in clients_dict:
            clients_dict[phone] = {
                "name": ev.client_name or "Cliente en Mostrador",
                "phone": phone,
                "city": ev.location.city if ev.location else "Ibagué",
                "location": ev.location.name if ev.location else "Mostrador General",
                "advisor": ev.advisor.full_name if ev.advisor else "Atención en Mostrador",
                "visits": 1,
                "sales": float(ev.invoice_amount or 0),
                "tickets": ev.tickets_count,
                "codes": ev.ticket_codes,
                "invoice_number": ev.invoice_number,
                "last_seen": ev.created_at.strftime("%d/%m/%Y %I:%M %p"),
                "auth": "AUTORIZADO (Ley 1581)" if ev.data_authorization else "NO"
            }
        else:
            c = clients_dict[phone]
            c["visits"] += 1
            c["sales"] += float(ev.invoice_amount or 0)
            c["tickets"] += ev.tickets_count
            if ev.ticket_codes:
                c["codes"] = (c["codes"] + ", " + ev.ticket_codes) if c["codes"] else ev.ticket_codes
            if ev.client_name and (not c["name"] or c["name"] == "Cliente en Mostrador"):
                c["name"] = ev.client_name
    return clients_dict


@login_required(login_url='admin_login')
def admin_clients(request):
    """Módulo Oficial de Clientes Registrados de Grupo Innovar (Deduplicado por Celular)."""
    city_filter = request.GET.get("city", "")
    raffle_filter = request.GET.get("raffle", "")
    q = request.GET.get("q", "").strip()

    qs = Evaluation.objects.filter(is_valid=True).exclude(client_phone="").select_related('advisor', 'location').order_by('-created_at')

    if city_filter:
        qs = qs.filter(location__city=city_filter)

    if q:
        qs = qs.filter(
            Q(client_name__icontains=q) |
            Q(client_phone__icontains=q) |
            Q(invoice_number__icontains=q) |
            Q(ticket_codes__icontains=q)
        )

    clients_dict = {}
    for ev in qs:
        phone = ev.client_phone.strip()
        if not phone:
            continue
        if phone not in clients_dict:
            clients_dict[phone] = {
                "client_name": ev.client_name or "Cliente en Mostrador",
                "client_phone": phone,
                "city": ev.location.city if ev.location else (ev.client_city or "Ibagué"),
                "location_name": ev.location.name if ev.location else "Mostrador General",
                "advisor_name": ev.advisor.full_name if ev.advisor else "Atención en Mostrador",
                "total_visits": 1,
                "total_sales": float(ev.invoice_amount or 0),
                "total_tickets": ev.tickets_count,
                "ticket_codes": ev.ticket_codes,
                "invoice_number": ev.invoice_number,
                "last_seen": ev.created_at,
                "overall_star": ev.overall_star,
                "data_authorization": ev.data_authorization,
            }
        else:
            c = clients_dict[phone]
            c["total_visits"] += 1
            c["total_sales"] += float(ev.invoice_amount or 0)
            c["total_tickets"] += ev.tickets_count
            if ev.ticket_codes:
                if c["ticket_codes"]:
                    c["ticket_codes"] += ", " + ev.ticket_codes
                else:
                    c["ticket_codes"] = ev.ticket_codes
            if ev.client_name and (not c["client_name"] or c["client_name"] == "Cliente en Mostrador"):
                c["client_name"] = ev.client_name

    unique_clients = list(clients_dict.values())

    if raffle_filter == "con_boletas":
        unique_clients = [c for c in unique_clients if c["total_tickets"] > 0]
    elif raffle_filter == "sin_boletas":
        unique_clients = [c for c in unique_clients if c["total_tickets"] == 0]

    total_clients = len(unique_clients)
    unique_phones = len(unique_clients)
    raffle_clients = sum(1 for c in unique_clients if c["total_tickets"] > 0)
    total_sales = sum(c["total_sales"] for c in unique_clients)

    phone_list_str = ", ".join(c["client_phone"] for c in unique_clients)

    return render(request, "main/admin_clients.html", {
        "active_tab": "clients",
        "clients": unique_clients,
        "city_filter": city_filter,
        "raffle_filter": raffle_filter,
        "q": q,
        "total_clients": total_clients,
        "unique_phones": unique_phones,
        "raffle_clients": raffle_clients,
        "total_sales": total_sales,
        "phone_list_str": phone_list_str,
        "cities": ["Ibagué", "Girardot", "Neiva", "Fusagasugá"],
    })


@login_required(login_url='admin_login')
def export_clients_excel(request):
    """Exporta el directorio de clientes en formato Microsoft Excel (.xlsx) corporativo de alta calidad."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Clientes Registrados"

    # Encabezado corporativo
    ws.merge_cells("A1:K1")
    title_cell = ws["A1"]
    title_cell.value = "GRUPO INNOVAR - DIRECTORIO OFICIAL DE CLIENTES REGISTRADOS"
    title_cell.font = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
    title_cell.fill = PatternFill(start_color="E11D48", end_color="E11D48", fill_type="solid")
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 36

    ws.merge_cells("A2:K2")
    sub_cell = ws["A2"]
    now_str = timezone.now().strftime("%d/%m/%Y %I:%M %p")
    sub_cell.value = f"Reporte oficial para auditoría comercial y sorteos | Generado el: {now_str} | Cumplimiento Ley 1581 de 2012"
    sub_cell.font = Font(name="Calibri", size=9, italic=True, color="475569")
    sub_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 20

    headers = [
        "#",
        "Nombre del Cliente (Titular)",
        "Celular / WhatsApp",
        "Ciudad",
        "Sede de Atención",
        "Asesor Comercial",
        "Visitas",
        "Total Compras (COP)",
        "Total Boletas",
        "Números de Boleta Oficiales",
        "Autorización Habeas Data"
    ]
    ws.append([])
    ws.append(headers)
    ws.row_dimensions[4].height = 28

    header_font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=4, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = thin_border

    clients_dict = _get_consolidated_clients_dict()
    zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

    row_num = 5
    for idx, c in enumerate(clients_dict.values(), start=1):
        ws.append([
            idx,
            c["name"],
            c["phone"],
            c["city"],
            c["location"],
            c["advisor"],
            c["visits"],
            c["sales"],
            c["tickets"],
            c["codes"] or "Sin boletas",
            c["auth"]
        ])
        ws.row_dimensions[row_num].height = 22

        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=row_num, column=col_idx)
            cell.font = Font(name="Calibri", size=10)
            cell.border = thin_border
            if idx % 2 == 0:
                cell.fill = zebra_fill

            if col_idx in [1, 3, 7, 9]:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif col_idx in [8]:
                cell.number_format = '"$"#,##0'
                cell.alignment = Alignment(horizontal="right", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")

        row_num += 1

    ws.column_dimensions['A'].width = 6
    ws.column_dimensions['B'].width = 32
    ws.column_dimensions['C'].width = 18
    ws.column_dimensions['D'].width = 14
    ws.column_dimensions['E'].width = 28
    ws.column_dimensions['F'].width = 28
    ws.column_dimensions['G'].width = 10
    ws.column_dimensions['H'].width = 22
    ws.column_dimensions['I'].width = 14
    ws.column_dimensions['J'].width = 30
    ws.column_dimensions['K'].width = 24

    buf = BytesIO()
    wb.save(buf)
    filename = f"Clientes_Grupo_Innovar_{timezone.now().strftime('%Y%m%d_%H%M')}.xlsx"
    response = HttpResponse(buf.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required(login_url='admin_login')
def export_raffle_excel(request):
    """Exporta el registro oficial de boletas y facturas del sorteo en formato Microsoft Excel (.xlsx)."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    city_filter = request.GET.get("city", "")
    search_query = request.GET.get("q", "")

    qs = Evaluation.objects.filter(is_valid=True, tickets_count__gt=0).select_related('advisor', 'location')
    if city_filter:
        qs = qs.filter(location__city=city_filter)
    if search_query:
        qs = qs.filter(
            Q(client_name__icontains=search_query) |
            Q(client_phone__icontains=search_query) |
            Q(invoice_number__icontains=search_query) |
            Q(ticket_codes__icontains=search_query) |
            Q(advisor__full_name__icontains=search_query)
        )

    entries = list(qs.order_by('-created_at'))
    total_entries = len(entries)
    total_tickets_sum = sum(ev.tickets_count or 0 for ev in entries)
    total_sales_sum = sum(float(ev.invoice_amount or 0) for ev in entries)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Boletas Sorteo"
    ws.freeze_panes = "A5"

    # Encabezado corporativo
    ws.merge_cells("A1:K1")
    title_cell = ws["A1"]
    title_cell.value = "GRUPO INNOVAR - CONTROL OFICIAL DE BOLETAS Y SORTEOS"
    title_cell.font = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
    title_cell.fill = PatternFill(start_color="E11D48", end_color="E11D48", fill_type="solid")
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 36

    ws.merge_cells("A2:K2")
    sub_cell = ws["A2"]
    now_str = timezone.now().strftime("%d/%m/%Y %I:%M %p")
    sub_cell.value = (
        f"Generado el: {now_str} | Registros: {total_entries} | "
        f"Boletas en juego: {total_tickets_sum} | Total facturado: ${total_sales_sum:,.0f} COP"
    )
    sub_cell.font = Font(name="Calibri", size=9, italic=True, color="475569")
    sub_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 20

    headers = [
        "#",
        "Fecha",
        "Cliente",
        "Celular / WhatsApp",
        "Ciudad",
        "Sede",
        "Asesor",
        "N° Factura",
        "Valor Factura (COP)",
        "Boletas",
        "Códigos de Boleta",
    ]
    ws.append([])
    ws.append(headers)
    ws.row_dimensions[4].height = 28

    header_font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=4, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = thin_border

    zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    min_widths = [6, 18, 28, 18, 14, 28, 26, 16, 20, 11, 34]
    col_max_lens = list(min_widths)

    row_num = 5
    for idx, ev in enumerate(entries, start=1):
        date_str = timezone.localtime(ev.created_at).strftime("%d/%m/%Y %H:%M") if ev.created_at else ""
        row_values = [
            idx,
            date_str,
            (ev.client_name or "Cliente Anónimo").strip(),
            (ev.client_phone or "").strip() or "No registrado",
            ev.location.city if ev.location else "General",
            ev.location.name if ev.location else "Sede General",
            ev.advisor.full_name if ev.advisor else "Sin asesor",
            ev.invoice_number or "N/A",
            float(ev.invoice_amount or 0),
            int(ev.tickets_count or 0),
            ev.ticket_codes or "",
        ]
        ws.append(row_values)
        ws.row_dimensions[row_num].height = 22

        for col_idx, val in enumerate(row_values, start=1):
            col_max_lens[col_idx - 1] = max(col_max_lens[col_idx - 1], len(str(val)) + 3)
            cell = ws.cell(row=row_num, column=col_idx)
            cell.font = Font(name="Calibri", size=10)
            cell.border = thin_border
            if idx % 2 == 0:
                cell.fill = zebra_fill

            if col_idx in [1, 2, 4, 8, 10]:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif col_idx == 9:
                cell.number_format = '"$"#,##0'
                cell.alignment = Alignment(horizontal="right", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")

        row_num += 1

    # Fila resumen de totales
    ws.append([
        "",
        "TOTALES",
        f"{total_entries} registros",
        "",
        "",
        "",
        "",
        "",
        total_sales_sum,
        total_tickets_sum,
        "",
    ])
    ws.row_dimensions[row_num].height = 26
    summary_fill = PatternFill(start_color="FEF2F2", end_color="FEF2F2", fill_type="solid")
    summary_font = Font(name="Calibri", size=10, bold=True, color="991B1B")
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=row_num, column=col_idx)
        cell.font = summary_font
        cell.fill = summary_fill
        cell.border = thin_border
        if col_idx == 9:
            cell.number_format = '"$"#,##0'
            cell.alignment = Alignment(horizontal="right", vertical="center")
        elif col_idx in [2, 10]:
            cell.alignment = Alignment(horizontal="center", vertical="center")
        else:
            cell.alignment = Alignment(horizontal="left", vertical="center")

    for col_idx, width in enumerate(col_max_lens, start=1):
        ws.column_dimensions[get_column_letter(col_idx)].width = min(width, 48)

    buf = BytesIO()
    wb.save(buf)
    response = HttpResponse(buf.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response['Content-Disposition'] = 'attachment; filename="Boletas_Sorteo_Grupo_Innovar.xlsx"'
    return response


@login_required(login_url='admin_login')
def export_clients_word(request):
    """Exporta el listado oficial y organizado de clientes y números en formato Microsoft Word (.docx)."""
    import docx
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.oxml import parse_xml
    from docx.oxml.ns import nsdecls

    doc = docx.Document()

    for section in doc.sections:
        section.top_margin = Inches(0.7)
        section.bottom_margin = Inches(0.7)
        section.left_margin = Inches(0.7)
        section.right_margin = Inches(0.7)

    # Título principal
    title_p = doc.add_paragraph()
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_title = title_p.add_run("GRUPO INNOVAR")
    run_title.font.name = "Arial"
    run_title.font.size = Pt(18)
    run_title.font.bold = True
    run_title.font.color.rgb = RGBColor(225, 29, 72)

    sub_p = doc.add_paragraph()
    sub_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_sub = sub_p.add_run("DIRECTORIO OFICIAL DE CLIENTES REGISTRADOS\nControl de Contactos y Registro de Sorteos")
    run_sub.font.name = "Arial"
    run_sub.font.size = Pt(11)
    run_sub.font.bold = True
    run_sub.font.color.rgb = RGBColor(30, 41, 59)

    now_str = timezone.now().strftime("%d/%m/%Y %I:%M %p")
    clients_dict = _get_consolidated_clients_dict()
    total_count = len(clients_dict)

    meta_p = doc.add_paragraph()
    meta_p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    meta_run = meta_p.add_run(
        f"• Fecha de emisión: {now_str}\n"
        f"• Total clientes registrados: {total_count}\n"
        f"• Marco Legal: Ley Estatutaria 1581 de 2012 (Protección de Datos Personales / Habeas Data)\n"
        f"• Sede Principal: Cerámicas San Lorenzo Ibagué (Jardín)"
    )
    meta_run.font.name = "Arial"
    meta_run.font.size = Pt(9)
    meta_run.font.color.rgb = RGBColor(100, 116, 139)

    table = doc.add_table(rows=1, cols=6)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False

    col_widths = [Inches(0.4), Inches(2.3), Inches(1.3), Inches(1.4), Inches(1.1), Inches(0.8)]
    headers = ["#", "NOMBRE CLIENTE", "CELULAR", "ASESOR", "COMPRAS", "BOLETAS"]
    hdr_cells = table.rows[0].cells
    for i, h_text in enumerate(headers):
        hdr_cells[i].text = h_text
        hdr_cells[i].width = col_widths[i]
        shading = parse_xml(r'<w:shd {} w:fill="E11D48"/>'.format(nsdecls('w')))
        hdr_cells[i]._tc.get_or_add_tcPr().append(shading)
        p = hdr_cells[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in p.runs:
            run.font.name = "Arial"
            run.font.size = Pt(8.5)
            run.font.bold = True
            run.font.color.rgb = RGBColor(255, 255, 255)

    for idx, c in enumerate(clients_dict.values(), start=1):
        row_cells = table.add_row().cells
        row_data = [
            str(idx),
            c["name"],
            c["phone"],
            c["advisor"],
            f"${c['sales']:,.0f}".replace(",", "."),
            str(c["tickets"])
        ]
        shd_color = "F8FAFC" if idx % 2 == 0 else "FFFFFF"
        for i, val in enumerate(row_data):
            row_cells[i].text = val
            row_cells[i].width = col_widths[i]
            shd = parse_xml(r'<w:shd {} w:fill="{}"/>'.format(nsdecls('w'), shd_color))
            row_cells[i]._tc.get_or_add_tcPr().append(shd)
            p = row_cells[i].paragraphs[0]
            if i in [0, 2, 5]:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            elif i == 4:
                p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            else:
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            for run in p.runs:
                run.font.name = "Arial"
                run.font.size = Pt(8.5)
                run.font.color.rgb = RGBColor(17, 24, 39)
                if i in [1, 2]:
                    run.font.bold = True

    doc.add_paragraph()
    footer_p = doc.add_paragraph()
    footer_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer_run = footer_p.add_run("Documento generado automáticamente por el Sistema INNOVAR SERVICE - Grupo Innovar Colombia.\nConfidencial - Uso exclusivo comercial y administrativo.")
    footer_run.font.name = "Arial"
    footer_run.font.size = Pt(8)
    footer_run.font.italic = True
    footer_run.font.color.rgb = RGBColor(148, 163, 184)

    buf = BytesIO()
    doc.save(buf)
    filename = f"Directorio_Clientes_Grupo_Innovar_{timezone.now().strftime('%Y%m%d_%H%M')}.docx"
    response = HttpResponse(buf.getvalue(), content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required(login_url='admin_login')
def export_clients_csv(request):
    """Exportar base de datos de clientes deduplicada en CSV compatible con Excel UTF-8 BOM."""
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = f'attachment; filename="Clientes_Grupo_Innovar_{timezone.now().strftime("%Y%m%d")}.csv"'

    writer = csv.writer(response)
    writer.writerow([
        "Nombre Cliente",
        "Celular / WhatsApp (Único)",
        "Ciudad Principal",
        "Sede Frecuente",
        "Asesor Comercial",
        "Visitas Registradas",
        "Total Compras Acumuladas (COP)",
        "Total Boletas Sorteo",
        "Códigos Boletas",
        "Última Interacción",
        "Autorización Habeas Data (Ley 1581)"
    ])

    clients_dict = _get_consolidated_clients_dict()
    for c in clients_dict.values():
        writer.writerow([
            c["name"],
            c["phone"],
            c["city"],
            c["location"],
            c["advisor"],
            c["visits"],
            c["sales"],
            c["tickets"],
            c["codes"] or "Sin boletas",
            c["last_seen"],
            c["auth"]
        ])

    return response


def download_qr_png(request, qr_id):
    """Descarga directa del código QR en alta resolución (PNG) garantizada en Vercel/Cloud."""
    qr_obj = get_object_or_404(QRCode, pk=qr_id)
    target_url = request.build_absolute_uri(qr_obj.evaluation_path)

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=12,
        border=3,
    )
    qr.add_data(target_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#111827", back_color="#FFFFFF")

    buf = BytesIO()
    img.save(buf, format="PNG")
    response = HttpResponse(buf.getvalue(), content_type="image/png")
    response["Content-Disposition"] = f'attachment; filename="{qr_obj.code}.png"'
    return response


def serve_qr_png(request, qr_id):
    """Sirve dinámicamente la imagen del código QR sin depender de almacenamiento local."""
    qr_obj = get_object_or_404(QRCode, pk=qr_id)
    target_url = request.build_absolute_uri(qr_obj.evaluation_path)

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(target_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#111827", back_color="#FFFFFF")

    buf = BytesIO()
    img.save(buf, format="PNG")
    response = HttpResponse(buf.getvalue(), content_type="image/png")
    response["Cache-Control"] = "public, max-age=86400"
    return response


def detect_receipt_ai(request):
    """
    API con Visión / IA para escanear facturas de compra y detectar el valor TOTAL exacto.
    Evita falsos positivos leyendo líneas finales, reconociendo patrones DIAN / POS colombianos
    y extrayendo el número de factura.
    """
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "Método no permitido"}, status=405)

    image_data = None

    if "invoice_image" in request.FILES:
        try:
            image_data = request.FILES["invoice_image"].read()
        except Exception:
            pass

    if not image_data:
        raw_b64 = request.POST.get("image_base64", "")
        if not raw_b64 and request.body:
            try:
                body_json = json.loads(request.body.decode("utf-8"))
                raw_b64 = body_json.get("image_base64", "")
            except Exception:
                pass

        if raw_b64:
            if "," in raw_b64:
                raw_b64 = raw_b64.split(",", 1)[1]
            try:
                image_data = base64.b64decode(raw_b64)
            except Exception:
                image_data = None

    if not image_data:
        return JsonResponse({"success": False, "message": "No se recibió ninguna imagen de factura válida."}, status=400)

    try:
        pil_img = Image.open(BytesIO(image_data))
        if pil_img.mode in ("RGBA", "P"):
            pil_img = pil_img.convert("RGB")

        max_dim = 1600
        if pil_img.width > max_dim or pil_img.height > max_dim:
            pil_img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

        gemini_key = os.getenv("GEMINI_API_KEY", "")
        if gemini_key:
            import urllib.request
            b64_str = base64.b64encode(image_data).decode("utf-8")
            gemini_payload = {
                "contents": [{
                    "parts": [
                        {"text": "Eres un auditor contable de Grupo Innovar en Colombia. Analiza esta foto de factura de compra física y extrae: 1) 'total': valor numérico entero en COP pagado como TOTAL A PAGAR (sin decimales ni comas, ej: 1540000). 2) 'factura_numero': consecutivo o número de factura impreso (ej: 'FE-12934' o 'POS-5541'). Responde estrictamente con un JSON válido con estas dos claves. Si no hay factura o no es legible, responde {\"total\": null, \"factura_numero\": null}."},
                        {"inline_data": {"mime_type": "image/jpeg", "data": b64_str}}
                    ]
                }]
            }
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
            req_g = urllib.request.Request(url, data=json.dumps(gemini_payload).encode("utf-8"), headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req_g, timeout=8) as resp_g:
                    res_data = json.loads(resp_g.read().decode("utf-8"))
                    text_out = res_data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    if "```" in text_out:
                        text_out = re.sub(r"```(?:json)?", "", text_out).strip()
                    parsed = json.loads(text_out)
                    total_val = int(parsed.get("total") or 0)
                    fac_num = str(parsed.get("factura_numero") or "").strip()
                    if total_val >= 1000000:
                        tickets = total_val // 1000000
                        return JsonResponse({
                            "success": True,
                            "total": total_val,
                            "factura_numero": fac_num,
                            "tickets": tickets,
                            "engine": "gemini_vision",
                            "message": f"Factura analizada con IA. Total: ${total_val:,.0f} COP ({tickets} boleta(s))."
                        })
            except Exception as e:
                print("Gemini API fallback to local parser:", e)

        return JsonResponse({
            "success": True,
            "engine": "client_hybrid",
            "message": "Imagen optimizada para lectura de alta precisión."
        })
    except Exception as e:
        return JsonResponse({"success": False, "message": f"Error procesando la imagen: {str(e)}"}, status=500)


