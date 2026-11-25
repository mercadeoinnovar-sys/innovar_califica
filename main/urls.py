from django.urls import path
from . import views

urlpatterns = [
    # Módulo de Inicio
    path('', views.home, name='home'),

    # Módulo de Clientes (Calificación QR ultra rápida)
    path('evaluar/', views.evaluate, name='evaluate_es'),
    path('evaluar/<str:advisor_code>/', views.evaluate_advisor_direct, name='evaluate_advisor_direct'),
    path('evaluar/sede/<int:location_id>/', views.evaluate_location_direct, name='evaluate_location_direct'),
    path('evaluate/', views.evaluate, name='evaluate'),

    # Módulo de Sorteos & Boletas de Facturas (Post-evaluación)
    path('boletas/registrar/<int:evaluation_id>/', views.add_invoice_to_evaluation, name='add_invoice_to_evaluation'),
    path('boletas/', views.raffle_register, name='raffle_register'),
    path('sorteo/', views.raffle_register, name='raffle_alias'),

    # Módulo de Ranking & Asesor
    path('ranking/', views.ranking, name='ranking'),
    path('advisor/<int:advisor_id>/', views.advisor_detail, name='advisor_detail'),

    # Suite Administrativa (Sidebar & Auth)
    path('admin-login/', views.admin_login, name='admin_login'),
    path('admin-logout/', views.admin_logout, name='admin_logout'),
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('admin-dashboard/asesores/', views.admin_advisors, name='admin_advisors'),
    path('admin-dashboard/asesores/editar/<int:advisor_id>/', views.admin_advisor_edit, name='admin_advisor_edit'),
    path('admin-dashboard/sedes/', views.admin_locations, name='admin_locations'),
    path('admin-dashboard/evaluaciones/', views.admin_evaluations, name='admin_evaluations'),
    path('admin-dashboard/clientes/', views.admin_clients, name='admin_clients'),
    path('admin-dashboard/clientes/export-excel/', views.export_clients_excel, name='export_clients_excel'),
    path('admin-dashboard/clientes/export-word/', views.export_clients_word, name='export_clients_word'),
    path('admin-dashboard/clientes/export-csv/', views.export_clients_csv, name='export_clients_csv'),
    path('admin-dashboard/clientes-pautas/', views.admin_clients, name='admin_clients_legacy'),
    path('admin-dashboard/clientes-pautas/export-csv/', views.export_clients_csv, name='export_clients_csv_legacy'),
    path('admin-dashboard/sorteos/', views.admin_raffle, name='admin_raffle'),
    path('admin-dashboard/sorteos/export-excel/', views.export_raffle_excel, name='export_raffle_excel'),
    path('admin-dashboard/reportes/', views.admin_reports, name='admin_reports'),
    path('admin-dashboard/configuracion/', views.admin_settings, name='admin_settings'),
    path('qr-management/', views.qr_management, name='qr_management'),

    # Descarga directa y visualización de QR
    path('qr/descargar/<int:qr_id>/', views.download_qr_png, name='download_qr_png'),
    path('qr/ver/<int:qr_id>/', views.serve_qr_png, name='serve_qr_png'),

    # API con Visión / IA para escanear facturas y bloqueo antiduplicados
    path('api/detectar-factura/', views.detect_receipt_ai, name='detect_receipt_ai'),
    path('api/verificar-factura/', views.check_invoice_duplicate, name='check_invoice_duplicate'),

    # Hablador de Mostrador Imprimible en acrílico
    path('imprimir-hablador/asesor/<int:advisor_id>/', views.print_counter_display, name='print_advisor_display'),
    path('imprimir-hablador/sede/<int:location_id>/', views.print_counter_display, name='print_location_display'),

    # Exportación
    path('export-csv/', views.export_evaluations_csv, name='export_evaluations_csv'),

    # SEO & Google Indexing
    path('robots.txt', views.robots_txt, name='robots_txt'),
    path('sitemap.xml', views.sitemap_xml, name='sitemap_xml'),
]
