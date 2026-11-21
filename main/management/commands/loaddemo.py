import random
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from main.models import Location, Advisor, Evaluation, QRCode, Badge


class Command(BaseCommand):
    help = 'Sincroniza las 9 sedes oficiales de Grupo Innovar'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('Inicializando sincronización de sedes oficiales de Grupo Innovar...'))

        # 1. Crear / Asegurar las 9 Sedes Oficiales de Grupo Innovar
        sedes_oficiales = [
            ("Cerámicas San Lorenzo Jardín", "Ibagué"),
            ("Supermercado Cerámico", "Ibagué"),
            ("Ferretería Innovar", "Ibagué"),
            ("Ambientes Innovar", "Ibagué"),
            ("Líder Cerámico", "Ibagué"),
            ("Supertiendas PVC y Disdrywall", "Ibagué"),
            ("Cerámicas San Lorenzo Centro", "Ibagué"),
            ("Cerámicas Innovar Neiva", "Neiva"),
            ("Cerámicas Innovar Girardot", "Girardot"),
        ]

        locations_map = {}
        for name, city in sedes_oficiales:
            loc, _ = Location.objects.get_or_create(name=name, defaults={"city": city})
            loc.city = city
            loc.save()
            locations_map[name] = loc

        self.stdout.write(self.style.SUCCESS(f'✓ Creadas/aseguradas las 9 sedes oficiales'))

        # 2. Asesores Comerciales asignados a las sedes oficiales
        asesores_data = [
            ("Carlos Alberto Mendoza", "ASESOR-001", "Asesor Senior de Ventas", "Cerámicas San Lorenzo Jardín"),
            ("María Fernanda Gómez", "ASESOR-002", "Especialista en Acabados", "Supermercado Cerámico"),
            ("Juan Sebastián Torres", "ASESOR-003", "Asesor de Mostrador", "Ferretería Innovar"),
            ("Diana Marcela Rodríguez", "ASESOR-004", "Líder de Experiencia al Cliente", "Ambientes Innovar"),
            ("Andrés Felipe Morales", "ASESOR-005", "Asesor Comercial de Proyectos", "Líder Cerámico"),
            ("Laura Camila Ortiz", "ASESOR-006", "Consultora de Diseño y Espacios", "Supertiendas PVC y Disdrywall"),
            ("Jorge Eliécer Castro", "ASESOR-007", "Asesor Comercial Senior", "Cerámicas San Lorenzo Centro"),
            ("Valentina Duque Pérez", "ASESOR-008", "Asesora de Atención y Ventas", "Cerámicas Innovar Neiva"),
            ("David Ricardo Herrera", "ASESOR-009", "Especialista en Materiales", "Cerámicas Innovar Girardot"),
            ("Ana María Cárdenas", "ASESOR-010", "Asesora de Atención y Ventas", "Supermercado Cerámico"),
            ("Diego Fernando Vargas", "ASESOR-011", "Asesor Técnico Comercial", "Cerámicas San Lorenzo Jardín"),
            ("Paula Andrea Beltrán", "ASESOR-012", "Asesora de Proyectos Residenciales", "Ambientes Innovar"),
            ("Mateo Alejandro Rojas", "ASESOR-013", "Asesor Comercial", "Ferretería Innovar"),
            ("Daniela Sofía Restrepo", "ASESOR-014", "Asesora Senior", "Cerámicas Innovar Neiva"),
            ("Santiago Muñoz Ospina", "ASESOR-015", "Consultor Comercial", "Cerámicas Innovar Girardot"),
        ]

        advisors = []
        for full_name, identifier, position, sede_name in asesores_data:
            target_loc = locations_map[sede_name]
            advisor, _ = Advisor.objects.update_or_create(
                identifier=identifier,
                defaults={
                    "full_name": full_name,
                    "location": target_loc,
                    "position": position,
                    "is_active": True,
                }
            )
            advisors.append(advisor)

        self.stdout.write(self.style.SUCCESS(f'✓ Asignados los 15 asesores a sus sedes oficiales'))

        # 3. Reasignar todas las evaluaciones existentes a las sedes de sus asesores
        for ev in Evaluation.objects.all():
            if ev.advisor:
                ev.location = ev.advisor.location
                ev.client_city = ev.advisor.location.city
                ev.save()

        self.stdout.write(self.style.SUCCESS('✓ Evaluaciones reasignadas a las sedes oficiales'))

        # 4. Eliminar sedes antiguas que ya no están en uso y no tienen referencias
        nombres_oficiales = [s[0] for s in sedes_oficiales]
        sedes_antiguas = Location.objects.exclude(name__in=nombres_oficiales)
        # Quitar los QR de sedes antiguas
        QRCode.objects.filter(location__in=sedes_antiguas).delete()
        sedes_antiguas.delete()
        self.stdout.write(self.style.SUCCESS('✓ Sedes antiguas desvinculadas y limpiadas'))

        # 5. Generar y actualizar Códigos QR para las 9 sedes oficiales
        for loc in locations_map.values():
            code_loc = f"QR-SEDE-{loc.id:03d}"
            qr_loc, _ = QRCode.objects.get_or_create(
                code=code_loc,
                defaults={"location": loc, "advisor": None}
            )
            qr_loc.location = loc
            qr_loc.advisor = None
            qr_loc.generate_qr_image()
            qr_loc.save()

        # Generar y actualizar Códigos QR para los 15 asesores
        for adv in advisors:
            code_adv = f"QR-{adv.identifier}"
            qr_adv, _ = QRCode.objects.get_or_create(
                code=code_adv,
                defaults={"location": adv.location, "advisor": adv}
            )
            qr_adv.location = adv.location
            qr_adv.advisor = adv
            qr_adv.generate_qr_image()
            qr_adv.save()

        self.stdout.write(self.style.SUCCESS('✓ Códigos QR actualizados y sincronizados'))
        self.stdout.write(self.style.SUCCESS('🎉 ¡Sedes oficiales de Grupo Innovar actualizadas en Supabase con éxito!'))
