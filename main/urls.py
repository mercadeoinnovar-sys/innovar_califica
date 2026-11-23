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

    # Módulo de Sorteos & Boletas de Facturas (Independiente)
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
    path('admin-dashboard/sedes/', views.admin_locations, name='admin_locations'),
    path('admin-dashboard/evaluaciones/', views.admin_evaluations, name='admin_evaluations'),
    path('admin-dashboard/clientes-pautas/', views.admin_clients, name='admin_clients'),
    path('admin-dashboard/clientes-pautas/export-csv/', views.export_clients_csv, name='export_clients_csv'),
    path('admin-dashboard/sorteos/', views.admin_raffle, name='admin_raffle'),
    path('admin-dashboard/reportes/', views.admin_reports, name='admin_reports'),
    path('admin-dashboard/configuracion/', views.admin_settings, name='admin_settings'),
    path('qr-management/', views.qr_management, name='qr_management'),

    # Hablador de Mostrador Imprimible en acrílico
    path('imprimir-hablador/asesor/<int:advisor_id>/', views.print_counter_display, name='print_advisor_display'),
    path('imprimir-hablador/sede/<int:location_id>/', views.print_counter_display, name='print_location_display'),

    # Exportación
    path('export-csv/', views.export_evaluations_csv, name='export_evaluations_csv'),

    # SEO & Google Indexing
    path('robots.txt', views.robots_txt, name='robots_txt'),
    path('sitemap.xml', views.sitemap_xml, name='sitemap_xml'),
]
