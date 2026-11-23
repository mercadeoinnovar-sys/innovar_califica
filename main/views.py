# main/views.py
"""Views for INNOVAR SERVICE - Grupo Innovar."""
import csv
from datetime import datetime
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


def raffle_register(request):
    """Módulo independiente para registrar facturas de compra y participar en sorteos de boletas."""
    if not request.session.session_key:
        request.session.save()
    session_key = request.session.session_key
    client_ip = get_client_ip(request)

    if request.method == "POST":
        form = RaffleRegistrationForm(request.POST)
        if form.is_valid():
            phone = form.cleaned_data.get("client_phone")
            new_amount = form.cleaned_data["invoice_amount"]
            now = timezone.now()

            # Control anti-redundancia: 1 solo registro por cliente por mes, acumulando sus compras y boletas
            existing_monthly = Evaluation.objects.filter(
                client_phone=phone,
                created_at__year=now.year,
                created_at__month=now.month,
                is_valid=True
            ).first()

            if existing_monthly:
                entry = existing_monthly
                entry.client_name = form.cleaned_data["client_name"]
                entry.location = form.cleaned_data["location"]
                if form.cleaned_data.get("advisor"):
                    entry.advisor = form.cleaned_data["advisor"]
                entry.client_city = entry.location.city if entry.location else ""
                prev_amount = entry.invoice_amount or 0
                entry.invoice_amount = prev_amount + new_amount
                if form.cleaned_data.get("invoice_number"):
                    entry.invoice_number = form.cleaned_data["invoice_number"]
                entry.ip_address = client_ip
                entry.session_key = session_key
                entry.created_at = now
            else:
                entry = form.save(commit=False)
                entry.client_city = entry.location.city if entry.location else ""
                entry.ip_address = client_ip
                entry.session_key = session_key
                entry.attention_quality = "Excelente"
                entry.info_clarity = "Sí, completamente"
                entry.product_knowledge = "Sí"
                entry.disposition = "Siempre"
                entry.recommendation = "Definitivamente sí"
                entry.overall_star = 5
                entry.is_valid = True
                entry.invoice_image = None

            # Asignación acumulada de boletas: 1 boleta por cada $1'000.000 COP
            if entry.invoice_amount and entry.invoice_amount >= 1000000:
                entry.tickets_count = int(entry.invoice_amount // 1000000)
            else:
                entry.tickets_count = 0

            entry.save()

            if entry.tickets_count > 0:
                codes = [f"INV-{entry.id:04d}-{i+1}" for i in range(entry.tickets_count)]
                entry.ticket_codes = ", ".join(codes)
                entry.save(update_fields=["ticket_codes"])

            return render(request, "main/thank_you.html", {
                "evaluation": entry,
                "advisor": entry.advisor,
                "is_raffle_entry": True
            })
    else:
        form = RaffleRegistrationForm()

    return render(request, "main/raffle_register.html", {
        "form": form
    })


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
            advisor = form.save()
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

    return render(request, "main/admin_raffle.html", {
        "raffle_entries": raffle_entries,
        "total_tickets": total_tickets,
        "total_participants": total_participants,
        "total_sales_amount": total_sales_amount,
        "cities": cities,
        "selected_city": city_filter,
        "search_query": search_query,
        "active_tab": "raffle",
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


@login_required(login_url='admin_login')
def admin_clients(request):
    """Módulo de Registro de Clientes para Pautas Publicitarias y Sorteos de Grupo Innovar (Deduplicado por Celular)."""
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

    # Consolidación y Deduplicación estricta por número celular: 1 sola fila por cliente único
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

    # Filtro por estado de sorteo sobre clientes únicos
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
def export_clients_csv(request):
    """Exportar base de datos de clientes deduplicada para pautas publicitarias (Meta Ads, Google Ads, WhatsApp)."""
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = 'attachment; filename="audiencia_pautas_grupo_innovar_unicos.csv"'

    writer = csv.writer(response)
    writer.writerow([
        "Nombre Cliente",
        "Celular / WhatsApp (Único)",
        "Ciudad Principal",
        "Sede Frecuente",
        "Visitas Registradas",
        "Total Compras Acumuladas (COP)",
        "Total Boletas Sorteo",
        "Códigos Boletas",
        "Última Interacción",
        "Autorización Habeas Data (Ley 1581)"
    ])

    qs = Evaluation.objects.filter(is_valid=True).exclude(client_phone="").select_related('advisor', 'location').order_by('-created_at')
    clients_dict = {}
    for ev in qs:
        phone = ev.client_phone.strip()
        if not phone:
            continue
        if phone not in clients_dict:
            clients_dict[phone] = {
                "name": ev.client_name or "Cliente Registrado",
                "phone": phone,
                "city": ev.location.city if ev.location else "Ibagué",
                "location": ev.location.name if ev.location else "General",
                "visits": 1,
                "sales": float(ev.invoice_amount or 0),
                "tickets": ev.tickets_count,
                "codes": ev.ticket_codes,
                "last_seen": ev.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "auth": "AUTORIZADO (Ley 1581 de 2012)" if ev.data_authorization else "NO"
            }
        else:
            c = clients_dict[phone]
            c["visits"] += 1
            c["sales"] += float(ev.invoice_amount or 0)
            c["tickets"] += ev.tickets_count
            if ev.ticket_codes:
                c["codes"] = (c["codes"] + ", " + ev.ticket_codes) if c["codes"] else ev.ticket_codes

    for c in clients_dict.values():
        writer.writerow([
            c["name"],
            c["phone"],
            c["city"],
            c["location"],
            c["visits"],
            c["sales"],
            c["tickets"],
            c["codes"] or "Sin boletas",
            c["last_seen"],
            c["auth"]
        ])

    return response

