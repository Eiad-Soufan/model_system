from django.contrib import admin
from .models import Section, FormModel, UserSectionPermission, Notification, UserNotification
from django.contrib.auth import get_user_model
from .models import Complaint
from .models import EmployeePointLog, HonorBoardSetting, CustomUser
from django.contrib.auth.admin import UserAdmin


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    # نحافظ على حقول الـUserAdmin الافتراضية ونضيف حقولنا
    fieldsets = UserAdmin.fieldsets + (
        ('Extra Info', {'fields': ('role', 'points', 'avatar')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Extra Info', {'fields': ('role',)}),
    )
    list_display = UserAdmin.list_display + ('role', 'points',)
    list_filter = UserAdmin.list_filter + ('role',)
    search_fields = UserAdmin.search_fields + ('first_name', 'last_name',)



CustomUser = get_user_model()

@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ('id', 'name_ar', 'name_en')

@admin.register(FormModel)
class FormModelAdmin(admin.ModelAdmin):
    list_display = ('serial_number', 'name_ar', 'section', 'category')
    list_filter = ('section', 'category')
    search_fields = ('name_ar', 'name_en', 'serial_number')

@admin.register(UserSectionPermission)
class UserSectionPermissionAdmin(admin.ModelAdmin):
    list_display = ('user', 'section')

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'message', 'importance', 'created_at')

@admin.register(UserNotification)
class UserNotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'notification')


    
@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = ('title','message','response', 'sender', 'recipient_type', 'is_responded', 'created_at')

# === [Tasks Feature] Admin ===
from django.contrib import admin as _admin
from .models import Task, TaskPhase, TaskRecipient, TaskComment

class TaskPhaseInline(_admin.TabularInline):
    model = TaskPhase
    extra = 0

class TaskRecipientInline(_admin.TabularInline):
    model = TaskRecipient
    extra = 0

@_admin.register(Task)
class TaskAdmin(_admin.ModelAdmin):
    list_display = ("id", "title", "creator_role", "status", "created_by", "created_at")
    list_filter = ("creator_role", "status", "created_at")
    search_fields = ("title", "description", "created_by__username")
    inlines = [TaskPhaseInline, TaskRecipientInline]

@_admin.register(TaskComment)
class TaskCommentAdmin(_admin.ModelAdmin):
    list_display = ("id", "task", "author", "created_at")
    search_fields = ("text",)



from django.contrib import admin
from .models import (
    Survey, SurveyQuestion, SurveyOption,
    SurveySubmission, SurveyAnswer,
    SurveyStatus, CreatorRole,
)

# ========= Inlines =========

class SurveyOptionInline(admin.TabularInline):
    model = SurveyOption
    extra = 1
    fields = ("text", "order")
    ordering = ("order", "id")


@admin.register(SurveyQuestion)
class SurveyQuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "survey", "order", "text_short", "required")
    list_filter = ("required", "survey__status", "survey__creator_role")
    search_fields = ("text", "survey__title")
    ordering = ("survey", "order", "id")
    inlines = (SurveyOptionInline,)

    def text_short(self, obj):
        return (obj.text or "")[:60]
    text_short.short_description = "Question"


class SurveyQuestionInline(admin.TabularInline):
    model = SurveyQuestion
    extra = 1
    fields = ("text", "required", "order")
    ordering = ("order", "id")


# ========= Survey Admin =========

@admin.register(Survey)
class SurveyAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "creator", "creator_role", "status", "published_at", "created_at")
    list_filter = ("status", "creator_role", "created_at")
    search_fields = ("title", "description", "creator__username", "creator__first_name", "creator__last_name")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    inlines = (SurveyQuestionInline,)
    readonly_fields = ("created_at", "updated_at", "published_at")

    actions = ("make_published", "make_draft", "make_archived")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # تحسين الأداء
        return qs.select_related("creator").prefetch_related("questions")

    # Actions
    def make_published(self, request, queryset):
        updated = 0
        for s in queryset:
            if s.status != SurveyStatus.PUBLISHED:
                s.status = SurveyStatus.PUBLISHED
                s.published_at = _timezone.now()
                s.save(update_fields=["status", "published_at", "updated_at"])
                updated += 1
        self.message_user(request, f"تم نشر {updated} استبيان/ات.")
    make_published.short_description = "نشر (Publish)"

    def make_draft(self, request, queryset):
        updated = queryset.update(status=SurveyStatus.DRAFT)
        self.message_user(request, f"تم تحويل {updated} استبيان/ات إلى مسودة.")
    make_draft.short_description = "تحويل إلى مسودة (Draft)"

    def make_archived(self, request, queryset):
        updated = queryset.update(status=SurveyStatus.ARCHIVED)
        self.message_user(request, f"تم أرشفة {updated} استبيان/ات.")
    make_archived.short_description = "أرشفة (Archive)"


# ========= Submissions & Answers (عرض إداري) =========

class SurveyAnswerInline(admin.TabularInline):
    model = SurveyAnswer
    extra = 0
    fields = ("question", "selected_option")
    readonly_fields = ("question", "selected_option")
    can_delete = False
    show_change_link = False


@admin.register(SurveySubmission)
class SurveySubmissionAdmin(admin.ModelAdmin):
    list_display = ("id", "survey", "user", "created_at")
    list_filter = ("survey__status", "survey__creator_role", "created_at")
    search_fields = ("survey__title", "user__username", "user__first_name", "user__last_name")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    inlines = (SurveyAnswerInline,)
    readonly_fields = ("survey", "user", "created_at")


@admin.register(SurveyAnswer)
class SurveyAnswerAdmin(admin.ModelAdmin):
    list_display = ("id", "submission", "question", "selected_option")
    list_filter = ("question__survey__status", "question__survey__creator_role")
    search_fields = ("question__text", "selected_option__text", "submission__user__username")
    ordering = ("-id",)
    readonly_fields = ("submission", "question", "selected_option")

admin.site.register(EmployeePointLog)
admin.site.register(HonorBoardSetting)