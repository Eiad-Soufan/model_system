from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from core.models import Section, UserSectionPermission

User = get_user_model()


class Command(BaseCommand):
    help = "Grant all employees (role=employee) permissions on all sections."

    def handle(self, *args, **options):
        self.stdout.write("📁 Collecting sections and employees...")

        sections = list(Section.objects.all())
        if not sections:
            self.stdout.write(self.style.ERROR("❌ No sections found. Aborting."))
            return

        employees = User.objects.filter(role__iexact="employee")
        if not employees.exists():
            self.stdout.write(self.style.ERROR("❌ No employees with role='employee' found. Aborting."))
            return

        self.stdout.write(self.style.SUCCESS(
            f"✅ Found {len(sections)} sections and {employees.count()} employees."
        ))

        created = 0
        skipped = 0

        # 🔁 مرّ على كل موظف وكل قسم
        for user in employees:
            for section in sections:
                # استخدم get_or_create حتى لا تتكرر السماحية
                perm, was_created = UserSectionPermission.objects.get_or_create(
                    user=user,
                    section=section,
                )
                if was_created:
                    created += 1
                else:
                    skipped += 1

        self.stdout.write(self.style.SUCCESS(
            f"✔️ Done. Permissions created: {created}, already existed: {skipped}."
        ))
