# core/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    # ViewSets
    TaskViewSet,
    SectionViewSet,
    FormModelViewSet,
    NotificationViewSet,
    UserNotificationViewSet,
    ComplaintViewSet,
    SurveyViewSet,  # ← جديد

    # APIViews / functions
    MyTokenObtainPairView,
    UserListAPIView,
    current_user_info,
    preview_form,
    public_form_preview,

    # Complaints helpers (function-based views)
    mark_complaint_as_seen,
    has_unread_complaints,
    mark_all_complaints_seen,
    EmployeeSearchView,
    AdjustPointsView,
    HonorBoardView,
    HonorBoardToggleView,
    AvatarUploadView,
    MeView,
)

router = DefaultRouter()
router.register(r"tasks", TaskViewSet, basename="task")
router.register(r"sections", SectionViewSet, basename="section")
router.register(r"forms", FormModelViewSet, basename="formmodel")
router.register(r"notifications", NotificationViewSet, basename="notification")
router.register(r"user-notifications", UserNotificationViewSet, basename="user-notifications")
router.register(r"complaints", ComplaintViewSet, basename="complaint")
router.register(r"surveys", SurveyViewSet, basename="survey")  # ← Surveys

urlpatterns = [
    # Router endpoints (ViewSets)
    path("", include(router.urls)),

    # Auth
    path("token/", MyTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),

    # Users
    path("users/", UserListAPIView.as_view(), name="user-list"),
    # alias إضافي للـ fallback في AdminNotify: /api/employees/?page=1&page_size=100
    path("employees/", UserListAPIView.as_view(), name="employees-list"),
    path("current-user/", current_user_info, name="current-user"),

    # Forms (preview)
    path("preview-form/<int:form_id>/", preview_form, name="preview-form"),
    path("public-form/<int:pk>/", public_form_preview, name="public-form-preview"),

    # Complaints helpers (تتوافق مع ما هو مستخدم في الفرونت)
    # ملاحظة: /api/complaints/<pk>/mark_seen/ متوفر أيضًا من ComplaintViewSet@mark_seen عبر router،
    # لكن نبقي هذا alias متوافقًا مع أي استخدام قديم.
    path("complaints/<int:pk>/mark_seen/", mark_complaint_as_seen),
    path("complaints/has_unread/", has_unread_complaints, name="has-unread-complaints"),
    path("mark-all-complaints-seen/", mark_all_complaints_seen, name="mark_all_complaints_seen"),

    # Honor board & points (تستخدم في PointsManager و HonorBoard)
    path("users/search/", EmployeeSearchView.as_view(), name="user-search"),
    path("points/adjust/", AdjustPointsView.as_view(), name="points-adjust"),
    path("honorboard/", HonorBoardView.as_view(), name="honorboard"),
    path("honorboard/toggle/", HonorBoardToggleView.as_view(), name="honorboard-toggle"),

    # Profile
    path("profile/avatar/", AvatarUploadView.as_view(), name="avatar-upload"),
    path("me/", MeView.as_view(), name="me"),
]
